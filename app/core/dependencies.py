"""Dependencias compartidas de los endpoints.

Dos mecanismos de autenticación, deliberadamente separados:

* **`X-API-Key`** — identifica a una *empresa*. Es lo que usan las aplicaciones
  integradas y todo queda aislado por `company_id`.
* **`X-Admin-Token`** — autoriza el *aprovisionamiento*: crear empresas y emitir
  sus API keys. Existe porque toda API key pertenece a una empresa, así que la
  primera empresa no puede autenticarse con una.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.logging import company_id_var
from app.models.company import Company

#: Página máxima admitida, alineada con `PaginatedResponse.page_size`.
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Datos del cliente que se registran en `audit_logs` (RF-12.2)."""

    ip_address: str | None
    user_agent: str | None


@dataclass(frozen=True, slots=True)
class Pagination:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_request_context(request: Request) -> RequestContext:
    """IP y user-agent del cliente.

    Respeta `X-Forwarded-For` porque en producción la app va detrás de un
    reverse proxy que termina TLS (RNF-01.5); sin esto se auditaría la IP del
    proxy en lugar de la del cliente.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    client_host = request.client.host if request.client else None
    ip_address = forwarded.split(",")[0].strip() if forwarded else client_host

    user_agent = request.headers.get("User-Agent")
    return RequestContext(
        ip_address=ip_address[:45] if ip_address else None,
        user_agent=user_agent[:500] if user_agent else None,
    )


def get_pagination(
    page: Annotated[int, Query(ge=1, description="Página, empezando en 1.")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Elementos por página.")
    ] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


def get_current_company(
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[
        str | None,
        Header(alias="X-API-Key", description="API key de la empresa."),
    ] = None,
) -> Company:
    """Resuelve la empresa dueña de la API key recibida.

    Nota: es `def`, no `async def`, a propósito. La capa de datos es síncrona
    (psycopg2), así que FastAPI debe ejecutarla en el threadpool en lugar de
    bloquear el event loop.
    """
    if not x_api_key:
        raise UnauthorizedError("Falta la cabecera X-API-Key.")

    # Import diferido: `api_key_service` importa modelos que a su vez importan
    # este módulo indirectamente a través de los routers.
    from app.services import api_key_service

    company = api_key_service.authenticate(db, x_api_key)
    company_id_var.set(str(company.id))
    return company


def require_admin_token(
    x_admin_token: Annotated[
        str | None,
        Header(alias="X-Admin-Token", description="Token de aprovisionamiento."),
    ] = None,
) -> None:
    """Exige el token de administración para las operaciones de alta.

    En desarrollo, si `ADMIN_TOKEN` no está configurado se deja pasar para no
    entorpecer las pruebas locales. En producción `Settings` no arranca sin él,
    así que ese atajo no puede colarse a un despliegue real.
    """
    import secrets

    expected = settings.ADMIN_TOKEN
    if not expected:
        if settings.is_production:  # pragma: no cover - Settings ya lo impide
            raise ForbiddenError("ADMIN_TOKEN no está configurado en el servidor.")
        return

    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise UnauthorizedError("Token de administración inválido o ausente.")


def get_idempotency_key(
    x_idempotency_key: Annotated[
        str | None,
        Header(
            alias="X-Idempotency-Key",
            description=(
                "Clave de idempotencia. Reenviar la misma clave devuelve la "
                "respuesta original en lugar de emitir un comprobante nuevo."
            ),
            max_length=255,
        ),
    ] = None,
) -> str | None:
    return x_idempotency_key or None


CurrentCompany = Annotated[Company, Depends(get_current_company)]
DbSession = Annotated[Session, Depends(get_db)]
Context = Annotated[RequestContext, Depends(get_request_context)]
Paginated = Annotated[Pagination, Depends(get_pagination)]
IdempotencyKey = Annotated[str | None, Depends(get_idempotency_key)]
AdminOnly = Depends(require_admin_token)
