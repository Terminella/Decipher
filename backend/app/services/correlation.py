"""
Contextual-analysis engine (Department 3).

    from app.services.correlation import run_contextual_analysis
    result = run_contextual_analysis(investigation_input)      # InvestigationInput or a plain dict
    for finding in result.findings: ...                         # sorted, highest priority first

What it does (all deterministic - the LLM only phrases the explanations afterwards)
  1. Works out what every extracted field MEANS (person name, date of birth, PAN, income, ...).
  2. Inside each document: conflicting duplicates, missing values, invalid ID formats, implausible dates,
     amount in figures vs amount in words.
  3. Across documents: compares the same concept in every pair of documents (names, dates, amounts, addresses,
     identifiers) while tolerating benign variation (initials, date formats, masked IDs, monthly vs annual income).
  4. Correlates with the visual-forensics output: an anomalous region overlapping a field raises a finding;
     low OCR confidence or look-alike characters lower it (probable extraction error).
  5. Classifies every finding (ordinary / extraction error / suspicious alteration / investigation indicator),
     scores severity and attaches evidence references that carry the original bounding boxes.
  6. Hands the findings to llm_service for evidence-grounded explanations (template fallback, never fails).

Severity score (0..1) = criticality(field) x weight(relation)  [+ visual corroboration] [+ identity escalation]
    HIGH >= 0.65, MEDIUM >= 0.40, LOW >= 0.20, otherwise INFO.
    Ordinary differences and probable extraction errors are capped at LOW: a finding never looks scarier than
    the evidence supports, and nothing is ever labelled "fraud" - only indicators for human review.
"""
from __future__ import annotations

import hashlib
import itertools
import logging
import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timezone
from typing import Optional

from . import llm_service
from .contextual_schemas import (
    AnomalyType, ContextualAnalysisResult, DocumentInput, EvidenceRef, EvidenceType, ExtractedField, Finding,
    FindingClass, InvestigationInput, ObservationStatus, Severity, VisualAnomaly,
)
from .normalization import (
    CONSISTENT, RELATION_RANK, Comparison, Concept, Kind, Relation, check_identifier_format, compare_amounts,
    compare_values, display_normalized, infer_concept, is_blank_value, label_text, parse_amount, parse_date,
)

log = logging.getLogger(__name__)

ENGINE_VERSION = "1.0.0"

# --- tunable thresholds ---------------------------------------------------------------
OCR_LOW = 0.75              # below this, an OCR read is considered unreliable
OCR_HIGH = 0.90             # at/above this, an OCR read is considered confident
SEV_HIGH, SEV_MEDIUM, SEV_LOW = 0.65, 0.40, 0.20
OVERLAP_MIN = 0.20          # share of a field's box that must be covered by an anomaly box to count
MIN_VISUAL_STRENGTH = 0.30  # weaker visual hints are ignored
DEFAULT_VISUAL_SCORE = 0.60 # used when the visual detector gives no score
CRITICAL_FIELD = 0.80       # criticality at/above which a visual anomaly alone is worth a finding
MAX_VISUAL_EVIDENCE = 3
MAX_VISUAL_ONLY_FINDINGS = 10

_WEIGHT = {Relation.COMPATIBLE: 0.12, Relation.TYPO: 0.45, Relation.DIFFERENT: 1.0}
_VISUAL_WEIGHT = 0.35
_BOOST_MULTI_IDENTITY = 0.15
_BOOST_ID_MATCHES = 0.10
_CAP_ORDINARY = 0.30
_CAP_EXTRACTION = 0.35
_CAP_VISUAL_ONLY = 0.55

