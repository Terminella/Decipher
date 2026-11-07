from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="created", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    documents = relationship(
        "Document",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )

    findings = relationship(
        "Finding",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )

    reports = relationship(
        "Report",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )

    analysis_runs = relationship(
        "AnalysisRun",
        back_populates="investigation",
        cascade="all, delete-orphan",
    )


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)

    investigation_id = Column(
        Integer,
        ForeignKey("investigations.id"),
        nullable=False,
        index=True,
    )

    filename = Column(String(255), nullable=False)
    storage_path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)

    doc_type = Column(String(100), nullable=True)
    processing_status = Column(
        String(50),
        default="uploaded",
        nullable=False,
    )

    processing_result_json = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=utc_now)

    investigation = relationship(
        "Investigation",
        back_populates="documents",
    )

    extracted_fields = relationship(
        "ExtractedField",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    findings = relationship(
        "Finding",
        back_populates="document",
    )

    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "sha256",
            name="uq_investigation_document_hash",
        ),
    )


class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(Integer, primary_key=True, index=True)

    document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=False,
        index=True,
    )

    field_name = Column(String(255), nullable=False)
    field_value = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    page_number = Column(Integer, nullable=True)
    bbox_json = Column(Text, nullable=True)

    document = relationship(
        "Document",
        back_populates="extracted_fields",
    )


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)

    investigation_id = Column(
        Integer,
        ForeignKey("investigations.id"),
        nullable=False,
        index=True,
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id"),
        nullable=True,
        index=True,
    )

    anomaly_type = Column(String(100), nullable=False)
    classification = Column(String(100), nullable=True)
    severity = Column(String(50), nullable=True)
    priority_score = Column(Float, nullable=True)

    title = Column(String(255), nullable=False)
    field_name = Column(String(255), nullable=True)
    explanation = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now)

    investigation = relationship(
        "Investigation",
        back_populates="findings",
    )

    document = relationship(
        "Document",
        back_populates="findings",
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    investigation_id = Column(
        Integer,
        ForeignKey("investigations.id"),
        nullable=False,
        index=True,
    )
    documents_analyzed = Column(Integer, nullable=False)
    findings_count = Column(Integer, nullable=False)
    result_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    investigation = relationship(
        "Investigation",
        back_populates="analysis_runs",
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)

    investigation_id = Column(
        Integer,
        ForeignKey("investigations.id"),
        nullable=False,
        index=True,
    )

    format = Column(String(20), default="json", nullable=False)
    file_path = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    investigation = relationship(
        "Investigation",
        back_populates="reports",
    )


class AIInvestigation(Base):
    __tablename__ = "ai_investigations"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    custom_instructions = Column(Text, nullable=True)
    selected_model = Column(String(255), nullable=True)
    analysis_depth = Column(String(50), nullable=False, default="quick")
    status = Column(String(50), nullable=False, default="created")
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    sources = relationship(
        "AIInvestigationSource",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )
    documents = relationship(
        "AIInvestigationDocument",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )
    analysis_runs = relationship(
        "AIAnalysisRun",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )
    chat_messages = relationship(
        "AIChatMessage",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship(
        "AIAuditLog",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )
    reports = relationship(
        "AIReport",
        back_populates="ai_investigation",
        cascade="all, delete-orphan",
    )


class AIInvestigationSource(Base):
    __tablename__ = "ai_investigation_sources"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    investigation_id = Column(
        Integer,
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    linked_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="sources",
    )
    investigation = relationship("Investigation")

    __table_args__ = (
        UniqueConstraint(
            "ai_investigation_id",
            "investigation_id",
            name="uq_ai_investigation_source",
        ),
    )


class AIInvestigationDocument(Base):
    __tablename__ = "ai_investigation_documents"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    doc_type = Column(String(100), nullable=True)
    storage_path = Column(Text, nullable=True)
    source_type = Column(String(50), nullable=False)
    processing_status = Column(String(50), nullable=False, default="uploaded")
    added_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="documents",
    )
    document = relationship("Document")
    evidence_links = relationship(
        "AIEvidenceLink",
        back_populates="ai_document",
    )

    __table_args__ = (
        UniqueConstraint(
            "ai_investigation_id",
            "document_id",
            name="uq_ai_investigation_document",
        ),
    )


class AIAnalysisRun(Base):
    __tablename__ = "ai_analysis_runs"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(50), nullable=False, default="queued")
    stage = Column(String(100), nullable=True)
    progress = Column(Integer, nullable=False, default=0)
    model_name = Column(String(255), nullable=True)
    model_version = Column(String(100), nullable=True)
    prompt_version = Column(String(100), nullable=True)
    configuration_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="analysis_runs",
    )
    findings = relationship(
        "AIFinding",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )


class AIFinding(Base):
    __tablename__ = "ai_findings"

    id = Column(Integer, primary_key=True, index=True)
    analysis_run_id = Column(
        Integer,
        ForeignKey("ai_analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_key = Column(String(128), nullable=False)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=True)
    severity = Column(String(50), nullable=False, default="unrated")
    confidence = Column(Float, nullable=True)
    description = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)
    alternative_explanations_json = Column(Text, nullable=False, default="[]")
    recommended_action = Column(Text, nullable=True)
    review_status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    analysis_run = relationship(
        "AIAnalysisRun",
        back_populates="findings",
    )
    evidence_links = relationship(
        "AIEvidenceLink",
        back_populates="ai_finding",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "AIReview",
        back_populates="ai_finding",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "finding_key",
            name="uq_ai_finding_run_key",
        ),
    )


class AIEvidenceLink(Base):
    __tablename__ = "ai_evidence_links"

    id = Column(Integer, primary_key=True, index=True)
    ai_finding_id = Column(
        Integer,
        ForeignKey("ai_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_document_id = Column(
        Integer,
        ForeignKey("ai_investigation_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    standard_finding_id = Column(
        Integer,
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type = Column(String(50), nullable=False)
    page_number = Column(Integer, nullable=True)
    field_name = Column(String(255), nullable=True)
    quoted_text = Column(Text, nullable=True)
    verification_status = Column(String(50), nullable=False, default="unverified")

    ai_finding = relationship(
        "AIFinding",
        back_populates="evidence_links",
    )
    ai_document = relationship(
        "AIInvestigationDocument",
        back_populates="evidence_links",
    )
    standard_finding = relationship("Finding")


class AIReview(Base):
    __tablename__ = "ai_reviews"

    id = Column(Integer, primary_key=True, index=True)
    ai_finding_id = Column(
        Integer,
        ForeignKey("ai_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review_status = Column(String(50), nullable=False)
    reviewer = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_finding = relationship(
        "AIFinding",
        back_populates="reviews",
    )


class AIChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id = Column(
        Integer,
        ForeignKey("ai_analysis_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="chat_messages",
    )


class AIReport(Base):
    __tablename__ = "ai_reports"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id = Column(
        Integer,
        ForeignKey("ai_analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    format = Column(String(20), nullable=False, default="pdf")
    file_path = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="reports",
    )
    analysis_run = relationship("AIAnalysisRun")


class AIAuditLog(Base):
    __tablename__ = "ai_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    ai_investigation_id = Column(
        Integer,
        ForeignKey("ai_investigations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_run_id = Column(
        Integer,
        ForeignKey("ai_analysis_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(100), nullable=False)
    details_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    ai_investigation = relationship(
        "AIInvestigation",
        back_populates="audit_logs",
    )