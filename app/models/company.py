from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, final

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampUpdateMixin

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.certificate import DigitalCertificate
    from app.models.daily_summary import DailySummary
    from app.models.document import ElectronicDocument
    from app.models.document_series import DocumentSeries
    from app.models.idempotency import IdempotencyKey
    from app.models.voided_document import VoidedDocument


@final
class Company(Base, SoftDeleteMixin, TimestampUpdateMixin):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ruc: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commercial_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    ubigeo: Mapped[str] = mapped_column(String(6), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    sol_user: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sol_password_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="SUNAT_DIRECT")
    ose_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ose_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ose_client_secret_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships — types resolved via SQLAlchemy's string registry;
    # no cross-model imports needed thanks to `from __future__ import annotations`.
    api_keys: Mapped[list[APIKey]] = relationship(back_populates="company")
    certificates: Mapped[list[DigitalCertificate]] = relationship(back_populates="company")
    document_series: Mapped[list[DocumentSeries]] = relationship(back_populates="company")
    documents: Mapped[list[ElectronicDocument]] = relationship(back_populates="company")
    daily_summaries: Mapped[list[DailySummary]] = relationship(back_populates="company")
    voided_documents: Mapped[list[VoidedDocument]] = relationship(back_populates="company")
    idempotency_keys: Mapped[list[IdempotencyKey]] = relationship(back_populates="company")