_CLASS_LABEL = {
    FindingClass.ORDINARY_INCONSISTENCY: "an ordinary inconsistency",
    FindingClass.EXTRACTION_ERROR: "a likely extraction error",
    FindingClass.SUSPICIOUS_ALTERATION: "a suspicious alteration",
    FindingClass.INVESTIGATION_INDICATOR: "an indicator requiring investigation",
}
_RECOMMENDED_REVIEW = {
    FindingClass.ORDINARY_INCONSISTENCY: "No action is normally needed; note the variation for the record.",
    FindingClass.EXTRACTION_ERROR: "Re-read the highlighted text from the original image (or re-run OCR) before "
                                   "treating this as a real difference.",
    FindingClass.SUSPICIOUS_ALTERATION: "Inspect the highlighted region(s) on the original document and request a "
                                        "verified copy from the issuer if the difference is confirmed.",
    FindingClass.INVESTIGATION_INDICATOR: "Escalate for manual review: confirm the correct value with the applicant "
                                          "or the issuing authority.",
}
_ANOMALY_FOR_KIND = {
    Kind.NAME: AnomalyType.NAME_MISMATCH, Kind.DATE: AnomalyType.DATE_MISMATCH,
    Kind.AMOUNT: AnomalyType.AMOUNT_MISMATCH, Kind.ADDRESS: AnomalyType.ADDRESS_MISMATCH,
    Kind.IDENTIFIER: AnomalyType.IDENTIFIER_MISMATCH, Kind.TEXT: AnomalyType.FIELD_MISMATCH,
}


# Scoring profile for "figures vs words" - a classic tampering spot, so it counts as a critical comparison.
_C_WORDS_VS_FIGURES = Concept("amount_words_vs_figures", Kind.AMOUNT, "amount", 0.9, unique=False, best_match=False)


def _today() -> date:
    return date.today()


# --------------------------------------------------------------------------------------
# Internal working types
# --------------------------------------------------------------------------------------
@dataclass
class _F:
    """A field together with its document and inferred meaning."""
    doc: DocumentInput
    f: ExtractedField
    concept: Concept


@dataclass
class _Hit:
    """A visual anomaly that overlaps a field."""
    field_id: str
    doc: DocumentInput
    page: int
    anomaly: VisualAnomaly
    ratio: float
    strength: float


@dataclass
class _Mismatch:
    anomaly_type: AnomalyType
    concept: Concept
    fields: list[_F]
    comparison: Comparison
    scope: str                                              # "cross" | "within"
    force_class: Optional[FindingClass] = None
    force_reason: Optional[str] = None
    notes: list[str] = dc_field(default_factory=list)       # extra reasoning lines (identity escalation, ...)
    boost: float = 0.0


@dataclass
class _Assessment:
    classification: FindingClass
    severity: Severity
    score: float
    status: ObservationStatus
    confidence: Optional[float]
    reasoning: list[str]
    hits: list[_Hit]


@dataclass
class _Stats:
    uncomparable: int = 0


def _doc_name(doc: DocumentInput) -> str:
    return doc.filename or doc.document_id


def _severity(score: float) -> Severity:
    if score >= SEV_HIGH:
        return Severity.HIGH
    if score >= SEV_MEDIUM:
        return Severity.MEDIUM
    if score >= SEV_LOW:
        return Severity.LOW
    return Severity.INFO


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


# --------------------------------------------------------------------------------------
# Visual-forensics correlation
# --------------------------------------------------------------------------------------
def _visual_hits(fd: _F) -> list[_Hit]:
    hits: list[_Hit] = []
    for an in fd.doc.visual_anomalies:
        if an.page is not None and an.page != fd.f.page:
            continue
        base = an.score if an.score is not None else DEFAULT_VISUAL_SCORE
        if an.bbox is not None:
            if fd.f.bbox is None:
                continue
            ratio = fd.f.bbox.overlap_ratio(an.bbox)
            if ratio < OVERLAP_MIN:
                continue
            strength = base * (1.0 if ratio >= 0.5 else 0.75)
        else:
            ratio, strength = 0.0, base * 0.4                # document-level observation: weak, unlocalised support
        if strength >= MIN_VISUAL_STRENGTH:
            hits.append(_Hit(fd.f.field_id, fd.doc, fd.f.page, an, ratio, strength))
    return sorted(hits, key=lambda h: -h.strength)


def _collect_hits(fields: list[_F]) -> list[_Hit]:
    hits = [h for fd in fields for h in _visual_hits(fd)]
    return sorted(hits, key=lambda h: -h.strength)


