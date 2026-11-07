# System Limitations

## OCR Limitations

- OCR accuracy depends on image quality.
- Blurred, rotated, compressed, or low-resolution documents may produce
  extraction errors.
- Handwritten text may not be reliably recognized.
- OCR confidence is not a guarantee of correctness.
- The supplied sample PDFs contain native text. The scanned-image EasyOCR path
  was not validated as part of the end-to-end sample run.

## Visual Forensics Limitations

- Compression and scanning can create visual artifacts.
- Error Level Analysis is a screening technique, not proof of editing.
- Brightness and region inconsistencies can produce false positives.
- Not every manipulation leaves detectable visual traces.

## Contextual Analysis Limitations

- Comparisons depend on the accuracy of extracted fields.
- Different document formats may represent the same information differently.
- Missing or ambiguous labels can reduce comparison accuracy.
- A mismatch does not necessarily indicate fraudulent activity.
- Without `LLM_MODEL` configuration, explanations use the Department 3
  evidence-grounded template fallback; hosted or local model generation was not
  validated in this run.
- Department 3 currently reports mismatches per document pair. A single
  underlying discrepancy can therefore produce multiple related findings in a
  multi-document investigation.

## Dataset Limitations

- Demonstration documents are not representative of every real-world
  document type.
- Artificially manipulated samples may not represent sophisticated
  real-world manipulation techniques.
- The supplied altered samples change document content; they do not establish
  the effectiveness of image-level tamper detection.

## Security and Deployment Limitations

- The prototype uses local file storage.
- The prototype does not currently implement user authentication.
- SQLite is intended for the demonstration workload.
- Uploaded files should be treated as untrusted input.
- Manual dossier-authoring controls are not backed by persistent API data.
  Generated investigation reports are available as downloadable JSON or PDF
  files; PDF does not replace or alter the existing JSON report contract.
- The AI-investigation backend currently supports configuration, runtime
  discovery, source/document linking, AI-only uploads, asynchronous
  multi-stage inference, evidence-checked findings, cancellation, and audit
  events, source-grounded persistent chat, append-only human finding reviews,
  and persisted AI-run PDF export.
- Review names are user-entered and are not authenticated identities because
  the prototype does not implement user authentication or authorization.
- New AI tables are created by SQLAlchemy `create_all`; the project does not
  yet have a versioned database migration workflow for production upgrades.
- Ollama discovery reports the runtime as unavailable when its configured API
  cannot be reached, even if the Ollama executable is installed.
- Hardware profiling uses platform memory APIs and `nvidia-smi`. GPU absence
  cannot be established when NVIDIA tooling is unavailable, and model-fit
  recommendations are heuristics rather than compatibility guarantees.
- AI-only image/scanned-document analysis is not implemented yet; document
  uploads are stored without invoking standard OCR or forensic processing.
  The AI analysis worker falls back to the existing OCR service when saved text
  is unavailable. The fallback path and real scanned-image behavior have not
  been validated against a live local model in this test run.
- Ollama inference and model behavior were tested with a scripted client, not a
  live local model; output quality and real-runtime compatibility remain
  unverified while the configured Ollama service is unreachable.

## Interpretation

Decipher provides automated indicators to support document review.
Its findings must be interpreted in context and verified by a human reviewer.
The system does not independently establish fraud or authenticity.