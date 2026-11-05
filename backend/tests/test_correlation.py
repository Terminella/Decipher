"""
Tests for the contextual-analysis module (Department 3).

Run from the backend/ folder with either:
    python -m pytest tests/test_correlation.py
    python tests/test_correlation.py          (no pytest needed)

No real LLM or internet is used: the LLM tests talk to a tiny fake OpenAI-compatible server on localhost.
"""
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import llm_service  # noqa: E402
from app.services.contextual_schemas import (  # noqa: E402
    AnomalyType, EvidenceType, FindingClass, ObservationStatus, Severity,
)
from app.services.correlation import run_contextual_analysis  # noqa: E402
from app.services.llm_service import LLMSettings  # noqa: E402


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def box(x0, y0, x1, y1):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def fld(fid, label, ftype, value, conf=None, bbox=None, page=1):
    return {"field_id": fid, "label": label, "field_type": ftype, "value": value,
            "ocr_confidence": conf, "bbox": bbox, "page": page}


def doc(did, name, fields, anomalies=None):
    return {"document_id": did, "filename": name, "fields": fields, "visual_anomalies": anomalies or []}


def inv(*docs, inv_id="INV-1"):
    return {"investigation_id": inv_id, "documents": list(docs)}


def run(*docs, **kw):
    return run_contextual_analysis(inv(*docs), use_llm=False, **kw)


def of_type(result, anomaly_type):
    return [f for f in result.findings if f.anomaly_type == anomaly_type]


# --------------------------------------------------------------------------------------
# cross-document behaviour
# --------------------------------------------------------------------------------------
def test_dob_digit_change_with_visual_overlap_is_high_and_potential_manipulation():
    a = doc("A", "form.pdf", [fld("a1", "Date of Birth", "date", "12/03/1990", 0.96, box(100, 140, 200, 160))])
    b = doc("B", "id.pdf", [fld("b1", "DOB", "date", "12/03/1991", 0.95, box(50, 120, 150, 140))],
            [{"anomaly_id": "v1", "kind": "ela_hotspot", "page": 1, "score": 0.8, "bbox": box(45, 115, 160, 145)}])
    f = of_type(run(a, b), AnomalyType.DATE_MISMATCH)[0]
    assert f.classification == FindingClass.SUSPICIOUS_ALTERATION
    assert f.severity == Severity.HIGH
    assert f.observation_status == ObservationStatus.POTENTIAL_MANIPULATION
    visual = [e for e in f.evidence if e.evidence_type == EvidenceType.VISUAL_ANOMALY]
    assert visual and visual[0].bbox.x0 == 45 and visual[0].anomaly_id == "v1"
    assert "12/03/1990" in f.explanation and "12/03/1991" in f.explanation
    assert "not proof" in f.explanation


def test_same_digit_change_without_visual_evidence_is_only_medium():
    a = doc("A", "form.pdf", [fld("a1", "Date of Birth", "date", "12/03/1990", 0.96)])
    b = doc("B", "id.pdf", [fld("b1", "DOB", "date", "12/03/1991", 0.95)])
    f = of_type(run(a, b), AnomalyType.DATE_MISMATCH)[0]
    assert f.classification == FindingClass.SUSPICIOUS_ALTERATION
    assert f.severity == Severity.MEDIUM


def test_benign_format_variations_produce_no_findings():
    a = doc("A", "form.pdf", [
        fld("a1", "Name of Applicant", "name", "Rahul Kumar Sharma", 0.97),
        fld("a2", "Date of Birth", "date", "12/03/1990", 0.96),
        fld("a3", "Aadhaar No", "id_number", "5678 9012 3456", 0.95),
        fld("a4", "Annual Income", "amount", "Rs. 5,40,000", 0.95),
        fld("a5", "Address", "address", "12 M.G. Road, Bhopal - 462001", 0.93),
        fld("a6", "PAN", "id_number", "ABCDE1234F", 0.98),
    ])
    b = doc("B", "slip.pdf", [
        fld("b1", "Name", "name", "SHARMA RAHUL KUMAR", 0.96),
        fld("b2", "DOB", "date", "12-Mar-1990", 0.95),
        fld("b3", "Aadhaar No", "id_number", "XXXX XXXX 3456", 0.9),
        fld("b4", "Net Pay (monthly)", "amount", "45,000", 0.97),
        fld("b5", "Address", "address", "12 MG Rd, Bhopal 462001", 0.91),
        fld("b6", "PAN", "id_number", "abcde 1234 f", 0.97),
    ])
    result = run(a, b)
    assert result.findings == [], [f.title for f in result.findings]