def _visual_note(an: VisualAnomaly) -> str:
    text = an.description or an.kind
    return f"{text} (detector score {an.score:.2f})" if an.score is not None else text


# --------------------------------------------------------------------------------------
# Assessment: classification, severity, confidence, reasoning
# --------------------------------------------------------------------------------------
def _assess(m: _Mismatch) -> _Assessment:
    cmp, concept, rel = m.comparison, m.concept, m.comparison.relation
    real_diff = rel in (Relation.TYPO, Relation.DIFFERENT)
    confs = [x.f.ocr_confidence for x in m.fields if x.f.ocr_confidence is not None]
    min_conf = min(confs) if confs else None
    hits = _collect_hits(m.fields) if real_diff else []
    vis = hits[0].strength if hits else 0.0
    corroborated = bool(hits)
    uncertain = min_conf is not None and min_conf < OCR_LOW
    lookalike = cmp.ocr_confusable and (min_conf is None or min_conf < OCR_HIGH)

    # 1) classification ------------------------------------------------------------
    if m.force_class is not None:
        cls = m.force_class
        why = m.force_reason or "determined by the rule that raised this finding"
    elif rel == Relation.COMPATIBLE:
        cls = FindingClass.ORDINARY_INCONSISTENCY
        why = ("the values differ in completeness or presentation (for example initials, rounding or omitted parts) "
               "but do not contradict each other")
    elif corroborated:
        cls = FindingClass.SUSPICIOUS_ALTERATION if rel == Relation.TYPO else FindingClass.INVESTIGATION_INDICATOR
        kinds = ", ".join(sorted({h.anomaly.kind for h in hits[:MAX_VISUAL_EVIDENCE]}))
        why = f"visual analysis flagged a region overlapping the compared field ({kinds})"
    elif uncertain or lookalike:
        cls = FindingClass.EXTRACTION_ERROR
        bits = []
        if uncertain:
            bits.append(f"OCR confidence is low ({min_conf:.2f})")
        if lookalike:
            bits.append("the difference involves only characters that OCR engines commonly confuse")
        why = " and ".join(bits)
    elif rel == Relation.TYPO and concept.kind in (Kind.NAME, Kind.ADDRESS, Kind.TEXT):
        cls = FindingClass.ORDINARY_INCONSISTENCY
        why = "this is a small spelling or wording variation of the kind found in genuine documents"
    elif rel == Relation.TYPO:
        cls = FindingClass.SUSPICIOUS_ALTERATION
        why = ("a small change in a field where small edits matter, with OCR confidence high in both places"
               if min_conf is not None else
               "a small change in a field where small edits matter, and no OCR confidence is available to "
               "explain it as a reading error")
    else:
        cls = FindingClass.INVESTIGATION_INDICATOR
        why = m.force_reason or "the values are materially different in a field that should normally agree"

    # 2) score -> severity -----------------------------------------------------------
    weight = _WEIGHT.get(rel, 0.0)
    if real_diff and cmp.magnitude:
        weight = max(weight, min(1.0, cmp.magnitude * 1.5))   # a big relative change in an amount counts more
    score = concept.criticality * weight
    if real_diff:
        score += _VISUAL_WEIGHT * vis + m.boost
    if cls == FindingClass.ORDINARY_INCONSISTENCY:
        score = min(score, _CAP_ORDINARY)
    elif cls == FindingClass.EXTRACTION_ERROR:
        score = min(score, _CAP_EXTRACTION)
    score = max(0.0, min(1.0, score))

    # 3) confidence that the discrepancy is real (not an OCR artefact) -----------------
    base = min_conf if min_conf is not None else 0.7
    if cmp.ocr_confusable:
        base *= 0.7
    if hits:
        base = min(1.0, base + 0.1 * vis)
    confidence = round(min(base, 0.95), 2)               # OCR is never ground truth: never claim certainty

    status = (ObservationStatus.POTENTIAL_MANIPULATION
              if cls == FindingClass.SUSPICIOUS_ALTERATION
              or (cls == FindingClass.INVESTIGATION_INDICATOR and corroborated)
              else ObservationStatus.DETECTED_INCONSISTENCY)

    # 4) reasoning trail (what the engine actually saw) --------------------------------
    reasoning: list[str] = []
    if cmp.detail:
        reasoning.append(cmp.detail)
    if confs:
        reasoning.append("OCR confidence: " + ", ".join(
            f"{x.f.ocr_confidence:.2f} in {_doc_name(x.doc)}" for x in m.fields if x.f.ocr_confidence is not None) + ".")
    if cmp.ocr_confusable:
        reasoning.append("The difference consists only of characters that OCR engines commonly confuse "
                         "(for example O/0, 1/7, S/5).")
    for h in hits[:MAX_VISUAL_EVIDENCE]:
        score_txt = f"detector score {h.anomaly.score:.2f}" if h.anomaly.score is not None else "no detector score"
        where = "overlapping this field" if h.anomaly.bbox is not None else "document-level, not localised"
        reasoning.append(f"Visual analysis flagged '{h.anomaly.kind}' ({score_txt}), {where}, in {_doc_name(h.doc)}.")
    reasoning.extend(m.notes)
    reasoning.append(f"Classified as {_CLASS_LABEL[cls]}: {why}.")

    return _Assessment(cls, _severity(score), score, status, confidence, reasoning, hits)


