"""
Data contract for the AI / Contextual Intelligence module (Department 3).

    Dept 4 (OCR / vision)  --InvestigationInput-->  correlation.run_contextual_analysis()
    ContextualAnalysisResult  -->  Backend (persist)  -->  Frontend (display) / PDF dossier

Conventions
  * Pydantic v2.
  * Bounding boxes are passed through untouched. Use whatever coordinate space Dept 4 uses
    (e.g. pixels of the rendered page image) - the frontend gets the same numbers back.
    Field boxes and visual-anomaly boxes must share that space, otherwise overlap checks are meaningless.
  * OCR confidence is 0..1 (values in 1..100 are rescaled automatically).
  * Ids (field_id, anomaly_id, document_id, investigation_id) may be ints or strings; they are stored as strings.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# --------------------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------------------
class BBox(BaseModel):
    """Axis-aligned box. Also accepts [x0, y0, x1, y1] lists."""

    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="before")
    @classmethod
    def _accept_sequences(cls, data: Any) -> Any:
        if isinstance(data, (list, tuple)) and len(data) == 4:
            x0, y0, x1, y1 = data
            return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
        return data

    @model_validator(mode="after")
    def _order_corners(self) -> "BBox":
        if self.x1 < self.x0:
            self.x0, self.x1 = self.x1, self.x0
        if self.y1 < self.y0:
            self.y0, self.y1 = self.y1, self.y0
        return self

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def overlap_ratio(self, other: "BBox") -> float:
        """Share of THIS box that is covered by `other` (0..1)."""
        ix = max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))
        iy = max(0.0, min(self.y1, other.y1) - max(self.y0, other.y0))
        return (ix * iy) / self.area if self.area > 0 else 0.0


class FieldType(str, Enum):
    NAME = "name"
    DATE = "date"
    AMOUNT = "amount"
    ADDRESS = "address"
    ID_NUMBER = "id_number"
    DOCUMENT_REFERENCE = "document_reference"
    OTHER = "other"


_FIELD_TYPE_ALIASES = {
    "person": "name", "person_name": "name", "full_name": "name", "names": "name",
    "dob": "date", "datetime": "date", "dates": "date",
    "money": "amount", "currency": "amount", "amounts": "amount",
    "location": "address", "gpe": "address", "addr": "address",
    "id": "id_number", "identifier": "id_number", "id_no": "id_number", "identification_number": "id_number",
    "reference": "document_reference", "ref": "document_reference", "doc_reference": "document_reference",
}


def _to_id(value: Any) -> str:
    return str(value)


# --------------------------------------------------------------------------------------
# INPUT  (produced by Dept 4 / the backend, consumed by the contextual engine)
# --------------------------------------------------------------------------------------
class ExtractedField(BaseModel):
    """One field/value pair read from a document page."""

    field_id: str                                   # unique inside the investigation (e.g. the DB row id)
    label: Optional[str] = None                     # label as printed, e.g. "Name of Applicant"
    field_type: FieldType = FieldType.OTHER         # name/date/amount/address/id_number/document_reference/other
    value: str = ""                                 # raw extracted text, exactly as read
    page: int = Field(default=1, ge=1)
    ocr_confidence: Optional[float] = None          # 0..1
    bbox: Optional[BBox] = None

    @field_validator("field_id", mode="before")
    @classmethod
    def _field_id_to_str(cls, v: Any) -> str:
        return _to_id(v)

    @field_validator("value", mode="before")
    @classmethod
    def _value_to_str(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("field_type", mode="before")
    @classmethod
    def _coerce_field_type(cls, v: Any) -> Any:
        if isinstance(v, FieldType):
            return v
        key = str(v or "other").strip().lower().replace(" ", "_").replace("-", "_")
        key = _FIELD_TYPE_ALIASES.get(key, key)
        return key if key in {t.value for t in FieldType} else FieldType.OTHER

    @field_validator("ocr_confidence", mode="before")
    @classmethod
    def _scale_confidence(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        v = float(v)
        if v > 1.0:
            v = v / 100.0
        return min(max(v, 0.0), 1.0)


class VisualAnomaly(BaseModel):
    """A suspicious region (or whole-document observation) reported by the visual-forensics module."""

    anomaly_id: str
    kind: str = "unspecified"                       # e.g. ela_hotspot, font_inconsistency, alignment_irregularity
    page: Optional[int] = Field(default=None, ge=1)  # None = applies to the whole document
    score: Optional[float] = None                   # 0..1, strength reported by the detector
    description: Optional[str] = None
    bbox: Optional[BBox] = None                     # None = not localised (document-level observation)

    @field_validator("anomaly_id", mode="before")
    @classmethod
    def _anomaly_id_to_str(cls, v: Any) -> str:
        return _to_id(v)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: Any) -> Optional[float]:
        if v is None:
            return None
        v = float(v)
        if v > 1.0:
            v = v / 100.0
        return min(max(v, 0.0), 1.0)


class DocumentInput(BaseModel):
    document_id: str
    filename: Optional[str] = None
    doc_type: Optional[str] = None                  # from the classifier, e.g. "id_proof", "application_form"
    fields: list[ExtractedField] = Field(default_factory=list)
    visual_anomalies: list[VisualAnomaly] = Field(default_factory=list)

    @field_validator("document_id", mode="before")
    @classmethod
    def _document_id_to_str(cls, v: Any) -> str:
        return _to_id(v)


class InvestigationInput(BaseModel):
    investigation_id: str
    documents: list[DocumentInput] = Field(default_factory=list)

    @field_validator("investigation_id", mode="before")
    @classmethod
    def _investigation_id_to_str(cls, v: Any) -> str:
        return _to_id(v)


# --------------------------------------------------------------------------------------
# OUTPUT  (returned to the backend for persistence; shown by the frontend and the PDF dossier)
# --------------------------------------------------------------------------------------
class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingClass(str, Enum):
    """What kind of discrepancy this is - the distinction the department brief asks for."""

    ORDINARY_INCONSISTENCY = "ordinary_inconsistency"      # benign: formatting, initials, rounding, spelling
    EXTRACTION_ERROR = "extraction_error"                  # probably an OCR / extraction artefact
    SUSPICIOUS_ALTERATION = "suspicious_alteration"        # small change that is consistent with an edit
    INVESTIGATION_INDICATOR = "investigation_indicator"    # material contradiction that needs investigation


class ObservationStatus(str, Enum):
    """Observed vs. inferred, so the UI never presents a guess as a fact."""

    OBSERVED_VISUAL = "observed_visual_characteristic"
    DETECTED_INCONSISTENCY = "detected_inconsistency"
    POTENTIAL_MANIPULATION = "potential_manipulation"


class AnomalyType(str, Enum):
    NAME_MISMATCH = "name_mismatch"
    DATE_MISMATCH = "date_mismatch"
    AMOUNT_MISMATCH = "amount_mismatch"
    ADDRESS_MISMATCH = "address_mismatch"
    IDENTIFIER_MISMATCH = "identifier_mismatch"
    FIELD_MISMATCH = "field_mismatch"
    CONFLICTING_VALUES_IN_DOCUMENT = "conflicting_values_in_document"
    MISSING_OR_UNREADABLE_VALUE = "missing_or_unreadable_value"
    INVALID_IDENTIFIER_FORMAT = "invalid_identifier_format"
    IMPLAUSIBLE_DATE = "implausible_date"
    AMOUNT_WORDS_MISMATCH = "amount_words_mismatch"
    VISUAL_ANOMALY_ON_CRITICAL_FIELD = "visual_anomaly_on_critical_field"


class EvidenceType(str, Enum):
    EXTRACTED_FIELD = "extracted_field"
    VISUAL_ANOMALY = "visual_anomaly"


class EvidenceRef(BaseModel):
    """Pointer back to the exact place in a source document that supports a finding."""

    evidence_type: EvidenceType
    document_id: str
    page: int = 1
    field_id: Optional[str] = None
    anomaly_id: Optional[str] = None
    label: Optional[str] = None                     # field label, or the visual anomaly kind
    value: Optional[str] = None                     # raw extracted text, exactly as received
    normalized_value: Optional[str] = None          # what the engine compared (for transparency)
    ocr_confidence: Optional[float] = None
    bbox: Optional[BBox] = None                     # passed through unchanged for frontend highlighting
    note: Optional[str] = None


class Finding(BaseModel):
    finding_id: str                                 # deterministic: same inputs -> same id (dashboard == report)
    anomaly_type: AnomalyType
    classification: FindingClass
    observation_status: ObservationStatus
    severity: Severity
    priority_score: int = Field(default=0, ge=0, le=100)   # sort key, higher = review first
    confidence: Optional[float] = None              # 0..1, confidence the discrepancy is real (not an OCR artefact)
    title: str
    field_name: Optional[str] = None                # human name of the compared field, e.g. "date of birth"
    explanation: str = ""                           # evidence-grounded, hedged text shown to the reviewer
    explanation_source: Literal["template", "llm"] = "template"
    reasoning: list[str] = Field(default_factory=list)     # engine's step-by-step facts behind the finding
    recommended_review: str = ""                    # what a human should check next
    evidence: list[EvidenceRef] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)


class ContextualAnalysisResult(BaseModel):
    investigation_id: str
    engine_version: str
    generated_at: str                               # ISO-8601, UTC
    documents_analyzed: int = 0
    fields_analyzed: int = 0
    findings: list[Finding] = Field(default_factory=list)   # sorted: highest priority first
    llm_used: bool = False
    llm_model: Optional[str] = None
    limitations: list[str] = Field(default_factory=list)    # honest notes for the dossier's limitations section
