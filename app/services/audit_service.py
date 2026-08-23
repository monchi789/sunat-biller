"""Registro de auditoría (RF-12).

Dos decisiones deliberadas:

* **Sesión propia.** Si el log compartiera la sesión del caller, un fallo en la
  emisión haría rollback y borraría precisamente la traza del fallo, que es
  cuando más falta hace.
* **Nunca propaga excepciones.** Que la auditoría falle no puede tumbar una
  emisión ya aceptada por SUNAT. Se registra el problema en el log de la
  aplicación y se sigue.
"""

from __future__ import annotations

from uuid import UUID

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.audit import AuditLog

logger = get_logger(__name__)


class AuditAction:
    """Acciones registradas. Constantes en vez de texto libre, para poder filtrar."""

    COMPANY_CREATED = "COMPANY_CREATED"
    COMPANY_UPDATED = "COMPANY_UPDATED"
    COMPANY_DELETED = "COMPANY_DELETED"
    SOL_CREDENTIALS_UPDATED = "SOL_CREDENTIALS_UPDATED"
    API_KEY_CREATED = "API_KEY_CREATED"
    API_KEY_REVOKED = "API_KEY_REVOKED"
    CERTIFICATE_UPLOADED = "CERTIFICATE_UPLOADED"
    CERTIFICATE_DELETED = "CERTIFICATE_DELETED"
    SERIES_CREATED = "SERIES_CREATED"
    SERIES_UPDATED = "SERIES_UPDATED"
    DOCUMENT_ISSUED = "DOCUMENT_ISSUED"
    DOCUMENT_SIGNED = "DOCUMENT_SIGNED"
    DOCUMENT_SENT = "DOCUMENT_SENT"
    DOCUMENT_ACCEPTED = "DOCUMENT_ACCEPTED"
    DOCUMENT_REJECTED = "DOCUMENT_REJECTED"
    DOCUMENT_ERROR = "DOCUMENT_ERROR"


class AuditStatus:
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    WARNING = "WARNING"


def log(
    company_id: UUID,
    action: str,
    *,
    status: str = AuditStatus.SUCCESS,
    document_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    message: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Registra un evento. Nunca lanza."""
    try:
        with SessionLocal() as session:
            session.add(
                AuditLog(
                    company_id=company_id,
                    document_id=document_id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    action=action,
                    status=status,
                    message=message[:2000] if message else None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            session.commit()
    except Exception:
        logger.exception(
            "no se pudo registrar la auditoría",
            extra={"action": action, "company_id": str(company_id)},
        )
