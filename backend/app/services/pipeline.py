
from pathlib import Path
import hashlib

from .ocr_service import OCRService
from .classifier import classify_document
from .normalization import normalize_extraction
from .visual_forensics import VisualForensics


class DocumentPipeline:

    def __init__(self):

        self.ocr = OCRService()

        self.forensics = VisualForensics()

    def process_document(
        self,
        file_path,
        force_ocr=False
    ):

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                "Document does not exist"
            )

        # Step 1: Generate SHA-256 hash
        file_hash = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        # Step 2: OCR extraction
        ocr_result = self.ocr.extract(
            path,
            force_ocr=force_ocr
        )

        # Step 3: Document classification
        classification = classify_document(
            ocr_result["full_text"]
        )

        # Step 4: Field normalization
        extracted = normalize_extraction(
            ocr_result
        )

        # Step 5: Visual forensic analysis
        visual_result = self.forensics.analyze_document(
            path
        )

        # Step 6: Final result
        return {

            "document_id": file_hash[:16],

            "filename": path.name,

            "sha256": file_hash,

            "processing_status": "completed",

            "classification": classification,

            "extracted_information": {

                "full_text": extracted["document_text"],

                "fields": extracted["fields"],

                "field_metadata": extracted["field_metadata"],

                "pages": extracted["pages"]
            },

            "visual_forensics": visual_result,

            "warnings": [
                "OCR confidence does not establish authenticity.",
                "Visual observations are not proof of fraud.",
                "All potential anomalies require human review."
            ]
        }


_pipeline = None


def process_document(file_path, force_ocr=False):

    global _pipeline

    if _pipeline is None:
        _pipeline = DocumentPipeline()

    return _pipeline.process_document(
        file_path,
        force_ocr
    )
