import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..ai_schemas import AIAnalysisRequest
from ..database import get_db
from ..models import (
    AIAnalysisRun,
    AIFinding,
    AIInvestigation,
    AIInvestigationDocument,
    AIInvestigationSource,
    AIAuditLog,
    Finding,
    utc_now,
)
from ..services.ai_analysis import submit_ai_analysis
from ..services.ollama_runtime import detect_environment


router = APIRouter(
    prefix="/ai/investigations",
    tags=["AI Analysis"],
)


def _investigation(db: Session, investigation_id: int) -> AIInvestigation:
    investigation = db.get(AIInvestigation, investigation_id)
    if not investigation:
        raise HTTPException(404, "AI investigation not found.")
    if investigation.status == "archived":
        raise HTTPException(409, "Archived AI investigations are read-only.")
    return investigation


def _run(
    db: Session,
    investigation_id: int,
    run_id: int,
) -> AIAnalysisRun:
    run = (
        db.query(AIAnalysisRun)
        .filter(
            AIAnalysisRun.id == run_id,
            AIAnalysisRun.ai_investigation_id == investigation_id,
        )
        .first()
    )
    if not run:
        raise HTTPException(404, "AI analysis run not found.")
    return run


def _audit(
    db: Session,
    investigation_id: int,
    run_id: int,
    event_type: str,
    details: dict,
) -> None:
    db.add(AIAuditLog(
        ai_investigation_id=investigation_id,
        analysis_run_id=run_id,
        event_type=event_type,
        details_json=json.dumps(details, ensure_ascii=False),
    ))


