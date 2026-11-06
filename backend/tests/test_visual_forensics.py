import pytest

from app.services.pipeline import process_document


def test_pipeline_rejects_missing_file():
    with pytest.raises((ValueError, RuntimeError, FileNotFoundError)):
        process_document("nonexistent_test_document.pdf")


def test_pipeline_result_is_dictionary(sample_pdf):
    result = process_document(str(sample_pdf))

    assert isinstance(result, dict)


def test_pipeline_contains_extracted_information(sample_pdf):
    result = process_document(str(sample_pdf))

    assert "extracted_information" in result


def test_extracted_information_has_fields(sample_pdf):
    result = process_document(str(sample_pdf))

    extracted = result["extracted_information"]

    assert isinstance(extracted, dict)
    assert "fields" in extracted


@pytest.fixture
def sample_pdf(tmp_path):
    import fitz

    path = tmp_path / "sample.pdf"

    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "Name: Rahul Sharma\nPAN: ABCDE1234F\nAmount: 50000",
    )
    document.save(path)
    document.close()

    return path