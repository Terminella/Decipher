"""
Explanations for contextual findings (Department 3).

Design goals (learned the hard way: free LLM quotas run out):
  1. Every finding ALWAYS gets a deterministic, evidence-grounded template explanation, so the whole
     system works with no LLM, no internet and no API quota.
  2. If an LLM is configured, ONE batched call per investigation asks it to rewrite the explanations in
     natural language. The call is cached on disk (same findings -> no new request, no new quota used),
     retried politely on rate limits, and never allowed to break the pipeline.
  3. The LLM's answer is validated per finding: it must quote the real extracted values and must not use
     accusatory wording. Anything that fails is replaced by the template text.
  4. Only structured findings are sent to the model (never whole documents).
     NOTE: with a hosted API, extracted values (names, ID numbers) leave the machine. Use a local model
     for anything that is not authorised sample data.

Configuration (environment variables, all optional)
    LLM_MODEL         model name. If unset -> template-only mode, no network calls at all.
    LLM_BASE_URL      OpenAI-compatible base URL (default http://localhost:11434/v1 = local Ollama).
                      Ollama, OpenAI, Gemini, Groq and OpenRouter all offer an OpenAI-compatible endpoint;
                      take the URL from the provider's docs.
    LLM_API_KEY       API key (not needed for a local model).
    LLM_ENABLED       "false" forces template-only mode.
    LLM_TIMEOUT       seconds per request (default 60).
    LLM_MAX_RETRIES   retries on rate-limit / server / network errors (default 2).
    LLM_MAX_FINDINGS  max findings sent to the model per investigation (default 12, highest priority first).
    LLM_CACHE_DIR     cache folder (default backend/generated/llm_cache).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .contextual_schemas import AnomalyType, EvidenceRef, EvidenceType, Finding, FindingClass, Severity

log = logging.getLogger(__name__)
_sleep = time.sleep                      # replaced in tests so retries do not really wait

_DEFAULT_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "generated" / "llm_cache"


class LLMUnavailable(Exception):
    """The LLM could not be used (unreachable, quota exhausted, unusable answer). Callers fall back to templates."""


@dataclass(frozen=True)
class LLMSettings:
    model: str = ""
    base_url: str = _DEFAULT_BASE_URL
    api_key: str = ""
    enabled: bool = True
    timeout: float = 60.0
    max_retries: int = 2
    max_findings: int = 12
    cache_dir: Optional[Path] = _DEFAULT_CACHE

    @property
    def configured(self) -> bool:
        return bool(self.model.strip())

    @classmethod
    def from_env(cls) -> "LLMSettings":
        env = os.environ

        def num(name: str, default, cast):
            try:
                return cast(env.get(name, default))
            except (TypeError, ValueError):
                return default

        cache = env.get("LLM_CACHE_DIR")
        return cls(
            model=env.get("LLM_MODEL", "").strip(),
            base_url=(env.get("LLM_BASE_URL") or _DEFAULT_BASE_URL).strip(),
            api_key=env.get("LLM_API_KEY", "").strip(),
            enabled=env.get("LLM_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"},
            timeout=num("LLM_TIMEOUT", 60.0, float),
            max_retries=num("LLM_MAX_RETRIES", 2, int),
            max_findings=num("LLM_MAX_FINDINGS", 12, int),
            cache_dir=Path(cache) if cache else _DEFAULT_CACHE,
        )


@dataclass
class ExplainReport:
    llm_used: bool = False
    model: Optional[str] = None
    notes: list[str] = field(default_factory=list)      # surfaced in the dossier's limitations section


# --------------------------------------------------------------------------------------
# Template explanations (always available, always grounded in the extracted values)
# --------------------------------------------------------------------------------------
_QUALIFIER = {
    FindingClass.ORDINARY_INCONSISTENCY:
        "This is recorded for completeness; differences of this kind are usually benign.",
    FindingClass.EXTRACTION_ERROR:
        "Please re-check the highlighted text against the original image before treating this as a real difference.",
    FindingClass.SUSPICIOUS_ALTERATION:
        "This is an automated indicator for human review, not proof of manipulation.",
    FindingClass.INVESTIGATION_INDICATOR:
        "This is an automated indicator that needs human verification; it does not by itself establish that "
        "either document is false.",
}
_CROSS_TYPES = {
    AnomalyType.NAME_MISMATCH, AnomalyType.DATE_MISMATCH, AnomalyType.AMOUNT_MISMATCH,
    AnomalyType.ADDRESS_MISMATCH, AnomalyType.IDENTIFIER_MISMATCH, AnomalyType.FIELD_MISMATCH,
}


def _where(ev: EvidenceRef, labels: dict[str, str]) -> str:
    return f"{labels.get(ev.document_id, ev.document_id)} (page {ev.page})"


def _q(value: Optional[str]) -> str:
    return f"'{value}'" if value else "an empty value"


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _observation(f: Finding, fields: list[EvidenceRef], visuals: list[EvidenceRef], labels: dict[str, str]) -> str:
    name = f.field_name or "value"
    t = f.anomaly_type
    if t in _CROSS_TYPES and len(fields) >= 2:
        a, b = fields[0], fields[1]
        return f"The {name} reads {_q(a.value)} in {_where(a, labels)} but {_q(b.value)} in {_where(b, labels)}."
    if t == AnomalyType.CONFLICTING_VALUES_IN_DOCUMENT and len(fields) >= 2:
        a, b = fields[0], fields[1]
        return f"The {name} appears more than once in {_where(a, labels)} with different values: {_q(a.value)} and {_q(b.value)}."
    if t == AnomalyType.MISSING_OR_UNREADABLE_VALUE and fields:
        e = fields[0]
        return (f"The field '{e.label or name}' was detected in {_where(e, labels)} "
                f"but no readable value was extracted (value: {_q(e.value)}).")
    if t == AnomalyType.INVALID_IDENTIFIER_FORMAT and fields:
        e = fields[0]
        return f"The {name} {_q(e.value)} in {_where(e, labels)} does not match the expected format."
    if t == AnomalyType.IMPLAUSIBLE_DATE and fields:
        vals = "; ".join(f"{e.label or 'date'} = {_q(e.value)}" for e in fields)
        return f"The dates in {_where(fields[0], labels)} ({vals}) are not plausible together."
    if t == AnomalyType.AMOUNT_WORDS_MISMATCH and len(fields) >= 2:
        a, b = fields[0], fields[1]
        return (f"In {_where(a, labels)} the amount in figures ({_q(a.value)}) and the amount in words "
                f"({_q(b.value)}) do not agree.")
    if t == AnomalyType.VISUAL_ANOMALY_ON_CRITICAL_FIELD and fields and visuals:
        v, e = visuals[0], fields[0]
        return (f"Visual analysis flagged a '{v.label}' region in {_where(v, labels)} that overlaps the "
                f"{name} {_q(e.value)}.")
    return _sentence(f.title)


def template_explanation(f: Finding, labels: dict[str, str]) -> str:
    fields = [e for e in f.evidence if e.evidence_type == EvidenceType.EXTRACTED_FIELD]
    visuals = [e for e in f.evidence if e.evidence_type == EvidenceType.VISUAL_ANOMALY]
    parts = [_observation(f, fields, visuals, labels)]
    if f.anomaly_type != AnomalyType.VISUAL_ANOMALY_ON_CRITICAL_FIELD and f.reasoning:
        parts.append(_sentence("Detail: " + f.reasoning[0]))
    if len(f.reasoning) > 1 and f.reasoning[-1].startswith("Classified"):
        parts.append(_sentence(f.reasoning[-1]))
    parts.append(_QUALIFIER[f.classification])
    return " ".join(p for p in parts if p)


# --------------------------------------------------------------------------------------
# LLM call (OpenAI-compatible chat/completions, stdlib only)
# --------------------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "You help a human reviewer understand findings produced by a rule-based document verification engine. "
    "For each finding write a short, neutral explanation.\n"
    "Rules:\n"
    "1. Use ONLY the facts given in the finding. Quote every value listed in `facts` exactly as given.\n"
    "2. Say what differs, in which document and page, and why a reviewer may want to look at it.\n"
    "3. Never say or imply that a document is fraudulent, forged, fake, counterfeit or illegal. "
    "Use cautious wording such as 'may', 'could' or 'is worth checking'.\n"
    "4. If OCR confidence is low or the difference looks like an OCR confusion, say it may be an extraction error.\n"
    "5. If visual evidence is listed, mention it only as supporting context.\n"
    "6. At most 3 sentences, plain text, no markdown, no bullet points.\n"
    'Return ONLY a JSON object: {"explanations": [{"id": "<finding id>", "text": "<explanation>"}]} '
    "with exactly one entry per finding."
)

_BANNED = re.compile(
    r"\b(fraud\w*|forg(?:ed|ery|eries)|fake\w*|counterfeit\w*|criminal\w*|illegal\w*|falsif\w+|fabricat\w+)\b",
    re.IGNORECASE,
)


def _build_user_prompt(targets: list[Finding], labels: dict[str, str]) -> str:
    items = []
    for f in targets:
        facts = [
            {"document": labels.get(e.document_id, e.document_id), "page": e.page, "label": e.label,
             "value": e.value, "ocr_confidence": e.ocr_confidence}
            for e in f.evidence if e.evidence_type == EvidenceType.EXTRACTED_FIELD
        ]
        visual = [
            {"document": labels.get(e.document_id, e.document_id), "page": e.page, "kind": e.label, "note": e.note}
            for e in f.evidence if e.evidence_type == EvidenceType.VISUAL_ANOMALY
        ]
        items.append({
            "id": f.finding_id, "type": f.anomaly_type.value, "classification": f.classification.value,
            "severity": f.severity.value, "field": f.field_name, "facts": facts,
            "visual_evidence": visual, "engine_notes": f.reasoning[:6],
        })
    return json.dumps({"findings": items}, ensure_ascii=False)


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> Optional[float]:
    """Seconds to wait before retrying, or None when waiting is pointless (quota window too long)."""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            seconds = float(retry_after)
        except ValueError:
            return float(min(2 ** attempt, 8))
        return seconds if seconds <= 20 else None
    return float(min(2 ** attempt, 8))


def _chat(settings: LLMSettings, system: str, user: str) -> str:
    url = settings.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    payload = {
        "model": settings.model,
        "temperature": 0.2,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    json_mode, attempt = True, 0
    while True:
        body = dict(payload)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=settings.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422) and json_mode:
                json_mode = False                  # this provider does not support response_format: retry without it
                continue
            if exc.code == 429 or exc.code >= 500:
                delay = _retry_delay(exc, attempt)
                if attempt >= settings.max_retries or delay is None:
                    raise LLMUnavailable("rate limit or quota exhausted" if exc.code == 429
                                         else f"server error {exc.code}")
                _sleep(delay)
                attempt += 1
                continue
            raise LLMUnavailable(f"request rejected (HTTP {exc.code})")
        except (urllib.error.URLError, OSError) as exc:        # includes timeouts and refused connections
            if attempt >= settings.max_retries:
                raise LLMUnavailable(f"could not reach the model endpoint ({type(exc).__name__})")
            _sleep(float(min(2 ** attempt, 8)))
            attempt += 1
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMUnavailable("unexpected response format from the model endpoint")


def _parse_explanations(content: str) -> dict[str, str]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMUnavailable("the model did not return JSON")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        raise LLMUnavailable("the model returned invalid JSON")
    items = data.get("explanations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise LLMUnavailable("the model's JSON had no 'explanations' list")
    out: dict[str, str] = {}
    for it in items:
        if isinstance(it, dict):
            fid, txt = it.get("id"), it.get("text") or it.get("explanation")
            if isinstance(fid, str) and isinstance(txt, str):
                out[fid] = txt
    return out


def _cached_explanations(settings: LLMSettings, system: str, user: str) -> dict[str, str]:
    """Same findings + same model => answered from disk, so repeated demos never burn API quota."""
    key = hashlib.sha256("\x1f".join([settings.model, system, user]).encode("utf-8")).hexdigest()
    path = settings.cache_dir / f"{key}.json" if settings.cache_dir else None
    if path is not None and path.exists():
        try:
            return _parse_explanations(json.loads(path.read_text(encoding="utf-8"))["content"])
        except (OSError, ValueError, KeyError, LLMUnavailable):
            pass                                              # unusable cache entry: ask the model again
    content = _chat(settings, system, user)
    parsed = _parse_explanations(content)                     # only cache answers that parse
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"content": content}), encoding="utf-8")
        except OSError:
            log.warning("Could not write LLM cache entry to %s", path)
    return parsed


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _validate(text: str, f: Finding) -> Optional[str]:
    """Return a reason string when the LLM text must be rejected, else None."""
    if not isinstance(text, str) or not (30 <= len(text.strip()) <= 900):
        return "length out of range"
    if _BANNED.search(text):
        return "accusatory wording"
    body = _norm(text)
    for e in f.evidence:
        if e.evidence_type != EvidenceType.EXTRACTED_FIELD or not e.value or len(e.value) > 60:
            continue
        needle = _norm(e.value)
        if needle and needle not in body:
            return f"does not quote the extracted value {e.value!r}"
    return None


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------
def explain_findings(
    findings: list[Finding],
    doc_labels: dict[str, str],
    *,
    use_llm: bool = True,
    settings: Optional[LLMSettings] = None,
) -> ExplainReport:
    """Fill `explanation` / `explanation_source` on every finding (in place)."""
    report = ExplainReport()
    for f in findings:
        f.explanation = template_explanation(f, doc_labels)
        f.explanation_source = "template"
    if not findings or not use_llm:
        return report

    settings = settings or LLMSettings.from_env()
    if not settings.enabled:
        return report
    if not settings.configured:
        report.notes.append("No LLM is configured (set LLM_MODEL); rule-based template explanations were used.")
        return report

    candidates = [f for f in findings if f.severity != Severity.INFO]
    targets = candidates[: max(1, settings.max_findings)]
    if not targets:
        return report
    if len(candidates) > len(targets):
        report.notes.append(f"Only the {len(targets)} highest-priority findings were sent to the LLM; "
                            "the rest use template explanations.")
    try:
        answers = _cached_explanations(settings, _SYSTEM_PROMPT, _build_user_prompt(targets, doc_labels))
    except LLMUnavailable as exc:
        report.notes.append(f"LLM explanations were unavailable ({exc}); rule-based template explanations were used.")
        log.warning("LLM unavailable: %s", exc)
        return report

    accepted = rejected = 0
    for f in targets:
        text = answers.get(f.finding_id)
        problem = _validate(text, f) if text is not None else "missing from the answer"
        if problem:
            rejected += 1
            log.info("LLM explanation for %s rejected: %s", f.finding_id, problem)
            continue
        f.explanation = f"{text.strip()} {_QUALIFIER[f.classification]}"
        f.explanation_source = "llm"
        accepted += 1
    if accepted:
        report.llm_used, report.model = True, settings.model
    if rejected:
        report.notes.append(f"{rejected} LLM explanation(s) failed the grounding/safety check and were replaced "
                            "by template text.")
    return report