def test_initials_are_an_ordinary_inconsistency_not_an_alarm():
    a = doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Kumar Sharma", 0.97)])
    b = doc("B", "b.pdf", [fld("b1", "Name", "name", "Rahul K Sharma", 0.97)])
    f = of_type(run(a, b), AnomalyType.NAME_MISMATCH)[0]
    assert f.classification == FindingClass.ORDINARY_INCONSISTENCY
    assert f.severity == Severity.INFO


def test_lookalike_with_low_ocr_confidence_is_an_extraction_error():
    a = doc("A", "a.pdf", [fld("a1", "PAN", "id_number", "ABCDE1234F", 0.98)])
    b = doc("B", "b.pdf", [fld("b1", "PAN", "id_number", "ABCDE1Z34F", 0.62)])
    result = run(a, b)
    mism = of_type(result, AnomalyType.IDENTIFIER_MISMATCH)[0]
    assert mism.classification == FindingClass.EXTRACTION_ERROR
    assert mism.severity == Severity.LOW
    fmt = of_type(result, AnomalyType.INVALID_IDENTIFIER_FORMAT)[0]
    assert fmt.classification == FindingClass.EXTRACTION_ERROR and "read as '2'" in " ".join(fmt.reasoning)
    assert all(f.severity in (Severity.LOW, Severity.INFO) for f in result.findings)


def test_low_ocr_confidence_alone_downgrades_a_mismatch_to_extraction_error():
    clear = run(doc("A", "a.pdf", [fld("a1", "Date of Birth", "date", "12/03/1990", 0.96)]),
                doc("B", "b.pdf", [fld("b1", "DOB", "date", "17/08/1985", 0.95)]))
    assert of_type(clear, AnomalyType.DATE_MISMATCH)[0].severity == Severity.HIGH
    blurry = run(doc("A", "a.pdf", [fld("a1", "Date of Birth", "date", "12/03/1990", 0.96)]),
                 doc("B", "b.pdf", [fld("b1", "DOB", "date", "17/08/1985", 0.45)]))
    f = of_type(blurry, AnomalyType.DATE_MISMATCH)[0]
    assert f.classification == FindingClass.EXTRACTION_ERROR and f.severity == Severity.LOW
    assert f.confidence < 0.5


def test_same_lookalike_with_confident_ocr_stays_suspicious():
    a = doc("A", "a.pdf", [fld("a1", "PAN", "id_number", "ABCDE1234F", 0.98)])
    b = doc("B", "b.pdf", [fld("b1", "PAN", "id_number", "ABCDE1Z34F", 0.97)])
    mism = of_type(run(a, b), AnomalyType.IDENTIFIER_MISMATCH)[0]
    assert mism.classification == FindingClass.SUSPICIOUS_ALTERATION
    assert mism.severity == Severity.MEDIUM


def test_substantive_name_mismatch_is_high_and_explanation_is_grounded_and_not_accusatory():
    a = doc("A", "application.pdf", [fld("a1", "Name of Applicant", "name", "Rahul Sharma", 0.96)])
    b = doc("B", "id_card.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96)])
    f = of_type(run(a, b), AnomalyType.NAME_MISMATCH)[0]
    assert f.classification == FindingClass.INVESTIGATION_INDICATOR and f.severity == Severity.HIGH
    assert "Rahul Sharma" in f.explanation and "Amit Verma" in f.explanation
    assert "application.pdf" in f.explanation and "id_card.pdf" in f.explanation
    assert not llm_service._BANNED.search(f.explanation)
    assert f.observation_status == ObservationStatus.DETECTED_INCONSISTENCY   # no visual evidence: not "manipulation"


def test_same_pan_with_different_names_is_escalated():
    a = doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.96), fld("a2", "PAN", "id_number", "ABCDE1234F", 0.98)])
    b = doc("B", "b.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96), fld("b2", "PAN", "id_number", "ABCDE1234F", 0.98)])
    f = of_type(run(a, b), AnomalyType.NAME_MISMATCH)[0]
    assert any("matches in both documents although" in r for r in f.reasoning)
    assert f.priority_score >= 90


def test_several_identity_fields_disagreeing_escalate_each_other():
    a = doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.96), fld("a2", "DOB", "date", "12/03/1990", 0.96),
                           fld("a3", "PAN", "id_number", "ABCDE1234F", 0.98)])
    b = doc("B", "b.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96), fld("b2", "DOB", "date", "01/09/1985", 0.96),
                           fld("b3", "PAN", "id_number", "PQRST9876L", 0.98)])
    result = run(a, b)
    for t in (AnomalyType.NAME_MISMATCH, AnomalyType.DATE_MISMATCH, AnomalyType.IDENTIFIER_MISMATCH):
        f = of_type(result, t)[0]
        assert f.severity == Severity.HIGH
        assert any("Other identity fields also differ" in r for r in f.reasoning)


