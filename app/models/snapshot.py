from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, final

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.document import ElectronicDocument


@final
class CompanySnapshot(Base):
    __tablename__ = "company_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ruc: Mapped[str] = mapped_column(String(11), nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commercial_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ubigeo: Mapped[str | None] = mapped_column(String(6), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    documents: Mapped[list[ElectronicDocument]] = relationship(back_populates="company_snapshot")


@final
class CustomerSnapshot(Base):
    __tablename__ = "customer_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_type: Mapped[str] = mapped_column(String(2), nullable=False)
    document_number: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ubigeo: Mapped[str | None] = mapped_column(String(6), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    documents: Mapped[list[ElectronicDocument]] = relationship(back_populates="customer_snapshot")
