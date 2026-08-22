from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, final

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, TimestampUpdateMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.document import ElectronicDocument


@final
class WebhookEndpoint(Base, SoftDeleteMixin, TimestampUpdateMixin):
    """Destino al que se notifican los eventos del facturador.

    Es el mecanismo por el que otras aplicaciones (ERP, POS, e-commerce) se
    enteran de que un comprobante fue aceptado o rechazado, sin tener que hacer
    polling.
    """

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_company_active", "company_id", "active"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    """Secreto HMAC cifrado con Fernet. Se muestra en claro una sola vez."""

    secret_next_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Secreto entrante durante una rotación.

    Mientras exista, cada entrega se firma con **ambos** secretos y el receptor
    acepta si cualquiera coincide. Sin esto, rotar el secreto obliga a una
    ventana de entregas perdidas.
    """

    event_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    """Eventos suscritos. `["*"]` recibe todos."""

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    """Para auto-desactivar destinos rotos y dejar de gastar reintentos."""

    company: Mapped[Company] = relationship(back_populates="webhook_endpoints")
    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


@final
class WebhookDelivery(Base, TimestampUpdateMixin):
    """Una entrega concreta de un evento. Funciona como **outbox transaccional**.

    La fila se inserta en la misma transacción que el cambio de estado que la
    origina, así que ningún evento se pierde aunque Redis o el proceso caigan.

    El `payload` se congela al crearse y **nunca** se recalcula: el cuerpo debe
    ser byte-idéntico entre reintentos para que la firma HMAC sea estable y el
    receptor pueda deduplicar por `event_id`.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_delivery_event"),
        Index("ix_webhook_deliveries_pending", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_company", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id"), nullable=False
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    """Desnormalizado a propósito: permite aislar por empresa sin join."""

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("electronic_documents.id"), nullable=True
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    """Estable entre reintentos: es la clave de deduplicación del receptor."""

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")
    document: Mapped[ElectronicDocument | None] = relationship()


__all__ = ["Base", "TimestampMixin", "WebhookDelivery", "WebhookEndpoint"]
