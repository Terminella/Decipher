# Decipher - System Architecture

## 1. Overview

Decipher is an AI-powered document forensics and verification system. It
accepts digital documents, extracts their content, identifies potential
visual irregularities, compares information across documents, and generates
an investigation dossier.

## 2. Architecture

The application follows a three-tier architecture.

### Presentation Tier

Technology:
- React
- Vite
- Tailwind CSS

Responsibilities:
- Document upload
- Investigation creation
- Processing status
- Extracted information display
- Findings and severity display
- Evidence visualization
- Report access

### Application and Intelligence Tier

Technology:
- Python
- FastAPI
- Pydantic
- EasyOCR
- PyMuPDF
- OpenCV
- NumPy
- Pillow

Responsibilities:
- API request handling
- Document processing orchestration
- OCR and text extraction
- Document classification
- Visual-forensics analysis
- Contextual comparison
- Evidence association
- Report generation

### Data and Persistence Tier

Technology:
- SQLite
- SQLAlchemy
- Local file storage

Responsibilities:
- Investigation records
- Uploaded document metadata
- SHA-256 document hashes
- Extracted fields
- Findings
- Generated reports

## 3. Processing Workflow

1. User creates an investigation.
2. User uploads one or more documents.
3. Backend validates file type and size.
4. Uploaded document is stored in the investigation directory.
5. SHA-256 hash is calculated.
6. Department 4 performs OCR, classification, extraction, and visual analysis.
7. Backend stores the processing result and extracted fields.
8. Department 3 performs contextual and cross-document analysis.
9. Findings are stored in SQLite.
10. Each analysis run stores a timestamped snapshot of its findings and
    analyzed documents; later runs refresh the current findings without
    overwriting prior run snapshots.
11. Report generator produces an investigation dossier.
12. Frontend displays current findings and provides report access.

The investigation API passes Department 4's observed visual pages and field
metadata into Department 3, including page coordinates scaled to the visual
page dimensions when both sources provide dimensions. Persisted findings keep
their structured evidence references, including document, page, field, and
bounding-box data where available.

## 4. Evidence Traceability

Each uploaded document is associated with:
- Investigation ID
- Original filename
- SHA-256 hash
- Storage path
- Processing status
- Extracted fields
- Processing output

Findings retain their classification, severity, explanation, and evidence
metadata.

Generated reports are retained as JSON files and indexed in the database.
The API download endpoint returns the report with document summaries,
extracted fields, contextual findings, visual observations, and limitations.
Analysis history is available through
`GET /investigations/{id}/analysis-runs` and
`GET /investigations/{id}/analysis-runs/{run_id}`; it is backend-only and does
not change the existing frontend.

## 5. Limitations

Automated visual and contextual findings are indicators requiring review.
They should not be treated as conclusive proof of fraud or manipulation.