# --------------------------------------------------------------------------------------
# Building findings
# --------------------------------------------------------------------------------------
def _finding_id(inv_id: str, anomaly_type: AnomalyType, keys: list[str]) -> str:
    raw = "|".join([inv_id, anomaly_type.value, *sorted(keys)])
    return "F-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _field_evidence(fd: _F) -> EvidenceRef:
    return EvidenceRef(
        evidence_type=EvidenceType.EXTRACTED_FIELD, document_id=fd.doc.document_id, page=fd.f.page,
        field_id=fd.f.field_id, label=fd.f.label or fd.concept.display, value=fd.f.value,
        normalized_value=display_normalized(fd.concept.kind, fd.f.value),
        ocr_confidence=fd.f.ocr_confidence, bbox=fd.f.bbox,
    )


def _visual_evidence(h: _Hit) -> EvidenceRef:
    return EvidenceRef(
        evidence_type=EvidenceType.VISUAL_ANOMALY, document_id=h.doc.document_id, page=h.page,
        anomaly_id=h.anomaly.anomaly_id, label=h.anomaly.kind, bbox=h.anomaly.bbox, note=_visual_note(h.anomaly),
    )


def _title(m: _Mismatch) -> str:
    t, name = m.anomaly_type, m.concept.display
    if t == AnomalyType.CONFLICTING_VALUES_IN_DOCUMENT:
        return f"{_cap(name)} appears with conflicting values in one document"
    if t == AnomalyType.MISSING_OR_UNREADABLE_VALUE:
        return f"No readable value for {name}"
    if t == AnomalyType.INVALID_IDENTIFIER_FORMAT:
        return f"{_cap(name)} does not match the expected format"
    if t == AnomalyType.IMPLAUSIBLE_DATE:
        return "Dates are not plausible together"
    if t == AnomalyType.AMOUNT_WORDS_MISMATCH:
        return "Amount in figures and amount in words disagree"
    rel = m.comparison.relation
    if rel == Relation.COMPATIBLE:
        return f"{_cap(name)} is written differently across documents"
    if rel == Relation.TYPO:
        return f"{_cap(name)} differs slightly between documents"
    return f"{_cap(name)} differs between documents"


def _unique(seq: list[str]) -> list[str]:
    return list(dict.fromkeys(seq))


