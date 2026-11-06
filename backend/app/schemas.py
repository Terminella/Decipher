from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class InvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None


class InvestigationRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: int
    investigation_id: int
    filename: str
    doc_type: Optional[str]
    processing_status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractedFieldRead(BaseModel):
    id: int
    document_id: int
    field_name: str
    field_value: Optional[str]
    confidence: Optional[float]
    page_number: Optional[int]
    bbox_json: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class FindingRead(BaseModel):
    id: int
    investigation_id: int
    document_id: Optional[int]
    anomaly_type: str
    classification: Optional[str]
    severity: Optional[str]
    priority_score: Optional[float]
    title: str
    field_name: Optional[str]
    explanation: Optional[str]
    evidence_json: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvestigationDetail(InvestigationRead):
    documents: list[DocumentRead] = Field(default_factory=list)
    findings: list[FindingRead] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    force_ocr: bool = False


class AnalysisResponse(BaseModel):
    document_id: int
    filename: str
    processing_status: str
    result: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str