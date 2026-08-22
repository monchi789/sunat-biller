from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING, final

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampUpdateMixin

if TYPE_CHECKING:
    from app.models.audit import AuditLog
    from app.models.company import Company
    from app.models.daily_summary import DailySummaryItem
    from app.models.document_file import DocumentFile
    from app.models.document_item import (
        DocumentInstallment,
        DocumentItem,
        DocumentReference,
    )
    from app.models.document_series import DocumentSeries
    from app.models.idempotency import IdempotencyKey
    from app.models.snapshot import CompanySnapshot, CustomerSnapshot
    from app.models.sunat_submission import SunatSubmission
    from app.models.voided_document import VoidedDocumentItem


@final
class ElectronicDocument(Base, SoftDeleteMixin, TimestampUpdateMixin):
    __tablename__ = "electronic_documents"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "document_type", "series", "number",
            name="uq_electronic_document",
        ),
        Index("ix_electronic_documents_company_status", "company_id", "status"),
        Index("ix_electronic_documents_sunat_status", "sunat_status"),
        Index("ix_electronic_documents_company_issue_date", "company_id", "issue_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_series.id"), nullable=False
    )
    company_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_snapshots.id"), nullable=False
    )
    customer_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_snapshots.id"), nullable=True
    )

    document_type: Mapped[str] = mapped_column(String(2), nullable=False)
    series: Mapped[str] = mapped_column(String(4), nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    issue_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    operation_type: Mapped[str] = mapped_column(String(4), nullable=False, default="0101")
    payment_terms: Mapped[str] = mapped_column(String(10), nullable=False, default="Contado")

    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    taxable_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    exempt_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    unaffected_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    export_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    free_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    igv_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    isc_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    icbper_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    other_tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False)

    sunat_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sunat_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sunat_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    xml_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    company: Mapped[Company] = relationship(back_populates="documents")
    series_rel: Mapped[DocumentSeries] = relationship(
        back_populates="documents", foreign_keys=[series_id]
    )
    company_snapshot: Mapped[CompanySnapshot] = relationship(back_populates="documents")
    customer_snapshot: Mapped[CustomerSnapshot | None] = relationship(
        back_populates="documents"
    )
    items: Mapped[list[DocumentItem]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    installments: Mapped[list[DocumentInstallment]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    references: Mapped[list[DocumentReference]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    sunat_submissions: Mapped[list[SunatSubmission]] = relationship(back_populates="document")
    files: Mapped[list[DocumentFile]] = relationship(back_populates="document")
    audit_logs: Mapped[list[AuditLog]] = relationship(back_populates="document")
    daily_summary_items: Mapped[list[DailySummaryItem]] = relationship(back_populates="document")
    voided_document_items: Mapped[list[VoidedDocumentItem]] = relationship(
        back_populates="document"
    )
    idempotency_key: Mapped[IdempotencyKey | None] = relationship(back_populates="document")
