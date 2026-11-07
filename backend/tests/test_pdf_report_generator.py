import pymupdf

from app.services.pdf_report_generator import (
    generate_ai_investigation_pdf,
    generate_investigation_pdf,
)


def test_ai_pdf_prioritizes_run_outcome_and_verified_evidence():
    report_data = {
        "generated_at": "2026-11-07T10:35:00+00:00",
        "investigation": {
            "id": 6,
            "title": "CASE-001 invoice comparison",
            "description": "Compare the genuine and manipulated invoices.",
            "analysis_depth": "quick",
        },
        "documents": [
            {
                "filename": "CASE-001_invoice_genuine.pdf",
                "sha256": "a" * 64,
                "source_type": "ai_upload",
            },
            {
                "filename": "CASE-001_invoice_manipulated.pdf",
                "sha256": "b" * 64,
                "source_type": "ai_upload",
            },
        ],
        "run": {
            "id": 7,
            "status": "completed",
            "model": "qwen3.5:4b",
            "model_version": "0.40.14",
            "prompt_version": "decipher-investigation-v1",
            "completed_at": "2026-11-07T10:34:30+00:00",
            "result": {
                "evidence_retrieval": {"sha256_verified": True},
                "structured_findings": {"accepted_count": 1, "rejected_count": 0},
            },
        },
        "findings": [
            {
                "title": "Invoice total amount discrepancy",
                "category": "Data integrity",
                "severity": "medium",
                "confidence": 0.95,
                "description": "The manipulated invoice total differs from the genuine invoice.",
                "reasoning": "Both source documents state their totals.",
                "recommended_action": "Verify the amount against the purchase order.",
                "review_status": "pending",
                "evidence": [
                    {
                        "filename": "CASE-001_invoice_genuine.pdf",
                        "page_number": 1,
                        "quote": "Total amount INR 48,500.00",
                        "verification_status": "verified",
                    },
                    {
                        "filename": "CASE-001_invoice_manipulated.pdf",
                        "page_number": 1,
                        "quote": "Total amount INR 61,000.00",
                        "verification_status": "verified",
                    },
                ],
            },
        ],
    }

    content = generate_ai_investigation_pdf(report_data)
    pdf = pymupdf.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)

    assert content.startswith(b"%PDF-")
    assert len(pdf) <= 2
    assert "Contents" not in text
    assert "Investigation overview" in pdf[0].get_text()
    assert "CASE-001_invoice_genuine.pdf" in text
    assert "CASE-001_invoice_manipulated.pdf" in text
    assert "Invoice total amount discrepancy" in text
    assert "INR 48,500.00" in text
    assert "INR 61,000.00" in text
    pdf.close()


def test_ai_pdf_explains_when_model_candidates_fail_source_verification():
    report_data = {
        "generated_at": "2026-11-07T10:35:00+00:00",
        "investigation": {"id": 6, "title": "CASE-001 invoice comparison"},
        "run": {
            "id": 6,
            "status": "completed",
            "model": "qwen3.5:4b",
            "result": {
                "structured_findings": {"accepted_count": 0, "rejected_count": 3},
            },
        },
        "findings": [],
    }

    content = generate_ai_investigation_pdf(report_data)
    pdf = pymupdf.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)

    assert "3 candidate(s) were excluded" in text
    assert "not presented as verified findings" in " ".join(text.split())
    pdf.close()


def test_standard_pdf_has_contents_bookmarks_unicode_and_handles_long_reports():
    findings = [
        {
            "finding_id": index,
            "title": f"Finding {index} – revisión de importe",
            "anomaly_type": "amount_mismatch",
            "classification": "financial",
            "severity": "medium" if index % 2 else "high",
            "priority_score": index / 10,
            "field_name": "invoice_total",
            "explanation": (
                "The source record contains Café & Co. — "
                + ("a detailed explanation with wrapped content. " * 18)
            ),
            "evidence": [{
                "document_id": index,
                "filename": f"source-{index}.pdf",
                "page": 1,
                "value": "Café & Co. total: INR 1,000",
            }],
        }
        for index in range(1, 36)
    ]
    visual_field_finding = {
        "finding_id": 36,
        "title": "Visual field region observation",
        "anomaly_type": "visual_anomaly_on_critical_field",
        "classification": "visual",
        "severity": "low",
        "explanation": "Visual indicator associated with an extracted critical field.",
        "evidence": [{"document_id": 1, "page": 1, "value": "Café logo area"}],
    }
    report_data = {
        "report_title": "Decipher Investigation Dossier · Café & Co.",
        "generated_at": "2026-11-07T08:00:00+00:00",
        "investigation": {
            "id": 42,
            "title": "Café & Co. document review",
            "description": "Review of long records and Unicode text.",
            "status": "completed",
        },
        "summary": {
            "document_count": 35,
            "finding_count": len(findings) + 1,
            "severity_counts": {"high": 17, "medium": 18, "low": 0, "info": 0},
        },
        "sections": {
            "document_overview": [{
                "filename": f"invoice-{index}.pdf",
                "document_type": "invoice",
                "processing_status": "completed",
                "sha256": f"{index:064x}",
                "uploaded_at": "2026-11-07",
            } for index in range(1, 36)],
            "extracted_information": [{
                "filename": "invoice-1.pdf",
                "fields": [{
                    "field_name": f"field_{index}",
                    "field_value": "value & detail — " + ("long value " * 30),
                    "confidence": 0.9,
                    "page_number": index,
                } for index in range(1, 45)],
            }],
            "contextual_analysis": findings,
            "visual_forensic_findings": [{
                "filename": "invoice-1.pdf",
                "page": 1,
                "observations": ["Café logo image differs from the reference."],
            }],
            "evidence_and_traceability": [
                {"finding_id": finding["finding_id"], "evidence": finding["evidence"]}
                for finding in findings
            ] + [{
                "finding_id": visual_field_finding["finding_id"],
                "evidence": visual_field_finding["evidence"],
            }],
        },
        "findings": findings + [visual_field_finding],
        "limitations": ["Review all discrepancies with source owners."],
        "disclaimer": "Automated findings are indicators for review.",
    }

    content = generate_investigation_pdf(report_data)
    pdf = pymupdf.open(stream=content, filetype="pdf")
    text = "\n".join(page.get_text() for page in pdf)

    assert content.startswith(b"%PDF-")
    assert len(pdf) > 5
    assert "Contents" in text
    assert "Executive summary" in text
    assert "Evidence and traceability" in text
    assert "Visual field region observation" in text
    assert "Café" in text
    assert any(item[1] == "Document inventory and integrity" for item in pdf.get_toc())
    embedded_fonts = [
        pdf.extract_font(font[0])[3]
        for page in pdf
        for font in page.get_fonts(full=True)
        if font[0] > 0
    ]
    assert any(embedded_fonts)
    pdf.close()