def _to_finding(inv_id: str, m: _Mismatch, a: _Assessment) -> Finding:
    evidence = [_field_evidence(fd) for fd in m.fields]
    seen: set[str] = set()
    for h in a.hits:
        if h.anomaly.anomaly_id in seen:
            continue
        if len(seen) >= MAX_VISUAL_EVIDENCE:
            break
        seen.add(h.anomaly.anomaly_id)
        evidence.append(_visual_evidence(h))
    return Finding(
        finding_id=_finding_id(inv_id, m.anomaly_type, [fd.f.field_id for fd in m.fields]),
        anomaly_type=m.anomaly_type, classification=a.classification, observation_status=a.status,
        severity=a.severity, priority_score=round(a.score * 100), confidence=a.confidence,
        title=_title(m), field_name=m.concept.display, reasoning=a.reasoning,
        recommended_review=_RECOMMENDED_REVIEW[a.classification], evidence=evidence,
        document_ids=_unique([e.document_id for e in evidence]),
    )


# --------------------------------------------------------------------------------------
# Cross-document checks
# --------------------------------------------------------------------------------------
_ADDRESS_FAMILY = {"address", "address_current", "address_permanent"}


def _family(key: str) -> str:
    return "address*" if key in _ADDRESS_FAMILY else key


def _pair_allowed(ka: str, kb: str) -> bool:
    """A permanent address is never compared with a current address, but a generic 'Address' matches either."""
    return ka == kb or (ka in _ADDRESS_FAMILY and kb in _ADDRESS_FAMILY and "address" in (ka, kb))


def _compare(concept: Concept, x: _F, y: _F) -> Comparison:
    cmp = compare_values(concept.kind, x.f.value, y.f.value)
    if concept.key == "income" and cmp.relation in (Relation.TYPO, Relation.DIFFERENT):
        pa, pb = parse_amount(x.f.value), parse_amount(y.f.value)
        if pa and pb and pa.value > 0 and pb.value > 0:
            ratio = float(max(pa.value, pb.value) / min(pa.value, pb.value))
            if abs(ratio - 12) <= 0.12:
                return Comparison(Relation.FORMAT_ONLY, 1.0, "the values differ by a factor of 12 (monthly vs annual figure)")
    return cmp


def _group(fields: list[_F]) -> dict[str, list[_F]]:
    groups: dict[str, list[_F]] = {}
    for fd in fields:
        groups.setdefault(_family(fd.concept.key), []).append(fd)
    return groups


def _cross_document_checks(docs: list[DocumentInput], by_doc: dict[str, list[_F]], stats: _Stats) -> list[_Mismatch]:
    out: list[_Mismatch] = []
    for da, db in itertools.combinations(docs, 2):
        ga = _group([fd for fd in by_doc[da.document_id] if not is_blank_value(fd.f.value)])
        gb = _group([fd for fd in by_doc[db.document_id] if not is_blank_value(fd.f.value)])
        pair_mismatches: list[_Mismatch] = []
        matched_identifiers: list[Concept] = []

        for fam in [k for k in ga if k in gb]:
            ca, cb = ga[fam], gb[fam]
            pairs = [(x, y) for x in ca for y in cb if _pair_allowed(x.concept.key, y.concept.key)]
            if not pairs:
                continue
            if not pairs[0][0].concept.best_match and not (len(ca) == 1 and len(cb) == 1):
                continue                                    # ambiguous (several candidates) and no safe way to pick
            best: Optional[tuple[_F, _F, Comparison, Concept]] = None
            for x, y in pairs:
                concept = y.concept if x.concept.key == "address" else x.concept
                cmp = _compare(concept, x, y)
                if cmp.relation == Relation.UNCOMPARABLE:
                    continue
                rank = (RELATION_RANK[cmp.relation], -cmp.similarity)
                if best is None or rank < (RELATION_RANK[best[2].relation], -best[2].similarity):
                    best = (x, y, cmp, concept)
            if best is None:
                stats.uncomparable += 1
                continue
            x, y, cmp, concept = best
            if cmp.relation in CONSISTENT:
                if concept.identity and concept.kind == Kind.IDENTIFIER:
                    matched_identifiers.append(concept)
                continue
            pair_mismatches.append(_Mismatch(_ANOMALY_FOR_KIND[concept.kind], concept, [x, y], cmp, "cross"))

        # Identity correlation: several identity fields disagreeing at once is far more telling than one.
        conflicts = [m for m in pair_mismatches
                     if m.concept.identity and m.comparison.relation in (Relation.TYPO, Relation.DIFFERENT)]
        if len(conflicts) >= 2:
            for m in conflicts:
                others = ", ".join(o.concept.display for o in conflicts if o is not m)
                m.boost += _BOOST_MULTI_IDENTITY
                m.notes.append(f"Other identity fields also differ between {_doc_name(da)} and {_doc_name(db)}: {others}.")
        if matched_identifiers:
            for m in conflicts:
                if m.concept.kind != Kind.IDENTIFIER:
                    m.boost += _BOOST_ID_MATCHES
                    m.notes.append(f"The {matched_identifiers[0].display} matches in both documents although the "
                                   f"{m.concept.display} differs.")
        out.extend(pair_mismatches)
    return out