@router.post(
    "/{investigation_id}/analysis-runs",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_ai_analysis(
    investigation_id: int,
    payload: AIAnalysisRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    investigation = _investigation(db, investigation_id)
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
            "An AI analysis run is already active for this investigation.",
        )

    environment = detect_environment()
    if environment["status"] != "available":
        raise HTTPException(
            503,
            f"Ollama is unavailable: {environment['error'] or 'runtime unavailable'}.",
        )

    model = payload.model or investigation.selected_model
    if not model:
        raise HTTPException(
            422,
            "Select an installed Ollama model before starting AI analysis.",
        )
    available_models = {
        item["name"] for item in environment["models"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if model not in available_models:
        raise HTTPException(
            409,
            "The selected model is not installed in the configured Ollama runtime.",
        )

    attached_documents = (
        db.query(AIInvestigationDocument)
        .filter(
            AIInvestigationDocument.ai_investigation_id == investigation.id
        )
        .order_by(AIInvestigationDocument.id)
        .all()
    )
    selected_document_ids = (
        payload.document_ids
        if payload.document_ids is not None
        else [item.id for item in attached_documents]
    )
    if not selected_document_ids:
        raise HTTPException(
            400,
            "Attach and select at least one document before analysis.",
        )
    if not set(selected_document_ids).issubset(
        {item.id for item in attached_documents}
    ):
        raise HTTPException(
            400,
            "Every selected document must be attached to this AI investigation.",
        )

    linked_source_ids = {
        item.investigation_id
        for item in db.query(AIInvestigationSource)
        .filter(
            AIInvestigationSource.ai_investigation_id == investigation.id
        )
        .all()
    }
    if payload.standard_finding_ids:
        selected_findings = (
            db.query(Finding.id)
            .filter(
                Finding.id.in_(payload.standard_finding_ids),
                Finding.investigation_id.in_(linked_source_ids),
            )
            .all()
        )
        if len(selected_findings) != len(payload.standard_finding_ids):
            raise HTTPException(
                400,
                "Every selected finding must belong to a linked standard investigation.",
            )

    configuration = {
        "document_ids": selected_document_ids,
        "standard_finding_ids": payload.standard_finding_ids,
        "objective": payload.objective,
        "custom_instructions": investigation.custom_instructions,
        "analysis_depth": investigation.analysis_depth,
        "options": {
            "cross_document_analysis": payload.cross_document_analysis,
            "entity_resolution": payload.entity_resolution,
            "timeline_analysis": payload.timeline_analysis,
            "financial_correlation": payload.financial_correlation,
        },
    }
    run = AIAnalysisRun(
        ai_investigation_id=investigation.id,
        status="queued",
        progress=0,
        model_name=model,
        model_version=environment["version"],
        prompt_version="decipher-investigation-v1",
        configuration_json=json.dumps(configuration, ensure_ascii=False),
        result_json="{}",
    )
    investigation.status = "queued"
    investigation.updated_at = utc_now()
    db.add(run)
    db.flush()
    _audit(
        db,
        investigation.id,
        run.id,
        "analysis_queued",
        {
            "model": model,
            "document_ids": selected_document_ids,
            "standard_finding_ids": payload.standard_finding_ids,
        },
    )
    db.commit()
    db.refresh(run)

    try:
        bind = db.get_bind()
        submit_ai_analysis(
            run.id,
            bind,
        )
    except RuntimeError as exc:
        run.status = "failed"
        run.error_message = "The AI analysis worker could not be started."
        run.completed_at = utc_now()
        investigation.status = "failed"
        _audit(
            db,
            investigation.id,
            run.id,
            "analysis_failed",
            {"error": run.error_message},
        )
        db.commit()
        raise HTTPException(503, run.error_message) from exc

    response.headers["Location"] = (
        f"/ai/investigations/{investigation.id}/analysis-runs/{run.id}"
    )
    return {
        "id": run.id,
        "ai_investigation_id": investigation.id,
        "status": run.status,
        "progress": run.progress,
        "model": run.model_name,
        "prompt_version": run.prompt_version,
    }


@router.get("/{investigation_id}/analysis-runs")
def list_ai_analysis_runs(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    if not db.get(AIInvestigation, investigation_id):
        raise HTTPException(404, "AI investigation not found.")
    runs = (
        db.query(AIAnalysisRun)
        .filter(AIAnalysisRun.ai_investigation_id == investigation_id)
        .order_by(AIAnalysisRun.created_at.desc(), AIAnalysisRun.id.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "status": item.status,
            "stage": item.stage,
            "progress": item.progress,
            "model": item.model_name,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "error": item.error_message,
        }
        for item in runs
    ]


@router.get("/{investigation_id}/analysis-runs/{run_id}")
def get_ai_analysis_run(
    investigation_id: int,
    run_id: int,
    db: Session = Depends(get_db),
):
    run = _run(db, investigation_id, run_id)
    findings = (
        db.query(AIFinding)
        .filter(AIFinding.analysis_run_id == run.id)
        .order_by(AIFinding.id)
        .all()
    )
    result = json.loads(run.result_json or "{}")
    return {
        "id": run.id,
        "ai_investigation_id": run.ai_investigation_id,
        "status": run.status,
        "stage": run.stage,
        "progress": run.progress,
        "model": run.model_name,
        "model_version": run.model_version,
        "prompt_version": run.prompt_version,
        "configuration": json.loads(run.configuration_json),
        "result": result,
        "error": run.error_message,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "findings": [
            {
                "id": finding.id,
                "finding_key": finding.finding_key,
                "title": finding.title,
                "category": finding.category,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "description": finding.description,
                "reasoning": finding.reasoning,
                "alternative_explanations": json.loads(
                    finding.alternative_explanations_json
                ),
                "recommended_action": finding.recommended_action,
                "review_status": finding.review_status,
                "reviews": [
                    {
                        "id": review.id,
                        "review_status": review.review_status,
                        "reviewer": review.reviewer,
                        "comment": review.comment,
                        "created_at": review.created_at,
                    }
                    for review in sorted(
                        finding.reviews,
                        key=lambda item: (item.created_at, item.id),
                    )
                ],
                "evidence": [
                    {
                        "id": evidence.id,
                        "ai_document_id": evidence.ai_document_id,
                        "standard_finding_id": evidence.standard_finding_id,
                        "source_type": evidence.source_type,
                        "page_number": evidence.page_number,
                        "field_name": evidence.field_name,
                        "quote": evidence.quoted_text,
                        "verification_status": evidence.verification_status,
                    }
                    for evidence in finding.evidence_links
                ],
            }
            for finding in findings
        ],
    }


@router.post("/{investigation_id}/analysis-runs/{run_id}/cancel")
def cancel_ai_analysis(
    investigation_id: int,
    run_id: int,
    db: Session = Depends(get_db),
):
    investigation = _investigation(db, investigation_id)
    run = _run(db, investigation_id, run_id)
    if run.status not in {"queued", "running", "cancel_requested"}:
        raise HTTPException(409, "This AI analysis run is no longer active.")
    run.cancel_requested = True
    run.status = "cancel_requested"
    _audit(
        db,
        investigation.id,
        run.id,
        "analysis_cancellation_requested",
        {"stage": run.stage},
    )
    db.commit()
    return {
        "id": run.id,
        "status": run.status,
        "message": (
            "Cancellation will take effect at the next analysis-stage boundary."
        ),
    }
