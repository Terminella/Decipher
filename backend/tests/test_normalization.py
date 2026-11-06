import pytest
from decimal import Decimal

from app.services.normalization import (
    clean_text,
    normalize_value,
    extract_fields,
    normalize_extraction,
    parse_date,
    parse_amount,
    compare_values,
    compare_amounts,
    check_identifier_format,
    display_normalized,
    infer_concept,
    is_blank_value,
    label_text,
    Kind,
    Relation,
)

from app.services.contextual_schemas import (
    ExtractedField,
    FieldType,
)


# =====================================================
# 1. TEXT CLEANING
# =====================================================

def test_clean_text_removes_extra_spaces():
    assert clean_text("  Hello   World  ") == "Hello World"


def test_clean_text_handles_form_feed():
    result = clean_text("Page 1\x0cPage 2")
    assert result == "Page 1\nPage 2"


def test_clean_text_reduces_multiple_newlines():
    result = clean_text("First\n\n\n\nSecond")
    assert result == "First\n\nSecond"


def test_clean_text_handles_empty_input():
    assert clean_text("") == ""


# =====================================================
# 2. VALUE NORMALIZATION
# =====================================================

def test_normalize_pan():
    assert normalize_value(
        "pan_number", " abcde 1234f "
    ) == "ABCDE1234F"


def test_normalize_email():
    assert normalize_value(
        "email", " TEST@EXAMPLE.COM "
    ) == "test@example.com"


def test_normalize_salary():
    assert normalize_value(
        "salary", "₹ 50,000"
    ) == "50,000"


def test_normalize_annual_income():
    assert normalize_value(
        "annual_income", "₹ 6,00,000"
    ) == "6,00,000"


def test_normalize_regular_value():
    assert normalize_value(
        "name", "  Rahul Mehta  "
    ) == "Rahul Mehta"


# =====================================================
# 3. FIELD EXTRACTION
# =====================================================

def test_extract_name():
    result = extract_fields("Name: Rahul Mehta")

    assert result["fields"]["name"] == "Rahul Mehta"


def test_extract_pan():
    result = extract_fields("PAN Number: ABCDE1234F")

    assert result["fields"]["pan_number"] == "ABCDE1234F"


def test_extract_email():
    result = extract_fields("Email: test@example.com")

    assert result["fields"]["email"] == "test@example.com"


def test_extract_phone():
    result = extract_fields("Mobile Number: 9876543210")

    assert result["fields"]["phone"] == "9876543210"


def test_extract_pan_fallback():
    result = extract_fields(
        "Applicant identification: ABCDE1234F"
    )

    assert result["fields"]["pan_number"] == "ABCDE1234F"


def test_extract_email_fallback():
    result = extract_fields(
        "Contact the applicant at test@example.com"
    )

    assert result["fields"]["email"] == "test@example.com"


def test_extract_phone_fallback():
    result = extract_fields(
        "Contact the applicant at 9876543210"
    )

    assert result["fields"]["phone"] == "9876543210"


def test_extract_returns_metadata():
    result = extract_fields("Name: Rahul Mehta")

    assert "field_metadata" in result
    assert "cleaned_text" in result


# =====================================================
# 4. OCR NORMALIZATION
# =====================================================

def test_normalize_extraction():
    ocr_result = {
        "full_text": "Name: Rahul Mehta",
        "pages": []
    }

    result = normalize_extraction(ocr_result)

    assert result["document_text"] == "Name: Rahul Mehta"
    assert result["fields"]["name"] == "Rahul Mehta"
    assert result["pages"] == []


def test_normalize_extraction_with_empty_input():
    result = normalize_extraction({})

    assert result["document_text"] == ""
    assert result["fields"] == {}


# =====================================================
# 5. DATE PARSING
# =====================================================

def test_parse_date_iso():
    result = parse_date("2025-10-15")

    assert result is not None
    assert result.candidates[0].isoformat() == "2025-10-15"


def test_parse_date_indian_format():
    result = parse_date("15/10/2025")

    assert result is not None
    assert result.candidates[0].isoformat() == "2025-10-15"


def test_parse_date_text_format():
    result = parse_date("15 October 2025")

    assert result is not None
    assert result.candidates[0].isoformat() == "2025-10-15"


def test_parse_invalid_date():
    assert parse_date("not a date") is None


def test_parse_empty_date():
    assert parse_date("") is None


# =====================================================
# 6. AMOUNT PARSING
# =====================================================

def test_parse_amount_numeric():
    result = parse_amount("50000")

    assert result is not None
    assert result.value == Decimal("50000")


def test_parse_amount_with_currency():
    result = parse_amount("₹50,000")

    assert result is not None
    assert result.value == Decimal("50000")


def test_parse_amount_lakh():
    result = parse_amount("5 lakh")

    assert result is not None
    assert result.value == Decimal("500000")


def test_parse_invalid_amount():
    assert parse_amount("not an amount") is None


def test_compare_equal_amounts():
    result = compare_amounts("50000", "50000")

    assert result.relation == Relation.EXACT


