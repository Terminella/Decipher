from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    Float,
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