def test_monthly_vs_annual_income_is_consistent_but_a_real_gap_is_flagged():
    annual = fld("a1", "Annual Income", "amount", "5,40,000", 0.95)
    ok = run(doc("A", "a.pdf", [annual]), doc("B", "b.pdf", [fld("b1", "Net Pay (monthly)", "amount", "45,000", 0.97)]))
    assert of_type(ok, AnomalyType.AMOUNT_MISMATCH) == []
    bad = run(doc("A", "a.pdf", [annual]), doc("B", "b.pdf", [fld("b1", "Net Pay (monthly)", "amount", "85,000", 0.97)]))
    assert of_type(bad, AnomalyType.AMOUNT_MISMATCH)[0].severity in (Severity.MEDIUM, Severity.HIGH)


def test_extra_zero_in_an_amount_is_caught():
    a = doc("A", "a.pdf", [fld("a1", "Loan Amount", "amount", "Rs. 1,50,000", 0.97)])
    b = doc("B", "b.pdf", [fld("b1", "Loan Amount Requested", "amount", "Rs. 15,00,000", 0.97)])
    f = of_type(run(a, b), AnomalyType.AMOUNT_MISMATCH)[0]
    assert f.severity == Severity.HIGH and f.classification == FindingClass.SUSPICIOUS_ALTERATION


def test_permanent_and_current_addresses_are_not_compared_but_generic_address_is():
    perm = doc("A", "a.pdf", [fld("a1", "Permanent Address", "address", "45 Park Street, Kolkata 700016")])
    cur = doc("B", "b.pdf", [fld("b1", "Present Address", "address", "12 MG Road, Bhopal 462001")])
    assert of_type(run(perm, cur), AnomalyType.ADDRESS_MISMATCH) == []
    generic = doc("C", "c.pdf", [fld("c1", "Address", "address", "99 Lake View, Pune 411001")])
    assert of_type(run(cur, generic), AnomalyType.ADDRESS_MISMATCH)


def test_unknown_labels_are_only_compared_with_identical_labels():
    a = doc("A", "a.pdf", [fld("a1", "Employee Code", "other", "E-100"), fld("a2", "Zone", "other", "North")])
    b = doc("B", "b.pdf", [fld("b1", "Employee Code", "other", "E-200"), fld("b2", "Grade", "other", "South")])
    found = of_type(run(a, b), AnomalyType.FIELD_MISMATCH)
    assert len(found) == 1 and "E-100" in found[0].explanation


# --------------------------------------------------------------------------------------
# within-document behaviour
# --------------------------------------------------------------------------------------
def test_father_mother_employer_and_bank_names_are_not_mistaken_for_conflicts():
    result = run(doc("A", "x.pdf", [
        fld("a1", "Name", "name", "Rahul Sharma", 0.96),
        fld("a2", "Father's Name", "name", "Mahesh Sharma", 0.96),
        fld("a3", "Mother's Name", "name", "Sunita Sharma", 0.96),
        fld("a4", "Employer Name", "name", "Acme Steel Ltd", 0.96),
        fld("a5", "Bank Name", "name", "State Bank", 0.96),
        fld("a6", "Nominee Name", "name", "Priya Sharma", 0.96),
    ]))
    assert result.findings == [], [f.title for f in result.findings]


