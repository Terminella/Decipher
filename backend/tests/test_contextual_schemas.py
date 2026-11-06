import pytest
from pydantic import ValidationError

from app.services.contextual_schemas import (
    BBox,
    FieldType,
    ExtractedField,
    VisualAnomaly,
    DocumentInput,
    InvestigationInput,
    Severity,
    FindingClass,
    ObservationStatus,
    AnomalyType,
    EvidenceType,
    EvidenceRef,
    Finding,
    ContextualAnalysisResult,
)


# ---------------------------------------------------------
# BBox TESTS
# ---------------------------------------------------------

def test_bbox_accepts_dictionary():
    bbox = BBox(x0=10, y0=20, x1=100, y1=200)

    assert bbox.x0 == 10
    assert bbox.y0 == 20
    assert bbox.x1 == 100
    assert bbox.y1 == 200


def test_bbox_accepts_list():
    bbox = BBox.model_validate([10, 20, 100, 200])

    assert bbox.x0 == 10
    assert bbox.y0 == 20
    assert bbox.x1 == 100
    assert bbox.y1 == 200


def test_bbox_accepts_tuple():
    bbox = BBox.model_validate((10, 20, 100, 200))

    assert bbox.area == 90 * 180


def test_bbox_reorders_reversed_coordinates():
    bbox = BBox(x0=100, y0=200, x1=10, y1=20)

    assert bbox.x0 == 10
    assert bbox.y0 == 20
    assert bbox.x1 == 100
    assert bbox.y1 == 200


def test_bbox_calculates_area():
    bbox = BBox(x0=0, y0=0, x1=100, y1=50)

    assert bbox.area == 5000


def test_bbox_calculates_overlap():
    first = BBox(x0=0, y0=0, x1=100, y1=100)
    second = BBox(x0=50, y0=50, x1=150, y1=150)

    assert first.overlap_ratio(second) == pytest.approx(0.25)


def test_bbox_no_overlap():
    first = BBox(x0=0, y0=0, x1=50, y1=50)
    second = BBox(x0=100, y0=100, x1=150, y1=150)

    assert first.overlap_ratio(second) == 0


def test_bbox_zero_area_returns_zero_overlap():
    first = BBox(x0=10, y0=10, x1=10, y1=10)
    second = BBox(x0=0, y0=0, x1=100, y1=100)

    assert first.overlap_ratio(second) == 0


# ---------------------------------------------------------
# EXTRACTED FIELD TESTS
# ---------------------------------------------------------

def test_extracted_field_minimum_required_data():
    field = ExtractedField(field_id="F001")

    assert field.field_id == "F001"
    assert field.value == ""
    assert field.field_type == FieldType.OTHER
    assert field.page == 1


def test_field_id_is_converted_to_string():
    field = ExtractedField(field_id=123)

    assert field.field_id == "123"


def test_field_value_is_converted_to_string():
    field = ExtractedField(
        field_id="F002",
        value=12345
    )

    assert field.value == "12345"


def test_none_field_value_becomes_empty_string():
    field = ExtractedField(
        field_id="F003",
        value=None
    )

    assert field.value == ""


def test_field_type_accepts_valid_enum():
    field = ExtractedField(
        field_id="F004",
        field_type=FieldType.NAME
    )

    assert field.field_type == FieldType.NAME


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("person", FieldType.NAME),
        ("person_name", FieldType.NAME),
        ("full_name", FieldType.NAME),
        ("dob", FieldType.DATE),
        ("datetime", FieldType.DATE),
        ("money", FieldType.AMOUNT),
        ("currency", FieldType.AMOUNT),
        ("location", FieldType.ADDRESS),
        ("addr", FieldType.ADDRESS),
        ("id", FieldType.ID_NUMBER),
        ("identifier", FieldType.ID_NUMBER),
        ("reference", FieldType.DOCUMENT_REFERENCE),
        ("ref", FieldType.DOCUMENT_REFERENCE),
    ],
)
def test_field_type_aliases(alias, expected):
    field = ExtractedField(
        field_id="F005",
        field_type=alias
    )

    assert field.field_type == expected


def test_unknown_field_type_becomes_other():
    field = ExtractedField(
        field_id="F006",
        field_type="something_unknown"
    )

    assert field.field_type == FieldType.OTHER


def test_field_type_is_case_insensitive():
    field = ExtractedField(
        field_id="F007",
        field_type="NAME"
    )

    assert field.field_type == FieldType.NAME


