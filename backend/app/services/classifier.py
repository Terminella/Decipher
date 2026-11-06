
import re


DOCUMENT_TYPES = {

    "pan_card": [
        "permanent account number",
        "income tax department"
    ],

    "aadhaar_card": [
        "unique identification authority",
        "uidai",
        "aadhaar"
    ],

    "bank_statement": [
        "account statement",
        "opening balance",
        "closing balance",
        "withdrawal",
        "deposit"
    ],

    "invoice": [
        "invoice",
        "invoice number",
        "total amount",
        "payment terms"
    ],

    "purchase_order": [
        "purchase order",
        "approved total",
        "order date",
        "delivery terms"
    ],

    "payment_confirmation": [
        "payment confirmation",
        "transaction id",
        "amount transferred",
        "payer",
        "payee"
    ],

    "salary_slip": [
        "salary slip",
        "pay slip",
        "basic salary",
        "gross salary",
        "net pay"
    ],

    "income_certificate": [
        "income certificate",
        "annual income",
        "tehsildar"
    ],

    "application_form": [
        "application form",
        "applicant name",
        "declaration"
    ]
}


def classify_document(text):

    text = re.sub(
        r"\s+",
        " ",
        text.lower()
    )

    scores = {}

    priority = [
        "invoice",
        "purchase_order",
        "payment_confirmation",
        *(
            document_type
            for document_type in DOCUMENT_TYPES
            if document_type not in {
                "invoice",
                "purchase_order",
                "payment_confirmation",
            }
        ),
    ]

    for document_type in priority:
        keywords = DOCUMENT_TYPES[document_type]

        matched = [
            keyword
            for keyword in keywords
            if keyword in text
        ]

        scores[document_type] = {
            "score": len(matched),
            "matched_keywords": matched
        }

    best_type = max(
        scores,
        key=lambda key: scores[key]["score"]
    )

    best_score = scores[best_type]["score"]

    if best_score == 0:

        return {
            "document_type": "unknown",
            "confidence": 0.0,
            "matched_keywords": []
        }

    confidence = min(
        0.95,
        0.45 + 0.12 * best_score
    )

    return {

        "document_type": best_type,

        "confidence": round(
            confidence,
            2
        ),

        "matched_keywords": (
            scores[best_type]["matched_keywords"]
        ),

        "all_scores": scores
    }
