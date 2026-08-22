from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, final

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company


@final
class DigitalCertificate(Base, SoftDeleteMixin, TimestampMixin):
    __tablename__ = "digital_certificates"
    __table_args__ = (
        Index(
            "ix_digital_certificates_company_active",
            "company_id",
            unique=True,
            postgresql_where="active = true",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    certificate_path: Mapped[str] = mapped_column(String(500), nullable=False)
    password_secret: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    company: Mapped[Company] = relationship(back_populates="certificates")
