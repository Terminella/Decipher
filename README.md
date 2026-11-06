# Decipher

## Project architecture

```text
Decipher/
├── README.md
├── .gitignore
├── .env.example
├── docs/
│   ├── ARCHITECTURE.md
│   ├── LIMITATIONS.md
│   └── DEVELOPMENT_STATUS.md
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── pages/
│       │   ├── UploadPage.jsx
│       │   ├── InvestigationPage.jsx
│       │   └── DossierPage.jsx
│       ├── components/
│       │   ├── DocumentViewer.jsx
│       │   ├── DocumentSelector.jsx
│       │   ├── FindingCard.jsx
│       │   ├── AuditTrailModal.jsx
│       │   └── StatusPill.jsx
│       ├── services/
│       │   └── api.js
│       └── styles/
│           └── index.css
├── backend/
│   ├── requirements.txt
│   ├── data/
│   │   └── .gitkeep
│   ├── storage/
│   │   └── .gitkeep
│   ├── generated/
│   │   └── .gitkeep
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── investigations.py
│   │   │   ├── documents.py
│   │   │   └── reports.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── pipeline.py
│   │       ├── classifier.py
│   │       ├── ocr_service.py
│   │       ├── visual_forensics.py
│   │       ├── correlation.py
│   │       ├── evidence_manager.py
│   │       ├── normalization.py
│   │       ├── llm_service.py
│   │       └── report_generator.py
|   |       └── contextual_schemas.py
|   |       └── run_demo.py
│   └── tests/
│       ├── test_visual_forensics.py
│       ├── test_correlation.py
│       └── test_api.py
|       └── test_normalization.py
|       └── test_llm_services.py
|       └── test_contextual_schemas.py
├── sample_documents/
│   ├── genuine/
│   ├── manipulated/
│   └── manifest.json
|   └── README.md 
└── scripts/
    ├── start-backend.ps1
    └── start-frontend.ps1
```
