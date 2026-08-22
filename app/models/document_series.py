from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, final

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampUpdateMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.document import ElectronicDocument


@final
class DocumentSeries(Base, TimestampUpdateMixin):
    __tablename__ = "document_series"
    __table_args__ = (
        UniqueConstraint("company_id", "document_type", "series", name="uq_document_series"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    document_type: Mapped[str] = mapped_column(String(2), nullable=False)
    series: Mapped[str] = mapped_column(String(4), nullable=False)
    current_number: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    company: Mapped[Company] = relationship(back_populates="document_series")
    documents: Mapped[list[ElectronicDocument]] = relationship(back_populates="series_rel")
