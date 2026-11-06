
"""FastAPI routes for Department 4."""

from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
    Query
)

from ..services.pipeline import process_document


router = APIRouter(
    prefix="/documents",
    tags=["Documents - Department 4"]
)


ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp"
}

MAX_FILE_SIZE = 20 * 1024 * 1024


@router.post("/analyze")
async def analyze_document_endpoint(

    file: UploadFile = File(...),

    force_ocr: bool = Query(False)

):

    suffix = Path(
        file.filename or ""
    ).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:

        raise HTTPException(
            status_code=400,
            detail="Unsupported document format."
        )

    content = await file.read()

    if not content:

        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty."
        )

    if len(content) > MAX_FILE_SIZE:

        raise HTTPException(
            status_code=413,
            detail="File exceeds the 20 MB limit."
        )

    temp_path = None

    try:

        with NamedTemporaryFile(
            delete=False,
            suffix=suffix
        ) as temp:

            temp.write(content)

            temp_path = temp.name

        result = process_document(
            temp_path,
            force_ocr=force_ocr
        )

        result["filename"] = file.filename

        return result

    except RuntimeError as exc:

        raise HTTPException(
            status_code=503,
            detail=str(exc)
        ) from exc

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Document processing failed: {exc}"
        ) from exc

    finally:

        if temp_path and os.path.exists(temp_path):

            os.remove(temp_path)


@router.get("/health")
async def department4_health():

    return {

        "department": (
            "Department 4 - OCR, "
            "Document Processing and Computer Vision"
        ),

        "status": "available",

        "supported_extensions": sorted(
            ALLOWED_EXTENSIONS
        )
    }
