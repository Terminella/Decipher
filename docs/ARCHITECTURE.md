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
- Investigation report generation
- Optional Ollama runtime and installed-model discovery
- Separate AI-investigation metadata and source-document links

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
- AI-investigation configuration, source links, execution records, findings,
  evidence references, reviews, chat messages, and audit events

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
11. Report generation produces a JSON dossier or a separately stored
    professional PDF rendition of the same report data.
12. Frontend displays current findings and provides report access.

The AI-investigation API is additive and separate from the standard workflow.
It can create independent AI investigations, link existing standard
investigations, select documents from explicitly linked sources, and store
additional AI-only uploads without invoking the standard document pipeline.
Ollama availability and installed-model discovery are exposed under `/ai`;
they are not prerequisites for standard uploads or analysis.

AI database entities use new tables created by the existing SQLAlchemy
`create_all` startup routine. Existing standard tables and processing
contracts are not changed by this addition.

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

Generated JSON and PDF reports are retained as files and indexed in the
database. The existing JSON endpoint and response contract remain unchanged;
PDF reports use a separate generation endpoint and the download route selects
the media type from the stored report format.
Analysis history is available through
`GET /investigations/{id}/analysis-runs` and
`GET /investigations/{id}/analysis-runs/{run_id}`; it is backend-only and does
not change the existing frontend.

AI investigation records are available through `/ai/investigations`; runtime
and model discovery are available through `/ai/environment` and `/ai/models`.
Multi-stage AI execution is queued in a bounded worker pool and exposes
progress, cancellation, and run-history APIs. Source files are hash-checked
before analysis; generated findings are persisted only when their evidence
references resolve to exact source quotes and valid pages. The frontend
provides a separate AI workspace for model selection, attaching source
documents, AI-only uploads, progress, findings, source-grounded chat, human
reviews, and AI-run PDF export. Chat persists conversations and restricts
returned citations to retrieved source evidence. Review decisions/comments are
stored as history and audit events. Completed AI runs are exported to their
own persisted PDF reports without changing standard investigation reports.
Quick analysis is the default and makes one bounded local-model request with a
compact evidence set; its default inference timeout is two minutes. Standard
and deep analysis retain the multi-stage workflow for users who choose the
longer review. Quick mode disables optional model thinking so its limited
output budget is used for structured findings rather than hidden reasoning.

Standard and AI PDFs include a contents page, clickable section bookmarks,
wrapped tables, and an embedded reportlab Vera Unicode font when available.
AI reports include run/model metadata, source evidence quotes, finding review
status and history, and a human-review disclaimer.

## 5. Limitations

Automated visual and contextual findings are indicators requiring review.
They should not be treated as conclusive proof of fraud or manipulation.