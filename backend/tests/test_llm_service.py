import json
import urllib.error
from pathlib import Path

import pytest

from app.services import llm_service
from app.services.contextual_schemas import (
    AnomalyType,
    EvidenceRef,
    EvidenceType,
    Finding,
    FindingClass,
    ObservationStatus,
    Severity,
)


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def make_finding(
    finding_id="F001",
    value="Rahul Sharma",
    classification=FindingClass.INVESTIGATION_INDICATOR,
    severity=Severity.HIGH,
):
    evidence = [
        EvidenceRef(
            evidence_type=EvidenceType.EXTRACTED_FIELD,
            document_id="DOC001",
            page=1,
            field_id="FIELD001",
            label="Applicant Name",
            value=value,
            ocr_confidence=0.98,
        ),
        EvidenceRef(
            evidence_type=EvidenceType.EXTRACTED_FIELD,
            document_id="DOC002",
            page=1,
            field_id="FIELD002",
            label="Applicant Name",
            value="Rahul Verma",
            ocr_confidence=0.97,
        ),
    ]

    return Finding(
        finding_id=finding_id,
        anomaly_type=AnomalyType.NAME_MISMATCH,
        classification=classification,
        observation_status=ObservationStatus.DETECTED_INCONSISTENCY,
        severity=severity,
        priority_score=90,
        title="Applicant name mismatch",
        field_name="applicant name",
        reasoning=["The extracted names differ between documents."],
        evidence=evidence,
        document_ids=["DOC001", "DOC002"],
    )


def make_settings(tmp_path, **kwargs):
    defaults = {
        "model": "test-model",
        "base_url": "http://localhost:11434/v1",
        "api_key": "",
        "enabled": True,
        "timeout": 10,
        "max_retries": 2,
        "max_findings": 12,
        "cache_dir": tmp_path / "cache",
    }
    defaults.update(kwargs)

    return llm_service.LLMSettings(**defaults)


# ---------------------------------------------------------
# SETTINGS TESTS
# ---------------------------------------------------------

def test_default_settings():
    settings = llm_service.LLMSettings()

    assert settings.model == ""
    assert settings.enabled is True
    assert settings.timeout == 60.0
    assert settings.max_retries == 2
    assert settings.max_findings == 12


def test_settings_configured_when_model_exists():
    settings = llm_service.LLMSettings(model="test-model")

    assert settings.configured is True


def test_settings_not_configured_without_model():
    settings = llm_service.LLMSettings(model="")

    assert settings.configured is False


def test_settings_not_configured_with_whitespace_model():
    settings = llm_service.LLMSettings(model="   ")

    assert settings.configured is False


def test_from_env_reads_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TIMEOUT", "30")
    monkeypatch.setenv("LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("LLM_MAX_FINDINGS", "8")
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))

    settings = llm_service.LLMSettings.from_env()

    assert settings.model == "gemini-test"
    assert settings.base_url == "https://example.com/v1"
    assert settings.api_key == "test-key"
    assert settings.timeout == 30.0
    assert settings.max_retries == 4
    assert settings.max_findings == 8
    assert settings.cache_dir == tmp_path


@pytest.mark.parametrize(
    "value",
    ["false", "0", "no", "off"],
)
def test_from_env_can_disable_llm(monkeypatch, value):
    monkeypatch.setenv("LLM_ENABLED", value)

    settings = llm_service.LLMSettings.from_env()

    assert settings.enabled is False


def test_from_env_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("LLM_ENABLED", raising=False)

    settings = llm_service.LLMSettings.from_env()

    assert settings.enabled is True


