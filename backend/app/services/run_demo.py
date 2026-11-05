"""
Quick demo of the contextual-analysis module (Department 3) - no other part of the project needed.
Run from the backend/ folder:   python run_demo.py
"""
from app.services.correlation import run_contextual_analysis


def field(fid, label, ftype, value, conf, bbox=None):
    return {"field_id": fid, "label": label, "field_type": ftype, "value": value,
            "ocr_confidence": conf, "bbox": bbox}


def box(x0, y0, x1, y1):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


# What Dept 4 (OCR + visual forensics) would hand over: fields with confidence + location,
# and suspicious regions found by the visual module.
investigation = {
    "investigation_id": "DEMO-1",
    "documents": [
        {"document_id": "A", "filename": "application_form.pdf", "fields": [
            field("a1", "Name of Applicant", "name", "Rahul Kumar Sharma", 0.97),
            field("a2", "Date of Birth", "date", "12/03/1990", 0.96, box(100, 140, 200, 160)),
            field("a3", "PAN", "id_number", "ABCDE1234F", 0.98),
        ]},
        {"document_id": "B", "filename": "id_proof.pdf",
         "fields": [
             field("b1", "Name", "name", "RAHUL K SHARMA", 0.96),
             field("b2", "DOB", "date", "12/03/1991", 0.95, box(50, 120, 150, 140)),
             field("b3", "PAN", "id_number", "ABCDE1Z34F", 0.62),
         ],
         "visual_anomalies": [{"anomaly_id": "v1", "kind": "ela_hotspot", "page": 1,
                               "score": 0.8, "bbox": box(45, 115, 160, 145)}]},
    ],
}

# use_llm=False -> template explanations, no internet, no API quota.
# After setting LLM_MODEL (see llm_service.py) you can switch it to True.
result = run_contextual_analysis(investigation, use_llm=False)

print(f"{result.documents_analyzed} documents, {result.fields_analyzed} fields, {len(result.findings)} findings\n")
for f in result.findings:
    print(f"[{f.severity.value.upper()}] {f.title}  ->  {f.classification.value}, confidence {f.confidence}")
    print("   ", f.explanation, "\n")
