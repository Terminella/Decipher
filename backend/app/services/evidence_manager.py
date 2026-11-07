import hashlib
import uuid
from pathlib import Path
from typing import Union

from fastapi import UploadFile

from ..config import settings


class UploadTooLargeError(ValueError):
    pass


class EvidenceManager:
    def __init__(self):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.report_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        file: UploadFile,
        investigation_id: Union[int, str],
    ) -> tuple[str, str]:
        original_name = Path(file.filename or "document").name
        suffix = Path(original_name).suffix.lower()

        safe_name = f"{uuid.uuid4().hex}{suffix}"

        investigation_dir = (
            settings.upload_dir / str(investigation_id)
        )
        investigation_dir.mkdir(parents=True, exist_ok=True)

        destination = investigation_dir / safe_name

        content = await file.read()

        if not content:
            raise ValueError("Uploaded file is empty.")

        if len(content) > settings.max_upload_size:
            raise UploadTooLargeError(
                f"File exceeds the {settings.max_upload_size // (1024 * 1024)} MB limit."
            )

        destination.write_bytes(content)

        digest = hashlib.sha256(content).hexdigest()

        return str(destination.resolve()), digest

    def get_document_path(self, storage_path: str) -> Path:
        path = Path(storage_path).resolve()
        upload_root = settings.upload_dir.resolve()

        if upload_root not in path.parents:
            raise ValueError("Invalid document storage path.")

        if not path.exists():
            raise FileNotFoundError("Stored document does not exist.")

        return path

    def save_report(
        self,
        investigation_id: Union[int, str],
        filename: str,
        content: bytes,
    ) -> str:
        report_dir = settings.report_dir / str(investigation_id)
        report_dir.mkdir(parents=True, exist_ok=True)

        destination = report_dir / filename
        destination.write_bytes(content)

        return str(destination.resolve())

    def get_report_path(self, file_path: str) -> Path:
        path = Path(file_path).resolve()
        report_root = settings.report_dir.resolve()

        if report_root not in path.parents:
            raise ValueError("Invalid report path.")

        if not path.exists():
            raise FileNotFoundError("Report does not exist.")

        return path

evidence_manager = EvidenceManager()