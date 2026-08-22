from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, final

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import ElectronicDocument


@final
class SunatSubmission(Base, TimestampMixin):
    """Bitácora de cada envío a SUNAT, y a la vez **outbox** de reintentos.

    Es 1:N con el documento a propósito: cada intento deja su propia fila, así
    que el historial de reintentos queda auditable.

    Como outbox, la fila se escribe en la **misma transacción** que el cambio de
    estado del documento. Redis solo dispara el job; si Redis pierde el mensaje,
    el barrido periódico recupera el trabajo desde esta tabla. Sin eso, un
    proceso que muere entre el commit y el encolado perdería el reintento.
    """

    __tablename__ = "sunat_submissions"
    __table_args__ = (
        # Barrido del outbox: "dame lo pendiente que ya toca reintentar".
        Index("ix_sunat_submissions_retry", "status", "next_attempt_at"),
        Index("ix_sunat_submissions_document", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=False
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    submission_type: Mapped[str] = mapped_column(String(50), nullable=False)

    ticket: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    sunat_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sunat_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── outbox de reintentos ────────────────────────────────────────────────
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Cuándo toca el siguiente intento. `NULL` = no hay reintento programado."""
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped[ElectronicDocument] = relationship(back_populates="sunat_submissions")