def test_fathers_name_is_compared_with_fathers_name_across_documents():
    a = doc("A", "a.pdf", [fld("a1", "Father's Name", "name", "Mahesh Sharma", 0.96)])
    b = doc("B", "b.pdf", [fld("b1", "Name of Father", "name", "Mukesh Verma", 0.96)])
    f = of_type(run(a, b), AnomalyType.NAME_MISMATCH)[0]
    assert f.field_name == "father's name" and "Mahesh Sharma" in f.explanation


def test_amount_in_words_must_agree_with_figures():
    bad = run(doc("A", "cheque.pdf", [fld("a1", "Amount", "amount", "1,50,000", 0.97),
                                      fld("a2", "Amount in Words", "amount", "Rupees One Lakh Five Thousand Only", 0.9)]))
    f = of_type(bad, AnomalyType.AMOUNT_WORDS_MISMATCH)[0]
    assert f.severity in (Severity.MEDIUM, Severity.HIGH) and "1,50,000" in f.explanation
    good = run(doc("A", "cheque.pdf", [fld("a1", "Amount", "amount", "1,50,000", 0.97),
                                       fld("a2", "Amount in Words", "amount", "Rupees One Lakh Fifty Thousand Only", 0.9)]))
    assert good.findings == []


def test_implausible_dates_are_flagged():
    result = run(doc("A", "x.pdf", [fld("a1", "Date of Birth", "date", "01/01/2090", 0.95),
                                    fld("a2", "Date of Issue", "date", "01/01/2024", 0.95),
                                    fld("a3", "Valid up to", "date", "01/01/2020", 0.95)]))
    found = of_type(result, AnomalyType.IMPLAUSIBLE_DATE)
    assert len(found) >= 2 and found[0].severity == Severity.HIGH
    assert any("after the expiry date" in " ".join(f.reasoning) for f in found)


def test_missing_value_is_a_low_extraction_error():
    result = run(doc("A", "x.pdf", [fld("a1", "PAN", "id_number", "N/A", 0.5)]))
    f = of_type(result, AnomalyType.MISSING_OR_UNREADABLE_VALUE)[0]
    assert f.classification == FindingClass.EXTRACTION_ERROR and f.severity == Severity.LOW


def test_conflicting_duplicates_in_one_document():
    result = run(doc("A", "x.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.95),
                                    fld("a2", "Account Holder Name", "name", "Rohit Verma", 0.95)]))
    f = of_type(result, AnomalyType.CONFLICTING_VALUES_IN_DOCUMENT)[0]
    assert f.severity == Severity.HIGH and "Rahul Sharma" in f.explanation and "Rohit Verma" in f.explanation


def test_visual_anomaly_on_a_critical_field_with_consistent_text_gets_its_own_finding():
    a = doc("A", "a.pdf", [fld("a1", "Date of Birth", "date", "12/03/1990", 0.96, box(100, 140, 200, 160))])
    b = doc("B", "b.pdf", [fld("b1", "DOB", "date", "12/03/1990", 0.95, box(50, 120, 150, 140))],
            [{"anomaly_id": "v9", "kind": "font_inconsistency", "page": 1, "score": 0.9, "bbox": box(45, 115, 160, 145)}])
    result = run(a, b)
    assert of_type(result, AnomalyType.DATE_MISMATCH) == []
    f = of_type(result, AnomalyType.VISUAL_ANOMALY_ON_CRITICAL_FIELD)[0]
    assert f.observation_status == ObservationStatus.OBSERVED_VISUAL
    assert f.severity in (Severity.LOW, Severity.MEDIUM)          # never more than the evidence supports
    assert any(e.anomaly_id == "v9" and e.bbox is not None for e in f.evidence)


