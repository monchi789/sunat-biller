"""Emisión y revocación de API keys."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.dependencies import AdminOnly, Context, DbSession
from app.schemas.api_key import APIKeyCreate, APIKeyCreatedResponse, APIKeyResponse
from app.services import api_key_service, audit_service, company_service
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/companies/{company_id}/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una API key",
    description=(
        "Devuelve la clave en claro **una sola vez**: solo se almacena su hash, "
        "así que no hay forma de recuperarla después. Guárdala al recibirla.\n\n"
        "Requiere `X-Admin-Token`."
    ),
    dependencies=[AdminOnly],
)
def create_api_key(
    company_id: UUID, data: APIKeyCreate, db: DbSession, context: Context
) -> APIKeyCreatedResponse:
    company_service.get_company(db, company_id)  # valida existencia y baja lógica
    api_key, raw_key = api_key_service.create_api_key(db, company_id, data)
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.API_KEY_CREATED,
        entity_type="APIKey",
        entity_id=api_key.id,
        message=f"key «{data.name}»",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return APIKeyCreatedResponse(key=raw_key)


@router.get(
    "",
    response_model=list[APIKeyResponse],
    summary="Listar API keys",
    description="Nunca expone el valor de la clave, solo sus metadatos.",
    dependencies=[AdminOnly],
)
def list_api_keys(company_id: UUID, db: DbSession) -> list[APIKeyResponse]:
    return [
        APIKeyResponse.model_validate(key) for key in api_key_service.list_api_keys(db, company_id)
    ]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revocar una API key",
    dependencies=[AdminOnly],
)
def revoke_api_key(company_id: UUID, key_id: UUID, db: DbSession, context: Context) -> None:
    api_key_service.revoke_api_key(db, company_id, key_id)
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.API_KEY_REVOKED,
        entity_type="APIKey",
        entity_id=key_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