# --------------------------------------------------------------------------------------
# Within-document checks
# --------------------------------------------------------------------------------------
def _within_document_checks(doc: DocumentInput, fields: list[_F]) -> list[_Mismatch]:
    out: list[_Mismatch] = []
    usable = [fd for fd in fields if not is_blank_value(fd.f.value)]

    # a) labelled field with no readable value (missing information)
    for fd in fields:
        if is_blank_value(fd.f.value) and fd.f.label:
            out.append(_Mismatch(
                AnomalyType.MISSING_OR_UNREADABLE_VALUE, fd.concept, [fd],
                Comparison(Relation.DIFFERENT, 0.0, "the field was detected but no readable value was extracted"),
                "within", force_class=FindingClass.EXTRACTION_ERROR,
                force_reason="the field was detected but no value could be read; it may be blank on the form or "
                             "an extraction failure"))

    # b) the same single-valued concept appearing twice with different values
    groups: dict[str, list[_F]] = {}
    for fd in usable:
        if fd.concept.unique:
            groups.setdefault(fd.concept.key, []).append(fd)
    for group in groups.values():
        for x, y in itertools.combinations(group, 2):
            cmp = compare_values(x.concept.kind, x.f.value, y.f.value)
            if cmp.relation in (Relation.TYPO, Relation.DIFFERENT):
                out.append(_Mismatch(AnomalyType.CONFLICTING_VALUES_IN_DOCUMENT, x.concept, [x, y], cmp, "within",
                                     force_reason="a field that should hold one value shows two different values in "
                                                  "the same document"))

    # c) identifier format (PAN / Aadhaar / passport)
    for fd in usable:
        chk = check_identifier_format(fd.concept.key, fd.f.value)
        if chk is None or chk.valid:
            continue
        if chk.repaired:
            cmp = Comparison(Relation.TYPO, 0.9, f"'{fd.f.value}' does not match the expected format "
                                                 f"({chk.expected}); it {chk.repair_note}", ocr_confusable=True)
        else:
            cmp = Comparison(Relation.TYPO, 0.5, f"'{fd.f.value}' does not match the expected format ({chk.expected})")
        out.append(_Mismatch(AnomalyType.INVALID_IDENTIFIER_FORMAT, fd.concept, [fd], cmp, "within"))

    out.extend(_date_logic(usable))
    out.extend(_words_vs_figures(usable))
    return out


def _first_date(fields: list[_F], key: str) -> Optional[tuple[_F, list[date]]]:
    for fd in fields:
        if fd.concept.key == key:
            parsed = parse_date(fd.f.value)
            if parsed:
                return fd, list(parsed.candidates)
    return None