def test_from_env_handles_invalid_numbers(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT", "invalid")
    monkeypatch.setenv("LLM_MAX_RETRIES", "invalid")

    settings = llm_service.LLMSettings.from_env()

    assert settings.timeout == 60.0
    assert settings.max_retries == 2


# ---------------------------------------------------------
# TEMPLATE EXPLANATION TESTS
# ---------------------------------------------------------

def test_template_explanation_contains_extracted_values():
    finding = make_finding()

    explanation = llm_service.template_explanation(
        finding,
        {"DOC001": "Application.pdf", "DOC002": "Identity.pdf"},
    )

    assert "Rahul Sharma" in explanation
    assert "Rahul Verma" in explanation


def test_template_explanation_contains_document_names():
    finding = make_finding()

    explanation = llm_service.template_explanation(
        finding,
        {"DOC001": "Application.pdf", "DOC002": "Identity.pdf"},
    )

    assert "Application.pdf" in explanation
    assert "Identity.pdf" in explanation


def test_template_explanation_contains_page_numbers():
    finding = make_finding()

    explanation = llm_service.template_explanation(finding, {})

    assert "page 1" in explanation


@pytest.mark.parametrize(
    "classification",
    [
        FindingClass.ORDINARY_INCONSISTENCY,
        FindingClass.EXTRACTION_ERROR,
        FindingClass.SUSPICIOUS_ALTERATION,
        FindingClass.INVESTIGATION_INDICATOR,
    ],
)
def test_template_explanation_supports_all_classifications(classification):
    finding = make_finding(classification=classification)

    explanation = llm_service.template_explanation(finding, {})

    assert explanation
    assert len(explanation) > 30


def test_template_explanation_handles_empty_values():
    finding = make_finding(value="")

    explanation = llm_service.template_explanation(finding, {})

    assert "empty value" in explanation


# ---------------------------------------------------------
# PROMPT GENERATION TESTS
# ---------------------------------------------------------

def test_build_user_prompt_returns_json():
    finding = make_finding()

    prompt = llm_service._build_user_prompt(
        [finding],
        {"DOC001": "Application.pdf"},
    )

    data = json.loads(prompt)

    assert "findings" in data
    assert len(data["findings"]) == 1


def test_build_user_prompt_contains_finding_id():
    finding = make_finding(finding_id="TEST123")

    prompt = llm_service._build_user_prompt([finding], {})

    assert "TEST123" in prompt


def test_build_user_prompt_contains_extracted_values():
    finding = make_finding()

    prompt = llm_service._build_user_prompt([finding], {})

    assert "Rahul Sharma" in prompt
    assert "Rahul Verma" in prompt


def test_build_user_prompt_uses_document_labels():
    finding = make_finding()

    prompt = llm_service._build_user_prompt(
        [finding],
        {"DOC001": "Application.pdf"},
    )

    assert "Application.pdf" in prompt


# ---------------------------------------------------------
# RESPONSE PARSING TESTS
# ---------------------------------------------------------

def test_parse_valid_json_response():
    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    })

    result = llm_service._parse_explanations(content)

    assert "F001" in result
    assert "Rahul Sharma" in result["F001"]


def test_parse_response_inside_markdown_code_block():
    content = """```json
    {
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    }
    ```"""

    result = llm_service._parse_explanations(content)

    assert "F001" in result


def test_parse_response_accepts_explanation_key():
    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "explanation": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    })

    result = llm_service._parse_explanations(content)

    assert "F001" in result


def test_parse_invalid_json_raises_error():
    with pytest.raises(llm_service.LLMUnavailable):
        llm_service._parse_explanations("not valid json")


def test_parse_missing_explanations_raises_error():
    content = json.dumps({"result": "something"})

    with pytest.raises(llm_service.LLMUnavailable):
        llm_service._parse_explanations(content)


def test_parse_response_without_json_raises_error():
    with pytest.raises(llm_service.LLMUnavailable):
        llm_service._parse_explanations("No JSON was returned")


def test_parse_ignores_invalid_entries():
    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            },
            "invalid entry",
            {
                "id": 123,
                "text": "Invalid ID"
            },
        ]
    })

    result = llm_service._parse_explanations(content)

    assert list(result.keys()) == ["F001"]


# ---------------------------------------------------------
# LLM RESPONSE VALIDATION TESTS
# ---------------------------------------------------------

def test_validate_accepts_grounded_explanation():
    finding = make_finding()

    explanation = (
        "The applicant name Rahul Sharma differs from Rahul Verma "
        "across the submitted documents and is worth checking."
    )

    assert llm_service._validate(explanation, finding) is None


def test_validate_rejects_short_explanation():
    finding = make_finding()

    result = llm_service._validate("Too short", finding)

    assert result == "length out of range"


def test_validate_rejects_long_explanation():
    finding = make_finding()

    explanation = "Rahul Sharma " * 100

    result = llm_service._validate(explanation, finding)

    assert result == "length out of range"


