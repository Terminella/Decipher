import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Investigation, Report
from ..services.evidence_manager import evidence_manager
from ..services.pdf_report_generator import generate_investigation_pdf
from ..services.report_generator import generate_investigation_report


router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
)


@router.post("/{investigation_id}/generate")
def generate_report(
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

    report_data = generate_investigation_report(investigation)

    filename = (
        f"investigation_{investigation_id}_{uuid.uuid4().hex}.json"
    )

    file_path = evidence_manager.save_report(
        investigation_id=investigation_id,
        filename=filename,
        content=json.dumps(
            report_data,
            indent=4,
            ensure_ascii=False,
        ).encode("utf-8"),
    )

    report = Report(
        investigation_id=investigation_id,
        format="json",
        file_path=file_path,
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "report_id": report.id,
        "investigation_id": investigation_id,
        "format": "json",
        "download_url": f"/reports/{report.id}/download",
        "report": report_data,
    }


@router.post("/{investigation_id}/generate-pdf")
def generate_pdf_report(
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

    report_data = generate_investigation_report(investigation)
    filename = (
        f"investigation_{investigation_id}_{uuid.uuid4().hex}.pdf"
    )
    file_path = evidence_manager.save_report(
        investigation_id=investigation_id,
        filename=filename,
        content=generate_investigation_pdf(report_data),
    )
    report = Report(
        investigation_id=investigation_id,
        format="pdf",
        file_path=file_path,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return {
        "report_id": report.id,
        "investigation_id": investigation_id,
        "format": "pdf",
        "download_url": f"/reports/{report.id}/download",
    }


@router.get("/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(Report.id == report_id).first()

    if not report:
        raise HTTPException(404, "Report not found.")

    path = evidence_manager.get_report_path(report.file_path)

    return FileResponse(
        path=path,
        media_type=(
            "application/pdf"
            if report.format == "pdf"
            else "application/json"
        ),
        filename=path.name,
    )


@router.get("/investigation/{investigation_id}")
def list_reports(
    investigation_id: int,
    db: Session = Depends(get_db),
):
    reports = (
        db.query(Report)
        .filter(Report.investigation_id == investigation_id)
        .order_by(Report.created_at.desc())
        .all()
    )

    return [
        {
            "id": report.id,
            "investigation_id": report.investigation_id,
            "format": report.format,
            "created_at": report.created_at,
            "download_url": f"/reports/{report.id}/download",
        }
        for report in reports
    ]