def _date_logic(fields: list[_F]) -> list[_Mismatch]:
    out: list[_Mismatch] = []
    today = _today()
    dob, issue, expiry = (_first_date(fields, k) for k in ("date_of_birth", "issue_date", "expiry_date"))

    def add(concept_fd: _F, involved: list[_F], detail: str) -> None:
        out.append(_Mismatch(AnomalyType.IMPLAUSIBLE_DATE, concept_fd.concept, involved,
                             Comparison(Relation.DIFFERENT, 0.0, detail), "within",
                             force_reason="the dates are logically impossible together"))

    if dob:
        fd, cands = dob
        if all(c > today for c in cands):
            add(fd, [fd], f"the date of birth {cands[0].isoformat()} is in the future")
        elif all((today - c).days / 365.25 > 120 for c in cands):
            add(fd, [fd], f"the date of birth {cands[0].isoformat()} implies an age above 120 years")
    if issue and expiry and all(i > e for i in issue[1] for e in expiry[1]):
        add(issue[0], [issue[0], expiry[0]],
            f"the issue date {issue[1][0].isoformat()} is after the expiry date {expiry[1][0].isoformat()}")
    if dob and issue and all(i < b for i in issue[1] for b in dob[1]):
        add(issue[0], [issue[0], dob[0]],
            f"the issue date {issue[1][0].isoformat()} is before the date of birth {dob[1][0].isoformat()}")
    return out


def _words_vs_figures(fields: list[_F]) -> list[_Mismatch]:
    out: list[_Mismatch] = []
    words = [fd for fd in fields if fd.concept.key == "amount_in_words"]
    figures = [fd for fd in fields if fd.concept.kind == Kind.AMOUNT and fd.concept.key != "amount_in_words"
               and re.search(r"\d", fd.f.value)]
    for w in words:
        if parse_amount(w.f.value) is None:
            continue                                         # not a clean number in words: cannot verify
        stem = re.sub(r"\b(in words|words|in rupees|rupees)\b", " ", label_text(w.f.label)).strip()
        same_page = [fd for fd in figures if fd.f.page == w.f.page]
        linked = [fd for fd in same_page
                  if stem and re.search(rf"\b{re.escape(stem)}\b", label_text(fd.f.label))]
        if not linked and len(same_page) == 1:
            linked = same_page
        if not linked:
            continue
        scored = [(compare_amounts(fd.f.value, w.f.value), fd) for fd in linked]
        scored = [s for s in scored if s[0].relation != Relation.UNCOMPARABLE]
        if not scored:
            continue
        cmp, fig = min(scored, key=lambda s: (RELATION_RANK[s[0].relation], -s[0].similarity))
        if cmp.relation in (Relation.TYPO, Relation.DIFFERENT):
            out.append(_Mismatch(AnomalyType.AMOUNT_WORDS_MISMATCH, _C_WORDS_VS_FIGURES, [fig, w], cmp, "within",
                                 force_reason="the amount written in figures and the amount written in words "
                                              "should always agree"))
    return out