# --------------------------------------------------------------------------------------
# contract / robustness
# --------------------------------------------------------------------------------------
def test_bounding_boxes_pass_through_and_finding_ids_are_stable():
    a = doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.96, box(10.5, 20.5, 110.5, 40.5))])
    b = doc("B", "b.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96, [5, 6, 105, 26])])
    r1, r2 = run(a, b), run(a, b)
    assert [f.finding_id for f in r1.findings] == [f.finding_id for f in r2.findings]
    boxes = [e.bbox for e in r1.findings[0].evidence if e.evidence_type == EvidenceType.EXTRACTED_FIELD]
    assert (boxes[0].x0, boxes[0].y0, boxes[0].x1, boxes[0].y1) == (10.5, 20.5, 110.5, 40.5)
    assert (boxes[1].x0, boxes[1].y1) == (5, 26)
    assert r1.findings[0].evidence[0].field_id == "a1" and r1.findings[0].document_ids == ["A", "B"]


def test_int_ids_percent_confidence_and_odd_field_types_are_accepted():
    payload = {"investigation_id": 7, "documents": [
        {"document_id": 1, "fields": [{"field_id": 11, "label": "Name", "field_type": "PERSON",
                                       "value": "Rahul Sharma", "ocr_confidence": 97}]},
        {"document_id": 2, "fields": [{"field_id": 21, "label": "Name", "field_type": "full_name",
                                       "value": "Amit Verma", "ocr_confidence": 96}]}]}
    result = run_contextual_analysis(payload, use_llm=False)
    f = of_type(result, AnomalyType.NAME_MISMATCH)[0]
    assert result.investigation_id == "7" and f.evidence[0].ocr_confidence == 0.97 and f.evidence[0].field_id == "11"
    assert json.dumps(result.model_dump(mode="json"))                    # fully JSON-serialisable for the backend


def test_single_document_reports_the_limitation_and_never_crashes():
    result = run(doc("A", "x.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.95)]))
    assert any("Only one document" in n for n in result.limitations)
    assert run_contextual_analysis({"investigation_id": "empty", "documents": []}, use_llm=False).findings == []


def test_no_template_explanation_ever_uses_accusatory_wording():
    a = doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.96), fld("a2", "DOB", "date", "12/03/1990", 0.96),
                           fld("a3", "PAN", "id_number", "ABCDE1234F", 0.98)])
    b = doc("B", "b.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96), fld("b2", "DOB", "date", "12/03/1991", 0.96),
                           fld("b3", "PAN", "id_number", "ABCDE1Z34F", 0.6)])
    result = run(a, b)
    assert result.findings
    for f in result.findings:
        assert f.explanation and f.explanation_source == "template"
        assert not llm_service._BANNED.search(f.explanation), f.explanation


# --------------------------------------------------------------------------------------
# LLM layer (fake OpenAI-compatible server on localhost - no real API, no quota)
# --------------------------------------------------------------------------------------
class FakeLLM:
    def __init__(self, responder):
        self.requests = 0
        self.bodies = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                outer.requests += 1
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                outer.bodies.append(body)
                status, payload, headers = responder(body)
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"


def _good_answer(body):
    findings = json.loads(body["messages"][1]["content"])["findings"]
    items = []
    for f in findings:
        quoted = " and ".join(f"'{x['value']}'" for x in f["facts"])
        items.append({"id": f["id"], "text": f"The {f['field']} shows up as {quoted}, which may be worth checking "
                                             "against the original documents."})
    return 200, {"choices": [{"message": {"content": json.dumps({"explanations": items})}}]}, {}


def _name_clash():
    return inv(doc("A", "a.pdf", [fld("a1", "Name", "name", "Rahul Sharma", 0.96)]),
               doc("B", "b.pdf", [fld("b1", "Name", "name", "Amit Verma", 0.96)]))


def test_llm_explanations_are_used_validated_and_cached():
    with FakeLLM(_good_answer) as fake, tempfile.TemporaryDirectory() as tmp:
        settings = LLMSettings(model="test-model", base_url=fake.url, cache_dir=Path(tmp), max_retries=0)
        first = run_contextual_analysis(_name_clash(), llm_settings=settings)
        f = first.findings[0]
        assert first.llm_used and first.llm_model == "test-model" and f.explanation_source == "llm"
        assert "'Rahul Sharma'" in f.explanation and f.explanation.endswith("either document is false.")
        assert fake.requests == 1
        second = run_contextual_analysis(_name_clash(), llm_settings=settings)      # same findings -> served from cache
        assert fake.requests == 1 and second.findings[0].explanation_source == "llm"


def test_only_structured_findings_are_sent_to_the_llm():
    with FakeLLM(_good_answer) as fake:
        settings = LLMSettings(model="m", base_url=fake.url, cache_dir=None, max_retries=0)
        run_contextual_analysis(_name_clash(), llm_settings=settings)
        sent = json.dumps(fake.bodies[0])
        assert "Rahul Sharma" in sent and "findings" in sent and "bbox" not in sent


