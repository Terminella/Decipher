import hashlib
import json

import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    AIAnalysisRun,
    AIEvidenceLink,
    AIFinding,
    AIInvestigation,
    AIInvestigationDocument,
)
from app.services import ai_analysis


def _analysis_fixture(tmp_path, monkeypatch, outputs, cancel_on_first=False):
    database_path = tmp_path / "ai-analysis.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    upload_dir = tmp_path / "uploads"
    document_dir = upload_dir / "ai-1"
    document_dir.mkdir(parents=True)
    document_path = document_dir / "source.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Invoice total: INR 1000")
    pdf.save(document_path)
    pdf.close()
    digest = hashlib.sha256(document_path.read_bytes()).hexdigest()

    monkeypatch.setattr(ai_analysis.settings, "upload_dir", upload_dir)

    with factory() as db:
        investigation = AIInvestigation(
            title="Evidence review",
            selected_model="test-model",
            status="queued",
        )
        db.add(investigation)
        db.flush()
        document = AIInvestigationDocument(
            ai_investigation_id=investigation.id,
            filename="source.pdf",
            sha256=digest,
            storage_path=str(document_path.resolve()),
            source_type="ai_upload",
            processing_status="uploaded",
        )
        db.add(document)
        db.flush()
        run = AIAnalysisRun(
            ai_investigation_id=investigation.id,
            status="queued",
            model_name="test-model",
            prompt_version=ai_analysis.PROMPT_VERSION,
            configuration_json=json.dumps({
                "document_ids": [document.id],
                "standard_finding_ids": [],
                "objective": None,
                "custom_instructions": None,
                "analysis_depth": "standard",
                "options": {
                    "cross_document_analysis": True,
                    "entity_resolution": True,
                    "timeline_analysis": True,
                    "financial_correlation": True,
                },
            }),
            result_json="{}",
        )
        db.add(run)
        db.commit()
        run_id = run.id
        evidence_id = f"doc-{document.id}-page-1-text-1"

    class FakeOllamaClient:
        def __init__(self):
            self.index = 0

        def chat_json(self, _model, _system, _payload):
            response = outputs[self.index]
            self.index += 1
            if cancel_on_first and self.index == 1:
                with factory() as cancel_db:
                    cancel_run = cancel_db.get(AIAnalysisRun, run_id)
                    cancel_run.cancel_requested = True
                    cancel_db.commit()
            return response

    monkeypatch.setattr(ai_analysis, "OllamaClient", FakeOllamaClient)
    return engine, factory, run_id, evidence_id


def _outputs(evidence_id, quote="Invoice total: INR 1000"):
    citation = {
        "evidence_id": evidence_id,
        "page_number": 1,
        "quote": quote,
    }
    return [
        {"observations": [{"fact": "Invoice total is INR 1000"}]},
        {"entities": [], "relationships": []},
        {"comparisons": [], "contradictions": []},
        {
            "claims": [{
                "claim": "The invoice records a total of INR 1000.",
                "evidence": [citation],
            }],
            "alternative_explanations": [],
            "disagreements": [],
        },
        {"claims": [{
            "claim": "The invoice records a total of INR 1000.",
            "evidence": [citation],
        }]},
        {"findings": [{
            "title": "Invoice amount recorded",
            "category": "financial",
            "severity": "low",
            "confidence": 0.81,
            "description": "The page shows an invoice total of INR 1000.",
            "reasoning": "This is a direct transcription of the source.",
            "alternative_explanations": [],
            "recommended_action": "Compare against the purchase order.",
            "evidence": [citation],
        }]},
    ]


def test_ai_analysis_persists_only_source_verified_findings(
    tmp_path,
    monkeypatch,
):
    engine, factory, run_id, evidence_id = _analysis_fixture(
        tmp_path,
        monkeypatch,
        _outputs("pending"),
    )

    class OrderedClient:
        def __init__(self):
            self.index = 0

        def chat_json(self, *_args):
            response = _outputs(evidence_id)[self.index]
            self.index += 1
            return response

    monkeypatch.setattr(ai_analysis, "OllamaClient", OrderedClient)

    ai_analysis.execute_ai_analysis(run_id, factory)

    with factory() as db:
        run = db.get(AIAnalysisRun, run_id)
        findings = db.query(AIFinding).filter_by(analysis_run_id=run_id).all()
        links = db.query(AIEvidenceLink).filter_by(
            ai_finding_id=findings[0].id
        ).all()
        assert run.status == "completed"
        assert run.progress == 100
        assert json.loads(run.result_json)["evidence_retrieval"]["sha256_verified"]
        assert len(findings) == 1
        assert findings[0].confidence == 0.81
        assert len(links) == 1
        assert links[0].verification_status == "verified"
        assert links[0].quoted_text == "Invoice total: INR 1000"
    engine.dispose()


