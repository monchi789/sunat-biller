from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, final

from sqlalchemy import (
    BigInteger,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import ElectronicDocument


@final
class DocumentItem(Base, TimestampMixin):
    __tablename__ = "document_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    product_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(3), nullable=False)

    unit_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    igv_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    isc_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    icbper_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    other_tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    tax_affectation: Mapped[str] = mapped_column(String(2), nullable=False)
    price_type: Mapped[str] = mapped_column(String(2), nullable=False)

    # Relationships
    document: Mapped[ElectronicDocument] = relationship(back_populates="items")


@final
class DocumentInstallment(Base, TimestampMixin):
    __tablename__ = "document_installments"
    __table_args__ = (
        UniqueConstraint("document_id", "installment_number", name="uq_document_installment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    installment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    # Relationships
    document: Mapped[ElectronicDocument] = relationship(back_populates="installments")


@final
class DocumentReference(Base):
    __tablename__ = "document_references"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    reference_document_type: Mapped[str] = mapped_column(String(2), nullable=False)
    reference_series: Mapped[str] = mapped_column(String(4), nullable=False)
    reference_number: Mapped[int] = mapped_column(BigInteger, nullable=False)

    reason_code: Mapped[str] = mapped_column(String(10), nullable=False)
    reason_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    document: Mapped[ElectronicDocument] = relationship(back_populates="references")
