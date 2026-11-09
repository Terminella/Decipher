import json
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Investigation,
    Document,
    ExtractedField,
    Finding,
    AnalysisRun,
)
from ..schemas import InvestigationCreate, InvestigationRead
from ..services.evidence_manager import evidence_manager
from ..services.evidence_manager import UploadTooLargeError
from ..services.pipeline import process_document

from ..services.contextual_schemas import (
    InvestigationInput,
    DocumentInput,
    ExtractedField as ContextualField,
    VisualAnomaly,
)

from ..services.correlation import run_contextual_analysis


router = APIRouter(
    prefix="/investigations",
    tags=["Investigations"],
)

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg",
    ".tif", ".tiff", ".bmp", ".webp",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: _jsonable(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _extract_fields(result: dict) -> list[dict]:
    extracted = result.get("extracted_information", {})
    fields = extracted.get("fields", {})
    metadata = extracted.get("field_metadata", {})

    output = []

    occurrences = extracted.get("field_occurrences")
    if isinstance(occurrences, list):
        for item in occurrences:
            if not isinstance(item, dict):
                continue
            output.append({
                "field_name": str(item.get("field_name", "unknown")),
                "field_value": str(item.get("field_value", "")),
                "confidence": item.get("confidence"),
                "page_number": item.get("page_number", 1),
                "bbox": item.get("bbox"),
            })
        return output

    if isinstance(fields, dict):
        for key, value in fields.items():
            field_metadata = metadata.get(key, {}) if isinstance(metadata, dict) else {}
            locations = field_metadata.get("locations", [])
            location = locations[0] if locations else {}

            if isinstance(value, dict):
                output.append({
                    "field_name": str(key),
                    "field_value": str(value.get("value", "")),
                    "confidence": value.get(
                        "confidence",
                        field_metadata.get("confidence"),
                    ),
                    "page_number": value.get(
                        "page",
                        location.get("page_number", 1),
                    ),
                    "bbox": value.get("bbox", location.get("bbox")),
                })
            else:
                output.append({
                    "field_name": str(key),
                    "field_value": str(value),
                    "confidence": field_metadata.get("confidence"),
                    "page_number": location.get("page_number", 1),
                    "bbox": location.get("bbox"),
                })

    elif isinstance(fields, list):
        for item in fields:
            if not isinstance(item, dict):
                continue

            output.append({
                "field_name": str(
                    item.get("field_name")
                    or item.get("label")
                    or item.get("name")
                    or "unknown"
                ),
                "field_value": str(
                    item.get("field_value")
                    or item.get("value")
                    or ""
                ),
                "confidence": item.get(
                    "confidence",
                    item.get("ocr_confidence"),
                ),
                "page_number": item.get(
                    "page_number",
                    item.get("page", 1),
                ),
                "bbox": item.get("bbox"),
            })

    return output


def _xywh_bbox(bbox):
    if isinstance(bbox, dict):
        if {"x0", "y0", "x1", "y1"}.issubset(bbox):
            return {
                "x": bbox["x0"],
                "y": bbox["y0"],
                "width": bbox["x1"] - bbox["x0"],
                "height": bbox["y1"] - bbox["y0"],
            }
        if {"x", "y", "width", "height"}.issubset(bbox):
            return bbox
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        x0, y0, x1, y1 = bbox
        return {
            "x": x0,
            "y": y0,
            "width": x1 - x0,
            "height": y1 - y0,
        }
    return None


def _scale_field_bbox(bbox, page_number, extracted_pages, visual_pages):
    normalized = _xywh_bbox(bbox)
    if normalized is None:
        return None

    extracted_page = next(
        (
            page for page in extracted_pages
            if page.get("page_number") == page_number
        ),
        None,
    )
    visual_page = next(
        (
            page for page in visual_pages
            if page.get("page_number") == page_number
        ),
        None,
    )
    if extracted_page is None or visual_page is None:
        return normalized

    source_width = extracted_page.get("width")
    source_height = extracted_page.get("height")
    target_width = visual_page.get("image_width")
    target_height = visual_page.get("image_height")
    if not source_width or not source_height or not target_width or not target_height:
        return normalized

    scale_x = target_width / source_width
    scale_y = target_height / source_height
    return {
        "x": normalized["x"] * scale_x,
        "y": normalized["y"] * scale_y,
        "width": normalized["width"] * scale_x,
        "height": normalized["height"] * scale_y,
    }


def _contextual_field_type(field_name):
    return {
        "supplier": "name",
        "payer": "name",
        "document_date": "date",
        "amount": "amount",
        "amount_in_words": "amount",
        "purchase_order": "document_reference",
        "invoice_number": "document_reference",
        "transaction_id": "document_reference",
        "reference": "document_reference",
    }.get(field_name, field_name)


def _contextual_field_label(field_name):
    return {
        "supplier": "Supplier name",
        "payer": "Supplier name",
        "document_date": "Document date",
        "amount": "Total amount",
        "amount_in_words": "Amount in words",
    }.get(field_name, field_name.replace("_", " "))


def _build_contextual_document(document: Document) -> DocumentInput:
    result = json.loads(document.processing_result_json or "{}")
    raw_fields = _extract_fields(result)
    extracted = result.get("extracted_information", {})
    extracted_pages = extracted.get("pages", [])
    visual_result = result.get("visual_forensics", {})
    visual_pages = visual_result.get("pages", [])
    stored_fields = {
        (field.field_name, field.field_value): field
        for field in document.extracted_fields
    }

    contextual_fields = []

    for index, item in enumerate(raw_fields):
        page_number = max(1, int(item.get("page_number") or 1))
        bbox = _scale_field_bbox(
            item.get("bbox"),
            page_number,
            extracted_pages,
            visual_pages,
        )
        normalized_bbox = (
            {
                "x0": bbox["x"],
                "y0": bbox["y"],
                "x1": bbox["x"] + bbox["width"],
                "y1": bbox["y"] + bbox["height"],
            }
            if bbox is not None
            else None
        )
        stored_field = stored_fields.get(
            (item["field_name"], item["field_value"])
        )

        contextual_fields.append(
            ContextualField(
                field_id=(
                    str(stored_field.id)
                    if stored_field is not None
                    else f"{document.id}-{index}"
                ),
                label=_contextual_field_label(item["field_name"]),
                field_type=_contextual_field_type(item["field_name"]),
                value=item["field_value"],
                page=page_number,
                ocr_confidence=item.get("confidence"),
                bbox=normalized_bbox,
            )
        )

    contextual_anomalies = []

    if isinstance(visual_pages, list):
        for page_result in visual_pages:
            observations = page_result.get("observations", [])
            for index, anomaly in enumerate(observations):
                if not isinstance(anomaly, dict):
                    continue
                bbox = _xywh_bbox(anomaly.get("bbox"))
                normalized_bbox = (
                    {
                        "x0": bbox["x"],
                        "y0": bbox["y"],
                        "x1": bbox["x"] + bbox["width"],
                        "y1": bbox["y"] + bbox["height"],
                    }
                    if bbox is not None
                    else None
                )
                page_number = anomaly.get(
                    "page_number",
                    page_result.get("page_number"),
                )
                contextual_anomalies.append(
                    VisualAnomaly(
                        anomaly_id=(
                            f"{document.id}-visual-{page_number}-{index}"
                        ),
                        kind=str(
                            anomaly.get("kind")
                            or anomaly.get("type")
                            or "visual_anomaly"
                        ),
                        page=page_number,
                        score=anomaly.get(
                            "score",
                            anomaly.get("confidence"),
                        ),
                        description=anomaly.get(
                            "description",
                            anomaly.get("message"),
                        ),
                        bbox=normalized_bbox,
                    )
                )

    return DocumentInput(
        document_id=str(document.id),
        filename=document.filename,
        doc_type=document.doc_type,
        fields=contextual_fields,
        visual_anomalies=contextual_anomalies,
    )


@router.post("/", response_model=InvestigationRead)
def create_investigation(
    payload: InvestigationCreate,
    db: Session = Depends(get_db),
):
    investigation = Investigation(
        title=payload.title,
        description=payload.description,
    )

    db.add(investigation)
    db.commit()
    db.refresh(investigation)

    return investigation


@router.get("/", response_model=list[InvestigationRead])
def list_investigations(
    db: Session = Depends(get_db),
):
    return (
        db.query(Investigation)
        .order_by(Investigation.created_at.desc())
        .all()
    )


@router.get("/{investigation_id}")
def get_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id)
        .first()
    )

    if not investigation:
        raise HTTPException(404, "Investigation not found.")

    return {
        "id": investigation.id,
        "title": investigation.title,
        "description": investigation.description,
        "status": investigation.status,
        "created_at": investigation.created_at,
        "documents": [
            {
                "id": document.id,
                "investigation_id": document.investigation_id,
                "filename": document.filename,
                "sha256": document.sha256,
                "doc_type": document.doc_type,
                "processing_status": document.processing_status,
                "uploaded_at": document.uploaded_at,
                "extracted_fields": [
                    {
                        "id": field.id,
                        "field_name": field.field_name,
                        "field_value": field.field_value,
                        "confidence": field.confidence,
                        "page_number": field.page_number,
                        "bbox": (
                            json.loads(field.bbox_json)
                            if field.bbox_json else None
                        ),
                    }
                    for field in document.extracted_fields
                ],
                "processing_result": (
                    json.loads(document.processing_result_json)
                    if document.processing_result_json else None
                ),
            }
            for document in investigation.documents
        ],
        "findings": [
            {
                "id": finding.id,
                "investigation_id": finding.investigation_id,
                "document_id": finding.document_id,
                "anomaly_type": finding.anomaly_type,
                "classification": finding.classification,
                "severity": finding.severity,
                "priority_score": finding.priority_score,
                "title": finding.title,
                "field_name": finding.field_name,
                "explanation": finding.explanation,
                "evidence": (
                    json.loads(finding.evidence_json)
                    if finding.evidence_json else []
                ),
                "created_at": finding.created_at,
            }
            for finding in investigation.findings
        ],
    }