def test_ai_analysis_rejects_unverifiable_finding_quotes(tmp_path, monkeypatch):
    outputs = _outputs("pending", quote="Invented amount: INR 9000")
    engine, factory, run_id, evidence_id = _analysis_fixture(
        tmp_path,
        monkeypatch,
        outputs,
    )

    class OrderedClient:
        def __init__(self):
            self.index = 0

        def chat_json(self, *_args):
            response = outputs[self.index]
            self.index += 1
            return response

    monkeypatch.setattr(ai_analysis, "OllamaClient", OrderedClient)

    ai_analysis.execute_ai_analysis(run_id, factory)

    with factory() as db:
        run = db.get(AIAnalysisRun, run_id)
        assert run.status == "completed"
        assert db.query(AIFinding).filter_by(analysis_run_id=run_id).count() == 0
        result = json.loads(run.result_json)
        assert result["structured_findings"]["rejected_count"] == 1
        assert evidence_id
    engine.dispose()


def test_ai_analysis_cancellation_keeps_completed_stage_results(
    tmp_path,
    monkeypatch,
):
    engine, factory, run_id, evidence_id = _analysis_fixture(
        tmp_path,
        monkeypatch,
        _outputs(evidence_id="unused"),
        cancel_on_first=True,
    )

    ai_analysis.execute_ai_analysis(run_id, factory)

    with factory() as db:
        run = db.get(AIAnalysisRun, run_id)
        assert run.status == "cancelled"
        assert run.progress > 0
        result = json.loads(run.result_json)
        assert result["individual_document_analysis"]["documents"]
        assert "entity_relationship_analysis" not in result
    engine.dispose()


def test_quick_ai_analysis_uses_one_bounded_inference_and_saves_verified_findings(
    tmp_path,
    monkeypatch,
):
    engine, factory, run_id, evidence_id = _analysis_fixture(
        tmp_path,
        monkeypatch,
        _outputs(evidence_id="unused"),
    )
    with factory() as db:
        run = db.get(AIAnalysisRun, run_id)
        configuration = json.loads(run.configuration_json)
        configuration["analysis_depth"] = "quick"
        run.configuration_json = json.dumps(configuration)
        db.commit()

    calls = []

    class QuickClient:
        def chat_json(
            self,
            _model,
            system,
            payload,
            **options,
        ):
            calls.append((system, payload, options))
            response = _outputs(evidence_id)[-1]
            citation = response["findings"][0]["evidence"][0]
            response["findings"][0]["evidence"] = [
                f"{citation['evidence_id']}: '{citation['quote']}'"
            ]
            return response

    monkeypatch.setattr(ai_analysis, "OllamaClient", QuickClient)
    monkeypatch.setattr(ai_analysis.settings, "ollama_quick_timeout", "90")
    monkeypatch.setattr(ai_analysis.settings, "ollama_quick_context_window", "4096")
    monkeypatch.setattr(ai_analysis.settings, "ollama_quick_max_output_tokens", "384")

    ai_analysis.execute_ai_analysis(run_id, factory)

    with factory() as db:
        run = db.get(AIAnalysisRun, run_id)
        findings = db.query(AIFinding).filter_by(analysis_run_id=run_id).all()
        result = json.loads(run.result_json)
        assert run.status == "completed"
        assert run.progress == 100
        assert len(findings) == 1
        assert result["structured_findings"]["accepted_count"] == 1
        assert result["quick_source_analysis"]["model_response"]["findings"]
        assert len(calls) == 1
        system, payload, options = calls[0]
        assert payload["mode"] == "quick"
        assert 'field name "confidence"' in system
        assert "array of objects containing" in system
        assert options == {
            "timeout": 90.0,
            "context_window": 4096,
            "max_output_tokens": 384,
            "think": False,
        }
        assert all(
            len(document_evidence) <= 6
            for document_evidence in [
                [
                    item for item in payload["evidence"]
                    if item["document_id"] == document["document_id"]
                ]
                for document in payload["documents"]
            ]
        )
    engine.dispose()
