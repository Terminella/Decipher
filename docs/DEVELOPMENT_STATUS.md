# Development Status

## Backend

- [x] FastAPI application entry point
- [x] SQLite database configuration
- [x] SQLAlchemy data models
- [x] Pydantic request and response schemas
- [x] Evidence storage service
- [x] Investigation creation and retrieval
- [x] Document upload endpoint
- [x] Document processing integration
- [x] Contextual analysis integration
- [x] JSON report generation endpoint
- [x] Optional Ollama runtime/version and installed-model discovery API
- [x] Hardware profile with CPU, memory, and NVIDIA GPU detection
- [x] AI investigation persistence, source linking, selective document
  attachment, AI-only upload, archive lifecycle, and audit events
- [x] Multi-stage AI analysis, asynchronous run execution, cancellation, and
  run-history APIs
- [x] Bounded one-pass quick analysis by default, with a compact evidence
  payload, smaller context/output limits, and a 120-second inference timeout
- [x] AI findings with source-hash verification and exact-quote/page validation
- [x] Persistent source-grounded investigation chat and review history/comments
- [x] AI investigation workspace with runtime/model selection, document linking,
  AI-only upload, progress, and findings display
- [x] Structured standard-report PDFs with contents, bookmarks, embedded
  Unicode font, evidence traceability, and long-report layout checks
- [x] Persisted PDF export for completed AI investigation runs

## Department Integration

- [x] Department 4 pipeline import
- [x] Department 3 contextual schema import
- [x] Contextual analysis adapter uses the actual Department 3 input/output structures
- [x] Department 4 field metadata and page-level visual output are mapped
- [x] End-to-end integration across all five sample cases

## Frontend

- [x] Centralized API service
- [x] Investigation creation and multi-document upload
- [x] Findings display with evidence references
- [x] Report generation and download link
- [x] JSON and PDF report generation and download
- [x] AI chat, finding review actions/history, and per-run PDF report downloads
- [x] Dashboard counts and recent activity from persisted API records

## Testing

- [x] Backend dependencies installed in `backend/.venv`
- [x] Backend tests: 245 passed (including AI runtime, worker, evidence, chat,
  review history, AI report export, and PDF layout checks)
- [x] Upload type, size, duplicate, SHA-256, and evidence checks
- [x] Contextual analysis integration against all 30 synthetic PDFs
- [x] Five complete six-document API workflows and report download
- [x] Timestamped analysis-run snapshots with list/detail API and regression test
- [x] Frontend production build
- [x] Browser upload, analysis, findings, and report-generation workflow

## Deployment

- [x] Environment configuration example and local startup scripts
- [ ] Production deployment, authentication, and persistent storage validation

## Verification Notes

- Each sample case produced amount, supplier/name, and date mismatch findings
  with evidence linking back to page-level extracted values. Department 3 emits
  pairwise comparisons, so one underlying discrepancy can appear in more than
  one finding.
- The sample PDFs contain native text; scanned-image OCR and production
  deployment were not validated in this run.
- Visual-forensics processing ran for the sample PDFs, which contain content
  changes rather than image-level manipulations.
- Ollama runtime detection was exercised on the development machine: the CLI
  was present, but its API service was unreachable. Model discovery and actual
  LLM inference therefore remain unverified against a running runtime.
- The AI backend foundation was verified with mocked runtime responses and
  database-backed API tests. AI uploads do not enter the standard processing
  pipeline, and selected standard documents remain linked rather than copied.
- Multi-stage AI analysis and cancellation were validated with a scripted
  Ollama client and temporary SQLite databases. Citation checks verified
  exact source quotes before findings were persisted. Live inference remains
  unverified because the configured Ollama API service is unreachable.
- PDF reports are saved separately from the existing JSON reports. Tests
  downloaded standard and AI-generated PDFs, checked PDF signatures and
  content types, extracted report text and bookmarks with PyMuPDF, confirmed
  embedded fonts, and rendered long synthetic reports across multiple pages.
- AI chat retrieval and citation filtering, review history, audit logging, and
  run-specific PDF downloads passed API tests with a scripted local model.
- Hardware GPU detection uses `nvidia-smi`; absence of that utility is reported
  as unknown GPU status, not proof that no GPU exists. Model recommendations
  are conservative heuristics and do not guarantee inference compatibility.