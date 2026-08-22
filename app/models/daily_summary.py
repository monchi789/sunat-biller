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
class DailySummary(Base, TimestampMixin):
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("company_id", "identifier", name="uq_daily_summary"),
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
    company: Mapped[Company] = relationship(back_populates="daily_summaries")
    items: Mapped[list[DailySummaryItem]] = relationship(
        back_populates="daily_summary", cascade="all, delete-orphan"
    )


@final
class DailySummaryItem(Base, TimestampMixin):
    __tablename__ = "daily_summary_items"
    __table_args__ = (
        UniqueConstraint("daily_summary_id", "document_id", name="uq_daily_summary_item"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    daily_summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_summaries.id"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    item_status: Mapped[str] = mapped_column(String(2), nullable=False)
    sunat_item_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    daily_summary: Mapped[DailySummary] = relationship(back_populates="items")
    document: Mapped[ElectronicDocument] = relationship(back_populates="daily_summary_items")
