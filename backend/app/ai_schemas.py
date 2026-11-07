from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AIInvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=8000)
    selected_model: Optional[str] = Field(default=None, max_length=255)
    analysis_depth: Literal["quick", "standard", "deep"] = "quick"

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title must not be blank.")
        return value


class AIInvestigationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    custom_instructions: Optional[str] = Field(default=None, max_length=8000)
    selected_model: Optional[str] = Field(default=None, max_length=255)
    analysis_depth: Optional[Literal["quick", "standard", "deep"]] = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Title must not be blank.")
        return value


class AIInvestigationDocumentSelection(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def document_ids_must_be_unique(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Document IDs must be unique.")
        return self


class AIAnalysisRequest(BaseModel):
    model: Optional[str] = Field(default=None, max_length=255)
    document_ids: Optional[list[int]] = Field(default=None, max_length=20)
    standard_finding_ids: list[int] = Field(default_factory=list, max_length=100)
    objective: Optional[str] = Field(default=None, max_length=4000)
    cross_document_analysis: bool = True
    entity_resolution: bool = True
    timeline_analysis: bool = True
    financial_correlation: bool = True

    @model_validator(mode="after")
    def selected_ids_must_be_unique(self):
        if self.document_ids is not None and (
            len(set(self.document_ids)) != len(self.document_ids)
        ):
            raise ValueError("Document IDs must be unique.")
        if len(set(self.standard_finding_ids)) != len(self.standard_finding_ids):
            raise ValueError("Standard finding IDs must be unique.")
        return self


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message must not be blank.")
        return value


class AIFindingReviewRequest(BaseModel):
    review_status: Literal["accepted", "rejected", "needs_review"]
    reviewer: Optional[str] = Field(default=None, max_length=255)
    comment: Optional[str] = Field(default=None, max_length=4000)

    @field_validator("reviewer", "comment")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AIInvestigationRead(BaseModel):
    id: int
    title: str
    description: Optional[str]
    custom_instructions: Optional[str]
    selected_model: Optional[str]
    analysis_depth: str
    status: str

    model_config = ConfigDict(from_attributes=True)
