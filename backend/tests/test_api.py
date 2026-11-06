import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.classifier import classify_document


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