@pytest.mark.parametrize(
    "word",
    ["fraud", "forged", "fake", "counterfeit", "criminal", "illegal", "falsified"],
)
def test_validate_rejects_accusatory_wording(word):
    finding = make_finding()

    explanation = (
        f"The applicant name Rahul Sharma differs between documents. "
        f"This document appears {word} and needs further review."
    )

    result = llm_service._validate(explanation, finding)

    assert result == "accusatory wording"


def test_validate_rejects_missing_extracted_value():
    finding = make_finding()

    explanation = (
        "The applicant name differs between the submitted documents "
        "and should be reviewed by a human investigator."
    )

    result = llm_service._validate(explanation, finding)

    assert result is not None
    assert "does not quote" in result


# ---------------------------------------------------------
# RETRY DELAY TESTS
# ---------------------------------------------------------

def test_retry_delay_uses_retry_after_header():
    error = urllib.error.HTTPError(
        "url",
        429,
        "Rate limited",
        {"Retry-After": "5"},
        None,
    )

    assert llm_service._retry_delay(error, 0) == 5.0


def test_retry_delay_uses_exponential_backoff():
    error = urllib.error.HTTPError(
        "url",
        500,
        "Server error",
        {},
        None,
    )

    assert llm_service._retry_delay(error, 0) == 1.0
    assert llm_service._retry_delay(error, 1) == 2.0


def test_retry_delay_ignores_very_long_retry_after():
    error = urllib.error.HTTPError(
        "url",
        429,
        "Rate limited",
        {"Retry-After": "60"},
        None,
    )

    assert llm_service._retry_delay(error, 0) is None


# ---------------------------------------------------------
# CHAT REQUEST TESTS
# ---------------------------------------------------------

def test_chat_sends_correct_request(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "choices": [
                    {
                        "message": {
                            "content": '{"explanations": []}'
                        }
                    }
                ]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        llm_service.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    settings = make_settings(
        tmp_path,
        api_key="test-api-key",
        timeout=15,
    )

    result = llm_service._chat(settings, "system prompt", "user prompt")

    assert result == '{"explanations": []}'
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["timeout"] == 15
    assert captured["headers"]["Authorization"] == "Bearer test-api-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["temperature"] == 0.2


def test_chat_retries_without_json_mode(monkeypatch, tmp_path):
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "choices": [
                    {"message": {"content": '{"explanations": []}'}}
                ]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        calls.append(body)

        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Unsupported response format",
                {},
                None,
            )

        return FakeResponse()

    monkeypatch.setattr(
        llm_service.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    settings = make_settings(tmp_path)

    llm_service._chat(settings, "system", "user")

    assert len(calls) == 2
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_chat_raises_unavailable_for_http_rejection(monkeypatch, tmp_path):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            None,
        )

    monkeypatch.setattr(
        llm_service.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(llm_service.LLMUnavailable):
        llm_service._chat(
            make_settings(tmp_path),
            "system",
            "user",
        )


def test_chat_retries_server_error(monkeypatch, tmp_path):
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({
                "choices": [
                    {"message": {"content": "success"}}
                ]
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls["count"] += 1

        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                "Server error",
                {},
                None,
            )

        return FakeResponse()

    monkeypatch.setattr(
        llm_service.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    monkeypatch.setattr(llm_service, "_sleep", lambda seconds: None)

    result = llm_service._chat(
        make_settings(tmp_path),
        "system",
        "user",
    )

    assert result == "success"
    assert calls["count"] == 2


# ---------------------------------------------------------
# CACHE TESTS
# ---------------------------------------------------------

def test_cached_explanations_saves_response(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)

    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    })

    calls = {"count": 0}

    def fake_chat(settings, system, user):
        calls["count"] += 1
        return content

    monkeypatch.setattr(llm_service, "_chat", fake_chat)

    first = llm_service._cached_explanations(
        settings,
        "system",
        "user",
    )

    second = llm_service._cached_explanations(
        settings,
        "system",
        "user",
    )

    assert first == second
    assert calls["count"] == 1


def test_cached_explanations_creates_cache_file(monkeypatch, tmp_path):
    settings = make_settings(tmp_path)

    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    })

    monkeypatch.setattr(
        llm_service,
        "_chat",
        lambda *args: content,
    )

    llm_service._cached_explanations(
        settings,
        "system",
        "user",
    )

    assert settings.cache_dir.exists()
    assert len(list(settings.cache_dir.glob("*.json"))) == 1