def test_compare_different_amounts():
    result = compare_amounts("50000", "75000")

    assert result.relation == Relation.DIFFERENT


# =====================================================
# 7. NAME COMPARISON
# =====================================================

def test_compare_same_names():
    result = compare_values(
        Kind.NAME,
        "Rahul Mehta",
        "Rahul Mehta"
    )

    assert result.relation == Relation.EXACT


def test_compare_names_with_different_titles():
    result = compare_values(
        Kind.NAME,
        "Mr. Rahul Mehta",
        "Rahul Mehta"
    )

    assert result.relation == Relation.FORMAT_ONLY


def test_compare_name_with_initial():
    result = compare_values(
        Kind.NAME,
        "Rahul Mehta",
        "R Mehta"
    )

    assert result.relation == Relation.COMPATIBLE


def test_compare_different_names():
    result = compare_values(
        Kind.NAME,
        "Rahul Mehta",
        "Amit Sharma"
    )

    assert result.relation == Relation.DIFFERENT


# =====================================================
# 8. ADDRESS COMPARISON
# =====================================================

def test_compare_same_addresses():
    result = compare_values(
        Kind.ADDRESS,
        "12 Park Road, Delhi 110001",
        "12 Park Road, Delhi 110001"
    )

    assert result.relation == Relation.EXACT


def test_compare_different_postcodes():
    result = compare_values(
        Kind.ADDRESS,
        "12 Park Road, Delhi 110001",
        "12 Park Road, Delhi 110002"
    )

    assert result.relation == Relation.DIFFERENT


# =====================================================
# 9. IDENTIFIER COMPARISON
# =====================================================

def test_compare_same_identifiers():
    result = compare_values(
        Kind.IDENTIFIER,
        "ABCDE1234F",
        "ABCDE1234F"
    )

    assert result.relation == Relation.EXACT


def test_compare_different_identifiers():
    result = compare_values(
        Kind.IDENTIFIER,
        "ABCDE1234F",
        "PQRSX9876K"
    )

    assert result.relation == Relation.DIFFERENT


# =====================================================
# 10. IDENTIFIER FORMAT VALIDATION
# =====================================================

def test_valid_pan():
    result = check_identifier_format(
        "pan", "ABCDE1234F"
    )

    assert result is not None
    assert result.valid is True


def test_invalid_pan():
    result = check_identifier_format(
        "pan", "ABCDE123"
    )

    assert result is not None
    assert result.valid is False


def test_valid_aadhaar():
    result = check_identifier_format(
        "aadhaar", "123456789012"
    )

    assert result is not None
    assert result.valid is True


def test_invalid_aadhaar():
    result = check_identifier_format(
        "aadhaar", "12345678"
    )

    assert result is not None
    assert result.valid is False


def test_unknown_identifier_type():
    result = check_identifier_format(
        "unknown", "123456"
    )

    assert result is None


# =====================================================
# 11. CONCEPT INFERENCE
# =====================================================

def test_infer_name_concept():
    field = ExtractedField(
        field_id="1",
        label="Applicant Name",
        field_type=FieldType.NAME,
        value="Rahul Mehta"
    )

    result = infer_concept(field)

    assert result.kind == Kind.NAME
    assert result.key == "person_name"


def test_infer_pan_concept():
    field = ExtractedField(
        field_id="2",
        label="PAN Number",
        field_type=FieldType.ID_NUMBER,
        value="ABCDE1234F"
    )

    result = infer_concept(field)

    assert result.kind == Kind.IDENTIFIER
    assert result.key == "pan"


def test_infer_date_of_birth_concept():
    field = ExtractedField(
        field_id="3",
        label="Date of Birth",
        field_type=FieldType.DATE,
        value="15/10/2000"
    )

    result = infer_concept(field)

    assert result.kind == Kind.DATE
    assert result.key == "date_of_birth"


def test_infer_address_concept():
    field = ExtractedField(
        field_id="4",
        label="Permanent Address",
        field_type=FieldType.ADDRESS,
        value="12 Park Road, Delhi"
    )

    result = infer_concept(field)

    assert result.kind == Kind.ADDRESS
    assert result.key == "address_permanent"


# =====================================================
# 12. HELPER FUNCTIONS
# =====================================================

def test_blank_values():
    assert is_blank_value("N/A") is True
    assert is_blank_value("   ") is True
    assert is_blank_value("Unknown") is True
    assert is_blank_value("Rahul Mehta") is False


def test_label_text():
    assert label_text("Applicant's Name") == "applicants name"


def test_display_normalized_name():
    result = display_normalized(
        Kind.NAME, "Mr. Rahul Mehta"
    )

    assert result == "rahul mehta"


def test_display_normalized_pan():
    result = display_normalized(
        Kind.IDENTIFIER, "ABCDE-1234-F"
    )

    assert result == "ABCDE1234F"


def test_display_normalized_amount():
    result = display_normalized(
        Kind.AMOUNT, "₹50,000"
    )

    assert result == "5E+4"


def test_display_invalid_date():
    result = display_normalized(
        Kind.DATE, "invalid date"
    )

    assert result is None