def test_rate_limit_falls_back_to_templates_without_crashing():
    original = llm_service._sleep
    llm_service._sleep = lambda seconds: None
    try:
        with FakeLLM(lambda body: (429, {"error": "quota"}, {})) as fake:
            settings = LLMSettings(model="m", base_url=fake.url, cache_dir=None, max_retries=2)
            result = run_contextual_analysis(_name_clash(), llm_settings=settings)
            assert fake.requests == 3                                   # first try + 2 polite retries
        assert not result.llm_used and all(f.explanation_source == "template" for f in result.findings)
        assert any("rate limit" in n for n in result.limitations)
        assert result.findings[0].explanation
        with FakeLLM(lambda body: (429, {"error": "quota"}, {"Retry-After": "3600"})) as fake:
            settings = LLMSettings(model="m", base_url=fake.url, cache_dir=None, max_retries=2)
            run_contextual_analysis(_name_clash(), llm_settings=settings)
            assert fake.requests == 1                                   # quota window too long: do not wait
    finally:
        llm_service._sleep = original


def test_ungrounded_or_accusatory_llm_text_is_rejected():
    def bad(body):
        findings = json.loads(body["messages"][1]["content"])["findings"]
        items = [{"id": f["id"], "text": "This document is clearly forged and the applicant committed fraud."}
                 for f in findings]
        return 200, {"choices": [{"message": {"content": json.dumps({"explanations": items})}}]}, {}

    def vague(body):
        findings = json.loads(body["messages"][1]["content"])["findings"]
        items = [{"id": f["id"], "text": "The two documents disagree about this particular field, so a closer look "
                                         "may be useful."} for f in findings]
        return 200, {"choices": [{"message": {"content": json.dumps({"explanations": items})}}]}, {}

    def accusatory_but_grounded(body):
        findings = json.loads(body["messages"][1]["content"])["findings"]
        items = [{"id": f["id"], "text": "'Rahul Sharma' versus 'Amit Verma' proves this is a forged identity document."}
                 for f in findings]
        return 200, {"choices": [{"message": {"content": json.dumps({"explanations": items})}}]}, {}

    for responder in (bad, vague, accusatory_but_grounded):
        with FakeLLM(responder) as fake:
            settings = LLMSettings(model="m", base_url=fake.url, cache_dir=None, max_retries=0)
            result = run_contextual_analysis(_name_clash(), llm_settings=settings)
        assert not result.llm_used and result.findings[0].explanation_source == "template"
        assert "Rahul Sharma" in result.findings[0].explanation
        assert any("grounding/safety check" in n for n in result.limitations)


def test_no_llm_configured_means_templates_and_an_honest_note():
    result = run_contextual_analysis(_name_clash(), llm_settings=LLMSettings(model="", cache_dir=None))
    assert not result.llm_used and result.findings[0].explanation_source == "template"
    assert any("No LLM is configured" in n for n in result.limitations)


def test_provider_without_json_mode_is_retried_and_fenced_json_is_accepted():
    def picky(body):
        if "response_format" in body:
            return 400, {"error": "unsupported parameter"}, {}
        status, payload, headers = _good_answer(body)
        content = payload["choices"][0]["message"]["content"]
        payload["choices"][0]["message"]["content"] = "```json\n" + content + "\n```"
        return status, payload, headers

    with FakeLLM(picky) as fake:
        settings = LLMSettings(model="m", base_url=fake.url, cache_dir=None, max_retries=0)
        result = run_contextual_analysis(_name_clash(), llm_settings=settings)
        assert fake.requests == 2 and result.llm_used and result.findings[0].explanation_source == "llm"


def test_unreachable_endpoint_falls_back_quickly():
    original = llm_service._sleep
    llm_service._sleep = lambda seconds: None
    try:
        settings = LLMSettings(model="m", base_url="http://127.0.0.1:9/v1", cache_dir=None, max_retries=1, timeout=2)
        result = run_contextual_analysis(_name_clash(), llm_settings=settings)
    finally:
        llm_service._sleep = original
    assert not result.llm_used and result.findings[0].explanation_source == "template"
    assert any("could not reach" in n for n in result.limitations)


# --------------------------------------------------------------------------------------
if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                import traceback
                print("FAIL", name, "->", repr(exc))
                traceback.print_exc()
    print(f"\n{'ALL TESTS PASSED' if not failed else str(failed) + ' TEST(S) FAILED'}")
    sys.exit(1 if failed else 0)
