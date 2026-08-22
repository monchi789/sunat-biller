from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, final

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.document import ElectronicDocument


@final
class VoidedDocument(Base, TimestampMixin):
    __tablename__ = "voided_documents"
    __table_args__ = (
        UniqueConstraint("company_id", "identifier", name="uq_voided_document"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )

    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    identifier: Mapped[str] = mapped_column(String(50), nullable=False)

    ticket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    sunat_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sunat_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    company: Mapped[Company] = relationship(back_populates="voided_documents")
    items: Mapped[list[VoidedDocumentItem]] = relationship(
        back_populates="voided_document", cascade="all, delete-orphan"
    )


@final
class VoidedDocumentItem(Base, TimestampMixin):
    __tablename__ = "voided_document_items"
    __table_args__ = (
        UniqueConstraint("voided_document_id", "document_id", name="uq_voided_document_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voided_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voided_documents.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    voided_document: Mapped[VoidedDocument] = relationship(back_populates="items")
    document: Mapped[ElectronicDocument] = relationship(back_populates="voided_document_items")