def test_ocr_confidence_accepts_decimal():
    field = ExtractedField(
        field_id="F008",
        ocr_confidence=0.85
    )

    assert field.ocr_confidence == 0.85


def test_ocr_confidence_scales_percentage():
    field = ExtractedField(
        field_id="F009",
        ocr_confidence=85
    )

    assert field.ocr_confidence == 0.85


def test_ocr_confidence_clamps_above_one():
    field = ExtractedField(
        field_id="F010",
        ocr_confidence=150
    )

    assert field.ocr_confidence == 1.0


def test_ocr_confidence_clamps_below_zero():
    field = ExtractedField(
        field_id="F011",
        ocr_confidence=-10
    )

    assert field.ocr_confidence == 0.0


def test_extracted_field_accepts_bbox():
    field = ExtractedField(
        field_id="F012",
        bbox=[10, 20, 100, 200]
    )

    assert isinstance(field.bbox, BBox)
    assert field.bbox.area == 90 * 180


def test_extracted_field_rejects_invalid_page():
    with pytest.raises(ValidationError):
        ExtractedField(
            field_id="F013",
            page=0
        )


# ---------------------------------------------------------
# VISUAL ANOMALY TESTS
# ---------------------------------------------------------

def test_visual_anomaly_creation():
    anomaly = VisualAnomaly(
        anomaly_id="A001",
        kind="font_inconsistency",
        page=1,
        score=0.85,
        description="Font appears inconsistent."
    )

    assert anomaly.anomaly_id == "A001"
    assert anomaly.kind == "font_inconsistency"
    assert anomaly.score == 0.85


def test_visual_anomaly_id_converts_to_string():
    anomaly = VisualAnomaly(anomaly_id=123)

    assert anomaly.anomaly_id == "123"


def test_visual_anomaly_score_scales_percentage():
    anomaly = VisualAnomaly(
        anomaly_id="A002",
        score=85
    )

    assert anomaly.score == 0.85


def test_visual_anomaly_score_clamps():
    anomaly = VisualAnomaly(
        anomaly_id="A003",
        score=150
    )

    assert anomaly.score == 1.0


def test_visual_anomaly_accepts_bbox():
    anomaly = VisualAnomaly(
        anomaly_id="A004",
        bbox=[10, 20, 100, 200]
    )

    assert isinstance(anomaly.bbox, BBox)


def test_visual_anomaly_rejects_invalid_page():
    with pytest.raises(ValidationError):
        VisualAnomaly(
            anomaly_id="A005",
            page=0
        )


# ---------------------------------------------------------
# DOCUMENT INPUT TESTS
# ---------------------------------------------------------

def test_document_input_creation():
    document = DocumentInput(
        document_id="DOC001",
        filename="invoice.pdf"
    )

    assert document.document_id == "DOC001"
    assert document.filename == "invoice.pdf"
    assert document.fields == []
    assert document.visual_anomalies == []


def test_document_id_converts_to_string():
    document = DocumentInput(document_id=123)

    assert document.document_id == "123"


def test_document_accepts_extracted_fields():
    document = DocumentInput(
        document_id="DOC002",
        fields=[
            {
                "field_id": "F001",
                "label": "Applicant Name",
                "field_type": "name",
                "value": "Rahul Sharma"
            }
        ]
    )

    assert len(document.fields) == 1
    assert document.fields[0].value == "Rahul Sharma"


def test_document_accepts_visual_anomalies():
    document = DocumentInput(
        document_id="DOC003",
        visual_anomalies=[
            {
                "anomaly_id": "A001",
                "kind": "ela_hotspot",
                "score": 0.9
            }
        ]
    )

    assert len(document.visual_anomalies) == 1
    assert document.visual_anomalies[0].kind == "ela_hotspot"


# ---------------------------------------------------------
# INVESTIGATION INPUT TESTS
# ---------------------------------------------------------

def test_investigation_input_creation():
    investigation = InvestigationInput(
        investigation_id="INV001"
    )

    assert investigation.investigation_id == "INV001"
    assert investigation.documents == []


def test_investigation_id_converts_to_string():
    investigation = InvestigationInput(
        investigation_id=123
    )

    assert investigation.investigation_id == "123"


def test_investigation_accepts_multiple_documents():
    investigation = InvestigationInput(
        investigation_id="INV002",
        documents=[
            {"document_id": "DOC001"},
            {"document_id": "DOC002"},
        ]
    )

    assert len(investigation.documents) == 2