@router.get("/{investigation_id}/documents/{document_id}/preview")
def preview_investigation_document(
    investigation_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.investigation_id == investigation_id,
        )
        .first()
    )
    if not document:
        raise HTTPException(404, "Document not found in this investigation.")

    try:
        path = evidence_manager.get_document_path(document.storage_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(404, "The stored document is unavailable.") from exc

    media_type = mimetypes.guess_type(document.filename)[0]
    return FileResponse(
        path=path,
        media_type=media_type or "application/octet-stream",
        filename=document.filename,
        content_disposition_type="inline",
    )


@router.get("/{investigation_id}/analysis-runs")
def list_analysis_runs(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id)
        .first()
    )
    if not investigation:
        raise HTTPException(404, "Investigation not found.")

    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.investigation_id == investigation_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .all()
    )
    return [
        {
            "id": run.id,
            "investigation_id": run.investigation_id,
            "documents_analyzed": run.documents_analyzed,
            "findings_count": run.findings_count,
            "created_at": run.created_at,
        }
        for run in runs
    ]


@router.get("/{investigation_id}/analysis-runs/{run_id}")
def get_analysis_run(
    investigation_id: int,
    run_id: int,
    db: Session = Depends(get_db),
):
    run = (
        db.query(AnalysisRun)
        .filter(
            AnalysisRun.id == run_id,
            AnalysisRun.investigation_id == investigation_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(404, "Analysis run not found.")

    result = json.loads(run.result_json)
    return {
        "id": run.id,
        "investigation_id": run.investigation_id,
        "documents_analyzed": run.documents_analyzed,
        "findings_count": run.findings_count,
        "created_at": run.created_at,
        "result": result,
    }


@router.post("/{investigation_id}/documents")
async def upload_document(
    investigation_id: int,
    file: UploadFile = File(...),
    force_ocr: bool = False,
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id)
        .first()
    )

    if not investigation:
        raise HTTPException(404, "Investigation not found.")

    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported document format.")

    try:
        storage_path, digest = await evidence_manager.save_upload(
            file,
            investigation_id,
        )

        existing = (
            db.query(Document)
            .filter(
                Document.investigation_id == investigation_id,
                Document.sha256 == digest,
            )
            .first()
        )

        if existing:
            Path(storage_path).unlink(missing_ok=True)
            raise HTTPException(
                409,
                "This document has already been uploaded to the investigation.",
            )

        document = Document(
            investigation_id=investigation_id,
            filename=filename,
            storage_path=storage_path,
            sha256=digest,
            processing_status="processing",
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        try:
            result = process_document(
                storage_path,
                force_ocr=force_ocr,
            )

            document.processing_result_json = json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            )
            document.processing_status = "completed"

            classification = result.get("classification", {})
            if isinstance(classification, dict):
                document.doc_type = (
                    classification.get("document_type")
                    or classification.get("type")
                )
            elif isinstance(classification, str):
                document.doc_type = classification

            for item in _extract_fields(result):
                db.add(
                    ExtractedField(
                        document_id=document.id,
                        field_name=item["field_name"],
                        field_value=item["field_value"],
                        confidence=item["confidence"],
                        page_number=item["page_number"],
                        bbox_json=_json(item["bbox"])
                        if item["bbox"] is not None else None,
                    )
                )

            investigation.status = "processing"
            db.commit()
            db.refresh(document)

        except Exception:
            document.processing_status = "failed"
            db.commit()
            raise

        return {
            "document_id": document.id,
            "filename": document.filename,
            "processing_status": document.processing_status,
            "result": result,
        }

    except HTTPException:
        raise
    except UploadTooLargeError as exc:
        db.rollback()
        raise HTTPException(413, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            500,
            f"Document upload or processing failed: {exc}",
        ) from exc


@router.post("/{investigation_id}/analyze")
def analyze_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    investigation = (
        db.query(Investigation)
        .filter(Investigation.id == investigation_id)
        .first()
    )

    if not investigation:
        raise HTTPException(404, "Investigation not found.")

    documents = (
        db.query(Document)
        .filter(
            Document.investigation_id == investigation_id,
            Document.processing_status == "completed",
        )
        .all()
    )

    if not documents:
        raise HTTPException(
            400,
            "Upload and process at least one document first.",
        )

    contextual_documents = [
        _build_contextual_document(document)
        for document in documents
    ]

    payload = InvestigationInput(
        investigation_id=str(investigation_id),
        documents=contextual_documents,
    )

    try:
        analysis = run_contextual_analysis(payload)
    except Exception as exc:
        raise HTTPException(
            500,
            f"Contextual analysis failed: {exc}",
        ) from exc

    findings = getattr(analysis, "findings", [])

    db.query(Finding).filter(
        Finding.investigation_id == investigation_id
    ).delete(synchronize_session=False)

    saved_findings = []

    for item in findings:
        evidence = getattr(item, "evidence", None)

        finding = Finding(
            investigation_id=investigation_id,
            document_id=(
                int(item.document_ids[0])
                if len(item.document_ids) == 1
                and item.document_ids[0].isdigit()
                else None
            ),
            anomaly_type=item.anomaly_type.value,
            classification=item.classification.value,
            severity=item.severity.value,
            priority_score=getattr(item, "priority_score", None),
            title=str(getattr(item, "title", "Finding")),
            field_name=getattr(item, "field_name", None),
            explanation=str(
                getattr(item, "explanation", "")
            ),
            evidence_json=_json(
                _jsonable(evidence)
            ),
        )

        db.add(finding)
        saved_findings.append(finding)

    db.flush()
    run_result = {
        "documents": [
            {
                "document_id": document.id,
                "filename": document.filename,
                "sha256": document.sha256,
                "doc_type": document.doc_type,
            }
            for document in documents
        ],
        "findings": [
            {
                "id": finding.id,
                "title": finding.title,
                "anomaly_type": finding.anomaly_type,
                "severity": finding.severity,
                "classification": finding.classification,
                "explanation": finding.explanation,
                "priority_score": finding.priority_score,
                "document_id": finding.document_id,
                "field_name": finding.field_name,
                "evidence": (
                    json.loads(finding.evidence_json)
                    if finding.evidence_json else []
                ),
            }
            for finding in saved_findings
        ],
    }
    analysis_run = AnalysisRun(
        investigation_id=investigation_id,
        documents_analyzed=len(documents),
        findings_count=len(saved_findings),
        result_json=_json(run_result),
    )
    db.add(analysis_run)
    investigation.status = "analyzed"
    db.commit()
    db.refresh(analysis_run)

    return {
        "investigation_id": investigation_id,
        "analysis_run_id": analysis_run.id,
        "created_at": analysis_run.created_at,
        "documents_analyzed": len(documents),
        "findings_count": len(saved_findings),
        "findings": run_result["findings"],
    }