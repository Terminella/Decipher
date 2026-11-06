# Decipher Synthetic Sample Documents

This folder contains 30 fictional PDF records for development and demonstration.

- `genuine/`: 15 mutually consistent synthetic invoices, purchase orders and payment confirmations.
- `manipulated/`: 15 altered counterparts, with intentional amount, supplier and date discrepancies.
- `manifest.json`: metadata, investigation grouping and expected findings.

All names, identifiers, dates and amounts are fictional. Do not use these documents as real financial, procurement, tax or legal records.

Suggested use:
1. Run OCR and visual-forensics checks on the PDFs.
2. Group documents by `investigation_id`.
3. Compare invoice, purchase-order and payment fields in contextual correlation.
4. Compare observed results against `expected_cross_document_findings` in the manifest.

Note: The altered PDFs are synthetic test fixtures. They demonstrate content inconsistencies; they are not intended to represent sophisticated image-level tampering.
