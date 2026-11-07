import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..ai_schemas import (
    AIInvestigationCreate,
    AIInvestigationDocumentSelection,
    AIInvestigationUpdate,
)
from ..database import get_db
from ..models import (
    AIInvestigation,
    AIAnalysisRun,
    AIInvestigationDocument,
    AIInvestigationSource,
    AIAuditLog,
    Document,
    Investigation,
    utc_now,
)
from ..services.evidence_manager import (
    UploadTooLargeError,
    evidence_manager,
)


router = APIRouter(
    prefix="/ai/investigations",
    tags=["AI Investigations"],
)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def _audit(
    db: Session,
    investigation_id: int,
    event_type: str,
    details: dict,
) -> None:
    investigation = db.get(AIInvestigation, investigation_id)
    if investigation:
        investigation.updated_at = utc_now()
    db.add(AIAuditLog(
        ai_investigation_id=investigation_id,
        event_type=event_type,
        details_json=json.dumps(details, ensure_ascii=False),
    ))


def _get_ai_investigation(
    db: Session,
    investigation_id: int,
) -> AIInvestigation:
    investigation = (
        db.query(AIInvestigation)
        .filter(AIInvestigation.id == investigation_id)
        .first()
    )
    if not investigation:
        raise HTTPException(404, "AI investigation not found.")
    return investigation


def _require_active(investigation: AIInvestigation) -> None:
    if investigation.status == "archived":
        raise HTTPException(
            409,
            "Archived AI investigations are read-only.",
        )


def _serialize_investigation(investigation: AIInvestigation) -> dict:
    return {
        "id": investigation.id,
        "title": investigation.title,
        "description": investigation.description,
        "custom_instructions": investigation.custom_instructions,
        "selected_model": investigation.selected_model,
        "analysis_depth": investigation.analysis_depth,
        "status": investigation.status,
        "created_at": investigation.created_at,
        "updated_at": investigation.updated_at,
        "sources": [
            {
                "investigation_id": source.investigation_id,
                "title": source.investigation.title,
                "linked_at": source.linked_at,
            }
            for source in investigation.sources
        ],
        "documents": [
            {
                "id": document.id,
                "document_id": document.document_id,
                "filename": document.filename,
                "sha256": document.sha256,
                "doc_type": document.doc_type,
                "source_type": document.source_type,
                "processing_status": document.processing_status,
                "added_at": document.added_at,
            }
            for document in investigation.documents
        ],
    }


@router.post("/")
def create_ai_investigation(
    payload: AIInvestigationCreate,
    db: Session = Depends(get_db),
):
    investigation = AIInvestigation(
        title=payload.title,
        description=payload.description,
        custom_instructions=payload.custom_instructions,
        selected_model=payload.selected_model,
        analysis_depth=payload.analysis_depth,
    )
    db.add(investigation)
    db.flush()
    _audit(db, investigation.id, "investigation_created", {
        "analysis_depth": investigation.analysis_depth,
        "selected_model": investigation.selected_model,
    })
    db.commit()
    db.refresh(investigation)
    return _serialize_investigation(investigation)


@router.get("/")
def list_ai_investigations(
    db: Session = Depends(get_db),
):
    investigations = (
        db.query(AIInvestigation)
        .filter(AIInvestigation.status != "archived")
        .order_by(AIInvestigation.updated_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "selected_model": item.selected_model,
            "analysis_depth": item.analysis_depth,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "document_count": len(item.documents),
        }
        for item in investigations
    ]


@router.get("/{investigation_id}")
def get_ai_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    return _serialize_investigation(
        _get_ai_investigation(db, investigation_id)
    )


