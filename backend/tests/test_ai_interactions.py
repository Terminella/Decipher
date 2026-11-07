import json

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.routes import ai_interactions
from app.models import (
    AIAnalysisRun,
    AIEvidenceLink,
    AIFinding,
    AIInvestigation,
    AIInvestigationDocument,
)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'ai-interactions.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    from app.config import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "storage" / "uploads")
    monkeypatch.setattr(settings, "report_dir", tmp_path / "storage" / "reports")
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


def _pdf_bytes(text="Invoice total: INR 1000"):
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    data = pdf.tobytes()
    pdf.close()
    return data


def test_chat_retrieves_evidence_persists_history_and_filters_citations(
    api_client,
    monkeypatch,
):
    client, _ = api_client
    investigation = client.post(
        "/ai/investigations/",
        json={"title": "Chat case", "selected_model": "local-test"},
    ).json()
    upload = client.post(
        f"/ai/investigations/{investigation['id']}/documents/upload",
        files={"file": ("invoice.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 200

    monkeypatch.setattr(
        ai_interactions,
        "detect_environment",
        lambda: {
            "status": "available",
            "models": [{"name": "local-test"}],
            "error": None,
        },
    )

    evidence = {
        "evidence-1": {
            "evidence_id": "evidence-1",
            "filename": "invoice.pdf",
            "page_number": 1,
            "label": "Page text",
            "quote": "Invoice total: INR 1000",
        },
    }

    def fake_build_evidence(_db, _investigation, document_ids, _finding_ids):
        assert document_ids
        return evidence, evidence

    monkeypatch.setattr(ai_interactions, "_build_evidence", fake_build_evidence)

    class FakeOllamaClient:
        def chat_json(self, model, _system, user_payload):
            assert model == "local-test"
            assert user_payload["source_evidence"][0]["evidence_id"] == "evidence-1"
            return {
                "answer": "The invoice states INR 1000.",
                "citation_ids": ["evidence-1", "fabricated-id", []],
            }

    monkeypatch.setattr(ai_interactions, "OllamaClient", FakeOllamaClient)
    response = client.post(
        f"/ai/investigations/{investigation['id']}/chat",
        json={"message": "What is the invoice total?"},
    )

    assert response.status_code == 200
    messages = response.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["content"] == "The invoice states INR 1000."
    assert [item["evidence_id"] for item in messages[1]["citations"]] == ["evidence-1"]
    assert client.get(
        f"/ai/investigations/{investigation['id']}/chat"
    ).json() == messages


def test_human_review_history_and_ai_run_pdf_export(api_client):
    client, factory = api_client
    with factory() as db:
        investigation = AIInvestigation(
            title="Reviewed AI report",
            description="Check evidence and review trail.",
        )
        db.add(investigation)
        db.flush()
        document = AIInvestigationDocument(
            ai_investigation_id=investigation.id,
            filename="invoice.pdf",
            sha256="a" * 64,
            source_type="ai_upload",
            processing_status="uploaded",
        )
        db.add(document)
        db.flush()
        run = AIAnalysisRun(
            ai_investigation_id=investigation.id,
            status="completed",
            model_name="local-test",
            model_version="test",
            prompt_version="test-prompt",
            configuration_json="{}",
            result_json=json.dumps({
                "evidence_retrieval": {"sha256_verified": True},
            }),
        )
        db.add(run)
        db.flush()
        finding = AIFinding(
            analysis_run_id=run.id,
            finding_key="finding-1",
            title="Invoice total recorded",
            category="financial",
            severity="medium",
            confidence=0.82,
            description="The source records INR 1000.",
            reasoning="Directly transcribed from the source.",
            alternative_explanations_json='["A later credit may explain the difference."]',
            recommended_action="Compare to the payment record.",
        )
        db.add(finding)
        db.flush()
        db.add(AIEvidenceLink(
            ai_finding_id=finding.id,
            ai_document_id=document.id,
            source_type="document_text",
            page_number=1,
            quoted_text="Invoice total: INR 1000",
            verification_status="verified",
        ))
        db.commit()
        investigation_id = investigation.id
        run_id = run.id
        finding_id = finding.id

    review_response = client.post(
        f"/ai/investigations/{investigation_id}/findings/{finding_id}/reviews",
        json={
            "review_status": "accepted",
            "reviewer": "Case reviewer",
            "comment": "Matched to the source invoice.",
        },
    )
    assert review_response.status_code == 200
    review = review_response.json()
    assert review["review_status"] == "accepted"
    assert client.get(
        f"/ai/investigations/{investigation_id}/findings/{finding_id}/reviews"
    ).json() == [review]
    run_detail = client.get(
        f"/ai/investigations/{investigation_id}/analysis-runs/{run_id}"
    ).json()
    assert run_detail["findings"][0]["reviews"][0]["comment"] == (
        "Matched to the source invoice."
    )

    generated = client.post(
        f"/ai/investigations/{investigation_id}/analysis-runs/{run_id}/generate-pdf"
    )
    assert generated.status_code == 200
    report = generated.json()
    download = client.get(report["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].endswith(
        'filename="reviewed-ai-report-run-1-report-1.pdf"'
    )
    assert download.content.startswith(b"%PDF-")
    pdf = pymupdf.open(stream=download.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)
    assert "Invoice total: INR 1000" in text
    assert "Matched to the source invoice." in text
    assert "Contents" not in text
    assert "AI findings and source evidence" in text
    pdf.close()
    reports = client.get(
        f"/ai/investigations/{investigation_id}/reports"
    ).json()
    assert len(reports) == 1
    assert reports[0]["id"] == report["id"]


def test_only_completed_ai_runs_can_be_exported(api_client):
    client, factory = api_client
    with factory() as db:
        investigation = AIInvestigation(title="Incomplete report")
        db.add(investigation)
        db.flush()
        run = AIAnalysisRun(
            ai_investigation_id=investigation.id,
            status="running",
            configuration_json="{}",
            result_json="{}",
        )
        db.add(run)
        db.commit()
        investigation_id, run_id = investigation.id, run.id

    response = client.post(
        f"/ai/investigations/{investigation_id}/analysis-runs/{run_id}/generate-pdf"
    )
    assert response.status_code == 409