# --------------------------------------------------------------------------------------
# Visual-only findings (an anomalous region on a critical field, nothing else wrong with its text)
# --------------------------------------------------------------------------------------
def _visual_only_findings(inv_id: str, docs: list[DocumentInput], by_doc: dict[str, list[_F]],
                          cited: set[tuple[str, str]]) -> list[Finding]:
    candidates: list[tuple[float, Finding]] = []
    for doc in docs:
        for an in doc.visual_anomalies:
            if an.bbox is None:
                continue
            matched: list[tuple[_F, _Hit]] = []
            for fd in by_doc[doc.document_id]:
                if fd.concept.criticality < CRITICAL_FIELD or is_blank_value(fd.f.value):
                    continue
                if (an.anomaly_id, fd.f.field_id) in cited:
                    continue
                hit = next((h for h in _visual_hits(fd) if h.anomaly is an), None)
                if hit:
                    matched.append((fd, hit))
            if not matched:
                continue
            strength = max(h.strength for _, h in matched)
            crit = max(fd.concept.criticality for fd, _ in matched)
            score = min(_CAP_VISUAL_ONLY, crit * strength * 0.7)
            fields = [fd for fd, _ in matched][:5]
            primary = fields[0]
            shown = ", ".join(f"{fd.concept.display} '{fd.f.value}'" for fd in fields)
            score_txt = f" (detector score {an.score:.2f})" if an.score is not None else ""
            finding = Finding(
                finding_id=_finding_id(inv_id, AnomalyType.VISUAL_ANOMALY_ON_CRITICAL_FIELD,
                                       [an.anomaly_id] + [fd.f.field_id for fd in fields]),
                anomaly_type=AnomalyType.VISUAL_ANOMALY_ON_CRITICAL_FIELD,
                classification=FindingClass.SUSPICIOUS_ALTERATION,
                observation_status=ObservationStatus.OBSERVED_VISUAL,
                severity=_severity(score), priority_score=round(score * 100), confidence=an.score,
                title=f"Visual anomaly overlaps {primary.concept.display}",
                field_name=primary.concept.display,
                reasoning=[
                    f"Visual analysis flagged '{an.kind}'{score_txt} in a region overlapping: {shown}.",
                    "This finding rests on the visual observation alone; the extracted text of the field did not "
                    "trigger a cross-document inconsistency.",
                    "Classified as a suspicious alteration: a region overlapping a critical field shows visual "
                    "irregularities that deserve a closer look.",
                ],
                recommended_review=_RECOMMENDED_REVIEW[FindingClass.SUSPICIOUS_ALTERATION],
                evidence=[_field_evidence(fd) for fd in fields] + [_visual_evidence(matched[0][1])],
                document_ids=[doc.document_id],
            )
            candidates.append((strength, finding))
    candidates.sort(key=lambda c: -c[0])
    return [f for _, f in candidates[:MAX_VISUAL_ONLY_FINDINGS]]


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------
def run_contextual_analysis(
    investigation: "InvestigationInput | dict",
    *,
    use_llm: bool = True,
    llm_settings: Optional[llm_service.LLMSettings] = None,
) -> ContextualAnalysisResult:
    """Analyse every document of one investigation and return structured, evidence-linked findings."""
    inv = InvestigationInput.model_validate(investigation)
    docs = list(inv.documents)
    all_fields: list[_F] = []
    by_doc: dict[str, list[_F]] = {}
    for doc in docs:
        rows = [_F(doc, f, infer_concept(f)) for f in doc.fields]
        by_doc[doc.document_id] = rows
        all_fields.extend(rows)

    stats = _Stats()
    mismatches: list[_Mismatch] = []
    for doc in docs:
        mismatches.extend(_within_document_checks(doc, by_doc[doc.document_id]))
    mismatches.extend(_cross_document_checks(docs, by_doc, stats))

    findings: dict[str, Finding] = {}
    cited: set[tuple[str, str]] = set()
    for m in mismatches:
        a = _assess(m)
        f = _to_finding(inv.investigation_id, m, a)
        findings.setdefault(f.finding_id, f)
        cited.update((h.anomaly.anomaly_id, h.field_id) for h in a.hits)
    for f in _visual_only_findings(inv.investigation_id, docs, by_doc, cited):
        findings.setdefault(f.finding_id, f)

    ordered = sorted(findings.values(), key=lambda f: (-f.priority_score, f.anomaly_type.value, f.finding_id))
    labels = {d.document_id: _doc_name(d) for d in docs}
    report = llm_service.explain_findings(ordered, labels, use_llm=use_llm, settings=llm_settings)

    limitations = [
        "Findings are automated indicators computed from OCR output, which is not verified ground truth; they "
        "require human review and are not proof of fraud or manipulation.",
        "Fields are compared only when their labels or types are recognised; fields with unrecognised labels are "
        "compared only with identically labelled fields in other documents.",
    ]
    limitations.append("Name and address matching is designed for Latin-script text; other scripts are compared only "
                       "when identical after normalisation.")
    if len(docs) < 2:
        limitations.append("Only one document was supplied, so cross-document comparison was not possible.")
    if stats.uncomparable:
        limitations.append(f"{stats.uncomparable} field pair(s) could not be compared because a value was empty, "
                           "unreadable or in an unsupported format.")
    limitations.extend(report.notes)

    return ContextualAnalysisResult(
        investigation_id=inv.investigation_id, engine_version=ENGINE_VERSION,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        documents_analyzed=len(docs), fields_analyzed=len(all_fields), findings=ordered,
        llm_used=report.llm_used, llm_model=report.model, limitations=limitations,
    )
