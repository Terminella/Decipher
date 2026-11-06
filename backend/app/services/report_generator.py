import json
from datetime import datetime, timezone

from ..models import Investigation


def generate_investigation_report(investigation: Investigation) -> dict:
    documents = []

    for document in investigation.documents:
        processing_result = json.loads(
            document.processing_result_json or "{}"
        )
        extracted_information = processing_result.get(
            "extracted_information",
            {},
        )
        visual_forensics = processing_result.get("visual_forensics", {})

        documents.append({
            "document_id": document.id,
            "filename": document.filename,
            "sha256": document.sha256,
            "document_type": document.doc_type,
            "processing_status": document.processing_status,
            "uploaded_at": (
                document.uploaded_at.isoformat()
                if document.uploaded_at else None
            ),
            "extracted_fields": [
                {
                    "field_name": field.field_name,
                    "field_value": field.field_value,
                    "confidence": field.confidence,
                    "page_number": field.page_number,
                    "bbox": (
                        json.loads(field.bbox_json)
                        if field.bbox_json else None
                    ),
                }
                for field in document.extracted_fields
            ],
            "page_count": extracted_information.get(
                "page_count",
                len(extracted_information.get("pages", [])),
            ),
            "pages": extracted_information.get("pages", []),
            "visual_forensics": visual_forensics,
            "processing_warnings": processing_result.get("warnings", []),
        })

    findings = [
        {
            "finding_id": finding.id,
            "title": finding.title,
            "anomaly_type": finding.anomaly_type,
            "classification": finding.classification,
            "severity": finding.severity,
            "priority_score": finding.priority_score,
            "field_name": finding.field_name,
            "explanation": finding.explanation,
            "evidence": (
                json.loads(finding.evidence_json)
                if finding.evidence_json else None
            ),
        }
        for finding in investigation.findings
    ]

    severity_counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
    }

    for finding in findings:
        severity = str(finding["severity"] or "").lower()
        if severity in severity_counts:
            severity_counts[severity] += 1

    visual_findings = [
        {
            "document_id": document["document_id"],
            "filename": document["filename"],
            "page": page.get("page_number"),
            "observations": page.get("observations", []),
        }
        for document in documents
        for page in document["visual_forensics"].get("pages", [])
        if page.get("observations")
    ]
    contextual_findings = [
        finding
        for finding in findings
        if finding["anomaly_type"] != "visual_anomaly_on_critical_field"
    ]
    traceability = [
        {
            "finding_id": finding["finding_id"],
            "evidence": finding["evidence"],
        }
        for finding in findings
    ]
    limitations = list(dict.fromkeys(
        warning
        for document in documents
        for warning in document["processing_warnings"]
    ))
    limitations.append(
        "Automated findings are indicators for human review, not proof "
        "of fraud or manipulation."
    )

    return {
        "report_title": "Decipher Investigation Dossier",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "investigation": {
            "id": investigation.id,
            "title": investigation.title,
            "description": investigation.description,
            "status": investigation.status,
            "created_at": (
                investigation.created_at.isoformat()
                if investigation.created_at else None
            ),
        },
        "summary": {
            "document_count": len(documents),
            "finding_count": len(findings),
            "severity_counts": severity_counts,
        },
        "sections": {
            "document_overview": [
                {
                    "document_id": document["document_id"],
                    "filename": document["filename"],
                    "document_type": document["document_type"],
                    "sha256": document["sha256"],
                    "processing_status": document["processing_status"],
                    "uploaded_at": document["uploaded_at"],
                }
                for document in documents
            ],
            "extracted_information": [
                {
                    "document_id": document["document_id"],
                    "filename": document["filename"],
                    "fields": document["extracted_fields"],
                    "pages": document["pages"],
                }
                for document in documents
            ],
            "contextual_analysis": contextual_findings,
            "visual_forensic_findings": visual_findings,
            "evidence_and_traceability": traceability,
            "investigation_summary": {
                "findings": findings,
                "limitations": limitations,
            },
        },
        "documents": documents,
        "findings": findings,
        "limitations": limitations,
        "disclaimer": (
            "Automated findings are indicators for review, not "
            "conclusive proof of document fraud or manipulation."
        ),
    }