@router.get("/{investigation_id}/audit-logs")
def list_ai_audit_logs(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    _get_ai_investigation(db, investigation_id)
    records = (
        db.query(AIAuditLog)
        .filter(AIAuditLog.ai_investigation_id == investigation_id)
        .order_by(AIAuditLog.created_at, AIAuditLog.id)
        .all()
    )
    return [
        {
            "id": item.id,
            "event_type": item.event_type,
            "details": json.loads(item.details_json),
            "created_at": item.created_at,
        }
        for item in records
    ]


@router.patch("/{investigation_id}")
def update_ai_investigation(
    investigation_id: int,
    payload: AIInvestigationUpdate,
    db: Session = Depends(get_db),
):
    investigation = _get_ai_investigation(db, investigation_id)
    _require_active(investigation)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(investigation, field, value)
    if changes:
        _audit(db, investigation.id, "investigation_updated", {
            "updated_fields": sorted(changes),
        })
    db.commit()
    db.refresh(investigation)
    return _serialize_investigation(investigation)


@router.delete("/{investigation_id}")
def archive_ai_investigation(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    investigation = _get_ai_investigation(db, investigation_id)
    _require_active(investigation)
    active_run = (
        db.query(AIAnalysisRun)
        .filter(
            AIAnalysisRun.ai_investigation_id == investigation.id,
            AIAnalysisRun.status.in_(("queued", "running", "cancel_requested")),
        )
        .first()
    )
    if active_run:
        raise HTTPException(
            409,
            "Cancel the active AI analysis before archiving this investigation.",
        )
    investigation.status = "archived"
    _audit(db, investigation.id, "investigation_archived", {})
    db.commit()
    return {"id": investigation.id, "status": investigation.status}


@router.post("/{investigation_id}/sources/{standard_investigation_id}")
def link_standard_investigation(
    investigation_id: int,
    standard_investigation_id: int,
    db: Session = Depends(get_db),
):
    ai_investigation = _get_ai_investigation(db, investigation_id)
    _require_active(ai_investigation)
    standard_investigation = (
        db.query(Investigation)
        .filter(Investigation.id == standard_investigation_id)
        .first()
    )
    if not standard_investigation:
        raise HTTPException(404, "Standard investigation not found.")

    source = AIInvestigationSource(
        ai_investigation_id=ai_investigation.id,
        investigation_id=standard_investigation.id,
    )
    db.add(source)
    _audit(db, ai_investigation.id, "standard_investigation_linked", {
        "investigation_id": standard_investigation.id,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            "This standard investigation is already linked.",
        ) from exc
    db.refresh(ai_investigation)
    return _serialize_investigation(ai_investigation)


@router.post("/{investigation_id}/documents")
def select_standard_documents(
    investigation_id: int,
    payload: AIInvestigationDocumentSelection,
    db: Session = Depends(get_db),
):
    ai_investigation = _get_ai_investigation(db, investigation_id)
    _require_active(ai_investigation)
    linked_investigation_ids = [
        source.investigation_id for source in ai_investigation.sources
    ]
    if not linked_investigation_ids:
        raise HTTPException(
            400,
            "Link a standard investigation before selecting its documents.",
        )

    documents = (
        db.query(Document)
        .filter(
            Document.id.in_(payload.document_ids),
            Document.investigation_id.in_(linked_investigation_ids),
        )
        .all()
    )
    if len(documents) != len(payload.document_ids):
        raise HTTPException(
            400,
            "Every selected document must belong to a linked standard investigation.",
        )

    selected_ids = {
        item.document_id for item in ai_investigation.documents
        if item.document_id is not None
    }
    if selected_ids.intersection(payload.document_ids):
        raise HTTPException(409, "A selected document is already attached.")

    for document in documents:
        db.add(AIInvestigationDocument(
            ai_investigation_id=ai_investigation.id,
            document_id=document.id,
            filename=document.filename,
            sha256=document.sha256,
            doc_type=document.doc_type,
            source_type="standard_document",
            processing_status=document.processing_status,
        ))
    _audit(db, ai_investigation.id, "standard_documents_selected", {
        "document_ids": sorted(payload.document_ids),
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            "One or more selected documents are already attached.",
        ) from exc
    db.refresh(ai_investigation)
    return _serialize_investigation(ai_investigation)


@router.post("/{investigation_id}/documents/upload")
async def upload_ai_document(
    investigation_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ai_investigation = _get_ai_investigation(db, investigation_id)
    _require_active(ai_investigation)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported document format.")

    try:
        storage_path, digest = await evidence_manager.save_upload(
            file,
            f"ai-{ai_investigation.id}",
        )
    except UploadTooLargeError as exc:
        raise HTTPException(413, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    duplicate = (
        db.query(AIInvestigationDocument)
        .filter(
            AIInvestigationDocument.ai_investigation_id == ai_investigation.id,
            AIInvestigationDocument.sha256 == digest,
        )
        .first()
    )
    if duplicate:
        Path(storage_path).unlink(missing_ok=True)
        raise HTTPException(
            409,
            "This document has already been uploaded to the AI investigation.",
        )

    db.add(AIInvestigationDocument(
        ai_investigation_id=ai_investigation.id,
        filename=filename,
        sha256=digest,
        storage_path=storage_path,
        source_type="ai_upload",
        processing_status="uploaded",
    ))
    _audit(db, ai_investigation.id, "ai_document_uploaded", {
        "filename": filename,
        "sha256": digest,
    })
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)
        raise HTTPException(409, "The AI document was already added.") from exc
    except SQLAlchemyError:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)
        raise

    db.refresh(ai_investigation)
    return _serialize_investigation(ai_investigation)