def test_investigation_accepts_nested_fields():
    investigation = InvestigationInput(
        investigation_id="INV003",
        documents=[
            {
                "document_id": "DOC001",
                "fields": [
                    {
                        "field_id": "F001",
                        "label": "Name",
                        "field_type": "name",
                        "value": "Aryan"
                    }
                ]
            }
        ]
    )

    assert investigation.documents[0].fields[0].value == "Aryan"


# ---------------------------------------------------------
# ENUM TESTS
# ---------------------------------------------------------

def test_severity_values():
    assert Severity.INFO.value == "info"
    assert Severity.LOW.value == "low"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.HIGH.value == "high"


def test_finding_class_values():
    assert FindingClass.ORDINARY_INCONSISTENCY.value == "ordinary_inconsistency"
    assert FindingClass.EXTRACTION_ERROR.value == "extraction_error"
    assert FindingClass.SUSPICIOUS_ALTERATION.value == "suspicious_alteration"
    assert FindingClass.INVESTIGATION_INDICATOR.value == "investigation_indicator"


def test_observation_status_values():
    assert ObservationStatus.OBSERVED_VISUAL.value == "observed_visual_characteristic"
    assert ObservationStatus.DETECTED_INCONSISTENCY.value == "detected_inconsistency"
    assert ObservationStatus.POTENTIAL_MANIPULATION.value == "potential_manipulation"


def test_anomaly_type_values():
    assert AnomalyType.NAME_MISMATCH.value == "name_mismatch"
    assert AnomalyType.DATE_MISMATCH.value == "date_mismatch"
    assert AnomalyType.AMOUNT_MISMATCH.value == "amount_mismatch"
    assert AnomalyType.IDENTIFIER_MISMATCH.value == "identifier_mismatch"


# ---------------------------------------------------------
# OUTPUT MODEL TESTS
# ---------------------------------------------------------

def test_evidence_reference_creation():
    evidence = EvidenceRef(
        evidence_type=EvidenceType.EXTRACTED_FIELD,
        document_id="DOC001",
        page=1,
        field_id="F001",
        label="Applicant Name",
        value="Aryan"
    )

    assert evidence.document_id == "DOC001"
    assert evidence.field_id == "F001"
    assert evidence.value == "Aryan"


def test_finding_creation():
    finding = Finding(
        finding_id="FIND001",
        anomaly_type=AnomalyType.NAME_MISMATCH,
        classification=FindingClass.INVESTIGATION_INDICATOR,
        observation_status=ObservationStatus.DETECTED_INCONSISTENCY,
        severity=Severity.HIGH,
        priority_score=90,
        title="Name mismatch detected"
    )

    assert finding.finding_id == "FIND001"
    assert finding.severity == Severity.HIGH
    assert finding.priority_score == 90
    assert finding.evidence == []


def test_finding_rejects_priority_above_100():
    with pytest.raises(ValidationError):
        Finding(
            finding_id="FIND002",
            anomaly_type=AnomalyType.NAME_MISMATCH,
            classification=FindingClass.INVESTIGATION_INDICATOR,
            observation_status=ObservationStatus.DETECTED_INCONSISTENCY,
            severity=Severity.HIGH,
            priority_score=101,
            title="Invalid priority"
        )


def test_contextual_analysis_result_creation():
    result = ContextualAnalysisResult(
        investigation_id="INV001",
        engine_version="1.0.0",
        generated_at="2026-11-06T10:00:00Z"
    )

    assert result.investigation_id == "INV001"
    assert result.engine_version == "1.0.0"
    assert result.findings == []
    assert result.documents_analyzed == 0
    assert result.fields_analyzed == 0
    assert result.llm_used is False


def test_contextual_analysis_result_accepts_findings():
    finding = Finding(
        finding_id="FIND003",
        anomaly_type=AnomalyType.AMOUNT_MISMATCH,
        classification=FindingClass.INVESTIGATION_INDICATOR,
        observation_status=ObservationStatus.DETECTED_INCONSISTENCY,
        severity=Severity.HIGH,
        title="Amount mismatch"
    )

    result = ContextualAnalysisResult(
        investigation_id="INV002",
        engine_version="1.0.0",
        generated_at="2026-11-06T10:00:00Z",
        documents_analyzed=2,
        fields_analyzed=10,
        findings=[finding]
    )

    assert len(result.findings) == 1
    assert result.findings[0].title == "Amount mismatch"
    assert result.documents_analyzed == 2
    assert result.fields_analyzed == 10