def test_cached_explanations_without_cache_directory(monkeypatch, tmp_path):
    settings = make_settings(tmp_path, cache_dir=None)

    content = json.dumps({
        "explanations": [
            {
                "id": "F001",
                "text": "The applicant name Rahul Sharma differs between the submitted documents."
            }
        ]
    })

    monkeypatch.setattr(
        llm_service,
        "_chat",
        lambda *args: content,
    )

    result = llm_service._cached_explanations(
        settings,
        "system",
        "user",
    )

    assert "F001" in result


# ---------------------------------------------------------
# PUBLIC FUNCTION TESTS
# ---------------------------------------------------------

def test_explain_findings_with_llm_disabled():
    finding = make_finding()

    report = llm_service.explain_findings(
        [finding],
        {},
        use_llm=False,
    )

    assert report.llm_used is False
    assert finding.explanation_source == "template"
    assert finding.explanation


def test_explain_findings_with_empty_list():
    report = llm_service.explain_findings(
        [],
        {},
        use_llm=True,
    )

    assert report.llm_used is False


def test_explain_findings_without_model_uses_template(tmp_path):
    finding = make_finding()

    settings = make_settings(tmp_path, model="")

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=settings,
    )

    assert report.llm_used is False
    assert finding.explanation_source == "template"
    assert any("No LLM is configured" in note for note in report.notes)


def test_explain_findings_when_disabled_uses_template(tmp_path):
    finding = make_finding()

    settings = make_settings(tmp_path, enabled=False)

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=settings,
    )

    assert report.llm_used is False
    assert finding.explanation_source == "template"


def test_explain_findings_uses_valid_llm_response(monkeypatch, tmp_path):
    finding = make_finding()

    explanation = (
        "The applicant name Rahul Sharma differs from Rahul Verma "
        "across the submitted documents and is worth checking."
    )

    monkeypatch.setattr(
        llm_service,
        "_cached_explanations",
        lambda *args: {"F001": explanation},
    )

    settings = make_settings(tmp_path)

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=settings,
    )

    assert report.llm_used is True
    assert report.model == "test-model"
    assert finding.explanation_source == "llm"
    assert explanation in finding.explanation


def test_explain_findings_rejects_unsafe_llm_response(monkeypatch, tmp_path):
    finding = make_finding()

    unsafe = (
        "The applicant name Rahul Sharma differs from Rahul Verma. "
        "This document is clearly fraudulent and requires review."
    )

    monkeypatch.setattr(
        llm_service,
        "_cached_explanations",
        lambda *args: {"F001": unsafe},
    )

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=make_settings(tmp_path),
    )

    assert report.llm_used is False
    assert finding.explanation_source == "template"
    assert any("failed the grounding/safety check" in note for note in report.notes)


def test_explain_findings_falls_back_when_llm_unavailable(monkeypatch, tmp_path):
    finding = make_finding()

    def fail(*args):
        raise llm_service.LLMUnavailable("test failure")

    monkeypatch.setattr(
        llm_service,
        "_cached_explanations",
        fail,
    )

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=make_settings(tmp_path),
    )

    assert report.llm_used is False
    assert finding.explanation_source == "template"
    assert any("unavailable" in note for note in report.notes)


def test_explain_findings_skips_info_severity(monkeypatch, tmp_path):
    finding = make_finding(severity=Severity.INFO)

    calls = {"count": 0}

    def fake_cached(*args):
        calls["count"] += 1
        return {}

    monkeypatch.setattr(
        llm_service,
        "_cached_explanations",
        fake_cached,
    )

    report = llm_service.explain_findings(
        [finding],
        {},
        settings=make_settings(tmp_path),
    )

    assert calls["count"] == 0
    assert report.llm_used is False
    assert finding.explanation_source == "template"


def test_explain_findings_respects_max_findings(monkeypatch, tmp_path):
    findings = [
        make_finding(finding_id=f"F{i}")
        for i in range(5)
    ]

    captured = {}

    def fake_cached(settings, system, user):
        captured["payload"] = json.loads(user)
        return {}

    monkeypatch.setattr(
        llm_service,
        "_cached_explanations",
        fake_cached,
    )

    settings = make_settings(tmp_path, max_findings=2)

    report = llm_service.explain_findings(
        findings,
        {},
        settings=settings,
    )

    assert len(captured["payload"]["findings"]) == 2
    assert any("highest-priority" in note for note in report.notes)
    assert report.llm_used is False
