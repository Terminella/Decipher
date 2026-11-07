import json
from pathlib import Path

import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.classifier import classify_document
from app.services import ollama_runtime
from app.routes import (
    ai_analysis as ai_analysis_route,
    investigations as investigations_route,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"
    test_engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "storage" / "uploads")
    monkeypatch.setattr(settings, "report_dir", tmp_path / "storage" / "reports")
    app.dependency_overrides[get_db] = override_get_db

    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_root_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ai_environment_endpoint_reports_ollama_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        ollama_runtime,
        "detect_environment",
        lambda: {
            "status": "unavailable",
            "models": [],
            "model_count": 0,
            "ollama_installed": False,
        },
    )

    response = client.get("/ai/environment")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["ollama_installed"] is False


def test_ai_models_endpoint_returns_discovered_models(client, monkeypatch):
    monkeypatch.setattr(
        ollama_runtime,
        "detect_environment",
        lambda: {
            "status": "available",
            "endpoint": "http://127.0.0.1:11434",
            "models": [{"name": "local:latest"}],
            "recommendation": {"model_name": "local:latest"},
            "error": None,
        },
    )

    response = client.get("/ai/models")

    assert response.status_code == 200
    assert response.json()["models"] == [{"name": "local:latest"}]


def test_ai_investigation_lifecycle_is_separate_and_audited(client):
    created = client.post(
        "/ai/investigations/",
        json={
            "title": "Independent AI Review",
            "custom_instructions": "Compare the selected records.",
            "analysis_depth": "deep",
        },
    )

    assert created.status_code == 200
    investigation = created.json()
    assert investigation["status"] == "created"
    assert investigation["sources"] == []
    assert investigation["documents"] == []

    logs = client.get(
        f"/ai/investigations/{investigation['id']}/audit-logs"
    )
    assert logs.status_code == 200
    assert logs.json()[0]["event_type"] == "investigation_created"

    archived = client.delete(
        f"/ai/investigations/{investigation['id']}"
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    update = client.patch(
        f"/ai/investigations/{investigation['id']}",
        json={"title": "Updated after archive"},
    )
    assert update.status_code == 409


def test_ai_investigation_defaults_to_bounded_quick_analysis(client):
    created = client.post(
        "/ai/investigations/",
        json={"title": "Fast default analysis"},
    )

    assert created.status_code == 200
    assert created.json()["analysis_depth"] == "quick"


def test_ai_investigation_can_link_a_standard_investigation(client):
    standard = client.post(
        "/investigations/",
        json={"title": "Existing forensic case"},
    ).json()
    ai_investigation = client.post(
        "/ai/investigations/",
        json={"title": "AI-assisted review"},
    ).json()
    link_url = (
        f"/ai/investigations/{ai_investigation['id']}/sources/"
        f"{standard['id']}"
    )

    linked = client.post(link_url)
    assert linked.status_code == 200
    assert linked.json()["sources"][0]["investigation_id"] == standard["id"]

    duplicate = client.post(link_url)
    assert duplicate.status_code == 409


def test_ai_document_selection_requires_linked_source_and_is_non_destructive(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        investigations_route,
        "process_document",
        lambda *_args, **_kwargs: {
            "filename": "source.pdf",
            "classification": {"document_type": "invoice"},
            "extracted_information": {
                "full_text": "",
                "fields": {},
                "pages": [],
            },
            "visual_forensics": {"pages": []},
            "warnings": [],
        },
    )
    standard = client.post(
        "/investigations/",
        json={"title": "Source forensic case"},
    ).json()
    uploaded = client.post(
        f"/investigations/{standard['id']}/documents",
        files={"file": ("source.pdf", b"%PDF-1.4 sample", "application/pdf")},
    )
    assert uploaded.status_code == 200
    document_id = uploaded.json()["document_id"]

    ai_investigation = client.post(
        "/ai/investigations/",
        json={"title": "Selective AI review"},
    ).json()
    selection_url = f"/ai/investigations/{ai_investigation['id']}/documents"
    payload = {"document_ids": [document_id]}

    unlinked_selection = client.post(selection_url, json=payload)
    assert unlinked_selection.status_code == 400

    link = client.post(
        f"/ai/investigations/{ai_investigation['id']}/sources/{standard['id']}"
    )
    assert link.status_code == 200

    selected = client.post(selection_url, json=payload)
    assert selected.status_code == 200
    linked_document = selected.json()["documents"][0]
    assert linked_document["document_id"] == document_id
    assert linked_document["source_type"] == "standard_document"

    duplicate = client.post(selection_url, json=payload)
    assert duplicate.status_code == 409
    standard_details = client.get(
        f"/investigations/{standard['id']}"
    ).json()
    assert len(standard_details["documents"]) == 1
    assert standard_details["documents"][0]["processing_status"] == "completed"


def test_investigation_document_preview_is_inline_and_scoped(client, monkeypatch):
    monkeypatch.setattr(
        investigations_route,
        "process_document",
        lambda *_args, **_kwargs: {
            "filename": "source.pdf",
            "classification": {"document_type": "invoice"},
            "extracted_information": {
                "full_text": "",
                "fields": {},
                "pages": [],
            },
            "visual_forensics": {"pages": []},
            "warnings": [],
        },
    )
    investigation = client.post(
        "/investigations/",
        json={"title": "Preview test"},
    ).json()
    other_investigation = client.post(
        "/investigations/",
        json={"title": "Other case"},
    ).json()
    document_content = b"%PDF-1.4 preview test"
    uploaded = client.post(
        f"/investigations/{investigation['id']}/documents",
        files={"file": ("source.pdf", document_content, "application/pdf")},
    )
    assert uploaded.status_code == 200
    document_id = uploaded.json()["document_id"]

    preview = client.get(
        f"/investigations/{investigation['id']}/documents/{document_id}/preview"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.content == document_content

    wrong_investigation = client.get(
        f"/investigations/{other_investigation['id']}/documents/{document_id}/preview"
    )
    assert wrong_investigation.status_code == 404


def test_ai_uploaded_document_does_not_create_standard_document(client):
    investigation = client.post(
        "/ai/investigations/",
        json={"title": "Independent document review"},
    ).json()
    path = (
        Path(__file__).resolve().parents[2]
        / "sample_documents"
        / "genuine"
        / "CASE-001_invoice_genuine.pdf"
    )

    with path.open("rb") as stream:
        uploaded = client.post(
            f"/ai/investigations/{investigation['id']}/documents/upload",
            files={"file": (path.name, stream, "application/pdf")},
        )

    assert uploaded.status_code == 200
    document = uploaded.json()["documents"][0]
    assert document["source_type"] == "ai_upload"
    assert document["processing_status"] == "uploaded"
    assert "storage_path" not in document
    assert client.get("/investigations/").json() == []

    with path.open("rb") as stream:
        duplicate = client.post(
            f"/ai/investigations/{investigation['id']}/documents/upload",
            files={"file": (path.name, stream, "application/pdf")},
        )
    assert duplicate.status_code == 409


def test_ai_analysis_requires_running_ollama_before_queueing(client, monkeypatch):
    investigation = client.post(
        "/ai/investigations/",
        json={"title": "Offline AI review", "selected_model": "local:latest"},
    ).json()
    monkeypatch.setattr(
        ai_analysis_route,
        "detect_environment",
        lambda: {
            "status": "unavailable",
            "error": "Could not connect to Ollama.",
        },
    )

    response = client.post(
        f"/ai/investigations/{investigation['id']}/analysis-runs",
        json={},
    )

    assert response.status_code == 503
    assert "Ollama is unavailable" in response.json()["detail"]
    assert client.get(
        f"/ai/investigations/{investigation['id']}/analysis-runs"
    ).json() == []


def test_ai_analysis_queues_persisted_run_and_accepts_cancellation(
    client,
    monkeypatch,
):
    investigation = client.post(
        "/ai/investigations/",
        json={"title": "Queued AI review", "selected_model": "local:latest"},
    ).json()
    sample_path = (
        Path(__file__).resolve().parents[2]
        / "sample_documents"
        / "genuine"
        / "CASE-001_invoice_genuine.pdf"
    )
    with sample_path.open("rb") as stream:
        uploaded = client.post(
            f"/ai/investigations/{investigation['id']}/documents/upload",
            files={
                "file": (
                    sample_path.name,
                    stream,
                    "application/pdf",
                )
            },
        )
    assert uploaded.status_code == 200
    attached_document_id = uploaded.json()["documents"][0]["id"]

    monkeypatch.setattr(
        ai_analysis_route,
        "detect_environment",
        lambda: {
            "status": "available",
            "version": "0.5.0",
            "models": [{"name": "local:latest"}],
        },
    )
    submitted = []
    monkeypatch.setattr(
        ai_analysis_route,
        "submit_ai_analysis",
        lambda run_id, bind: submitted.append((run_id, bind)),
    )

    response = client.post(
        f"/ai/investigations/{investigation['id']}/analysis-runs",
        json={"document_ids": [attached_document_id]},
    )

    assert response.status_code == 202
    run = response.json()
    assert run["status"] == "queued"
    assert run["model"] == "local:latest"
    assert len(submitted) == 1
    assert response.headers["location"].endswith(
        f"/analysis-runs/{run['id']}"
    )

    cancellation = client.post(
        f"/ai/investigations/{investigation['id']}/analysis-runs/"
        f"{run['id']}/cancel"
    )
    assert cancellation.status_code == 200
    assert cancellation.json()["status"] == "cancel_requested"

    archive = client.delete(
        f"/ai/investigations/{investigation['id']}"
    )
    assert archive.status_code == 409


def test_create_investigation(client):
    response = client.post(
        "/investigations/",
        json={
            "title": "API Test Investigation",
            "description": "Created during automated testing.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] is not None
    assert data["title"] == "API Test Investigation"


def test_list_investigations(client):
    response = client.get("/investigations/")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_nonexistent_investigation(client):
    response = client.get("/investigations/999999")

    assert response.status_code == 404


def test_upload_to_nonexistent_investigation(client):
    response = client.post(
        "/investigations/999999/documents",
        files={
            "file": (
                "sample.pdf",
                b"not a real pdf",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 404


def test_unsupported_file_type(client):
    investigation = client.post(
        "/investigations/",
        json={"title": "File Validation Test"},
    ).json()

    response = client.post(
        f"/investigations/{investigation['id']}/documents",
        files={
            "file": (
                "sample.exe",
                b"not allowed",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400


def test_upload_size_limit_returns_payload_too_large(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size", 10)
    investigation = client.post(
        "/investigations/",
        json={"title": "Size Validation Test"},
    ).json()

    response = client.post(
        f"/investigations/{investigation['id']}/documents",
        files={"file": ("sample.pdf", b"x" * 11, "application/pdf")},
    )

    assert response.status_code == 413


def test_classifier_recognizes_procurement_sample_types():
    assert classify_document(
        "INVOICE Invoice number Total amount Payment terms"
    )["document_type"] == "invoice"
    assert classify_document(
        "PURCHASE ORDER Purchase order Approved total Order date"
    )["document_type"] == "purchase_order"
    assert classify_document(
        "PAYMENT CONFIRMATION Transaction ID Payer Payee Amount transferred"
    )["document_type"] == "payment_confirmation"


def test_sample_investigation_full_workflow(client):
    repo_root = Path(__file__).resolve().parents[2]
    investigation = client.post(
        "/investigations/",
        json={
            "title": "CASE-001 integration test",
            "description": "Synthetic sample workflow test.",
        },
    ).json()
    investigation_id = investigation["id"]

    uploaded_names = []
    for variant in ("genuine", "manipulated"):
        for kind in ("invoice", "purchase_order", "bank_statement"):
            path = (
                repo_root
                / "sample_documents"
                / variant
                / f"CASE-001_{kind}_{variant}.pdf"
            )
            with path.open("rb") as stream:
                response = client.post(
                    f"/investigations/{investigation_id}/documents",
                    files={
                        "file": (
                            path.name,
                            stream,
                            "application/pdf",
                        )
                    },
                )
            assert response.status_code == 200, response.text
            assert response.json()["processing_status"] == "completed"
            assert len(response.json()["result"]["sha256"]) == 64
            uploaded_names.append(path.name)

    duplicate_path = (
        repo_root
        / "sample_documents"
        / "genuine"
        / "CASE-001_invoice_genuine.pdf"
    )
    with duplicate_path.open("rb") as stream:
        duplicate = client.post(
            f"/investigations/{investigation_id}/documents",
            files={
                "file": (
                    duplicate_path.name,
                    stream,
                    "application/pdf",
                )
            },
        )
    assert duplicate.status_code == 409

    details_response = client.get(
        f"/investigations/{investigation_id}"
    )
    assert details_response.status_code == 200
    details = details_response.json()
    assert len(details["documents"]) == 6
    assert all(
        "storage_path" not in document
        for document in details["documents"]
    )
    assert all(
        field["page_number"] == 1 and field["bbox"]
        for document in details["documents"]
        for field in document["extracted_fields"]
    )
    assert {
        document["doc_type"]
        for document in details["documents"]
    } == {"invoice", "purchase_order", "payment_confirmation"}

    analysis_response = client.post(
        f"/investigations/{investigation_id}/analyze"
    )
    assert analysis_response.status_code == 200
    analysis = analysis_response.json()
    assert analysis["documents_analyzed"] == 6
    assert analysis["findings_count"] > 0
    anomaly_types = {
        finding["anomaly_type"]
        for finding in analysis["findings"]
    }
    assert {
        "amount_mismatch",
        "name_mismatch",
        "date_mismatch",
    }.issubset(anomaly_types)
    assert all(
        isinstance(finding["evidence"], list)
        and all(isinstance(item, dict) for item in finding["evidence"])
        for finding in analysis["findings"]
    )

    first_run = client.get(
        f"/investigations/{investigation_id}/analysis-runs"
    )
    assert first_run.status_code == 200
    first_run_list = first_run.json()
    assert len(first_run_list) == 1
    first_run_id = analysis["analysis_run_id"]
    assert first_run_list[0]["id"] == first_run_id
    assert first_run_list[0]["created_at"] == analysis["created_at"]

    first_run_detail = client.get(
        f"/investigations/{investigation_id}/analysis-runs/{first_run_id}"
    )
    assert first_run_detail.status_code == 200
    first_snapshot = first_run_detail.json()
    assert first_snapshot["result"]["findings"] == analysis["findings"]
    assert len(first_snapshot["result"]["documents"]) == 6

    second_analysis_response = client.post(
        f"/investigations/{investigation_id}/analyze"
    )
    assert second_analysis_response.status_code == 200
    second_analysis = second_analysis_response.json()
    assert second_analysis["analysis_run_id"] != first_run_id

    history = client.get(
        f"/investigations/{investigation_id}/analysis-runs"
    ).json()
    assert len(history) == 2
    assert history[0]["id"] == second_analysis["analysis_run_id"]
    assert history[1]["id"] == first_run_id
    assert history[0]["created_at"] >= history[1]["created_at"]

    preserved_first_run = client.get(
        f"/investigations/{investigation_id}/analysis-runs/{first_run_id}"
    ).json()
    assert preserved_first_run["result"] == first_snapshot["result"]

    report_response = client.post(
        f"/reports/{investigation_id}/generate"
    )
    assert report_response.status_code == 200
    report_id = report_response.json()["report_id"]
    download = client.get(f"/reports/{report_id}/download")
    assert download.status_code == 200
    report = json.loads(download.content)
    assert report["summary"]["document_count"] == 6
    assert report["summary"]["finding_count"] == analysis["findings_count"]
    assert set(report["sections"]) == {
        "document_overview",
        "extracted_information",
        "contextual_analysis",
        "visual_forensic_findings",
        "evidence_and_traceability",
        "investigation_summary",
    }
    assert report["sections"]["evidence_and_traceability"]


def test_generate_and_download_pdf_report(client):
    investigation = client.post(
        "/investigations/",
        json={
            "title": "PDF verification case",
            "description": "Review <unsafe> source text & attachments.",
        },
    ).json()

    generated = client.post(
        f"/reports/{investigation['id']}/generate-pdf"
    )

    assert generated.status_code == 200
    assert generated.json()["format"] == "pdf"
    downloaded = client.get(generated.json()["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.content.startswith(b"%PDF-")
    pdf = pymupdf.open(stream=downloaded.content, filetype="pdf")
    report_text = "\n".join(page.get_text() for page in pdf)
    assert "PDF verification case" in report_text
    assert "Limitations and review notice" in report_text
    assert "conclusive proof" in report_text
    pdf.close()

    reports = client.get(
        f"/reports/investigation/{investigation['id']}"
    ).json()
    assert len(reports) == 1
    assert reports[0]["format"] == "pdf"