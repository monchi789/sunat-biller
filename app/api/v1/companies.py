"""Alta y mantenimiento de empresas emisoras."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.dependencies import AdminOnly, Context, DbSession, Paginated
from app.schemas.common import PaginatedResponse
from app.schemas.company import (
    CompanyCreate,
    CompanyResponse,
    CompanySunatCredentialsUpdate,
    CompanyUpdate,
)
from app.services import audit_service, company_service
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/companies", tags=["Empresas"])


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una empresa emisora",
    description=(
        "Requiere `X-Admin-Token`. Es el primer paso: toda API key pertenece a "
        "una empresa, así que la empresa no puede crearse con una API key.\n\n"
        "El RUC se valida con el algoritmo módulo 11 de SUNAT."
    ),
    dependencies=[AdminOnly],
)
def create_company(data: CompanyCreate, db: DbSession, context: Context) -> CompanyResponse:
    company = company_service.create_company(db, data)
    db.commit()
    audit_service.log(
        company.id,
        AuditAction.COMPANY_CREATED,
        message=f"RUC {company.ruc}",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return CompanyResponse.model_validate(company)


@router.get(
    "",
    response_model=PaginatedResponse[CompanyResponse],
    summary="Listar empresas",
    dependencies=[AdminOnly],
)
def list_companies(db: DbSession, pagination: Paginated) -> PaginatedResponse[CompanyResponse]:
    companies, total = company_service.list_companies(
        db, offset=pagination.offset, limit=pagination.page_size
    )
    return PaginatedResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Obtener una empresa",
    dependencies=[AdminOnly],
)
def get_company(company_id: UUID, db: DbSession) -> CompanyResponse:
    return CompanyResponse.model_validate(company_service.get_company(db, company_id))


@router.patch(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Actualizar los datos de una empresa",
    dependencies=[AdminOnly],
)
def update_company(
    company_id: UUID, data: CompanyUpdate, db: DbSession, context: Context
) -> CompanyResponse:
    company = company_service.update_company(db, company_id, data)
    db.commit()
    audit_service.log(
        company.id,
        AuditAction.COMPANY_UPDATED,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return CompanyResponse.model_validate(company)


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja una empresa",
    description="Baja lógica: se conserva todo lo emitido para mantener la trazabilidad.",
    dependencies=[AdminOnly],
)
def delete_company(company_id: UUID, db: DbSession, context: Context) -> None:
    company_service.delete_company(db, company_id)
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.COMPANY_DELETED,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


@router.patch(
    "/{company_id}/sunat-credentials",
    response_model=CompanyResponse,
    summary="Configurar las credenciales SOL",
    description=(
        "La contraseña se cifra en reposo y nunca vuelve a salir por la API.\n\n"
        "**Para el ambiente BETA de SUNAT** usa `sol_user = MODDATOS` y "
        "`sol_password = moddatos`. El servicio antepone tu RUC automáticamente, "
        "formando el usuario `{RUC}MODDATOS` que espera SUNAT."
    ),
    dependencies=[AdminOnly],
)
def update_sunat_credentials(
    company_id: UUID, data: CompanySunatCredentialsUpdate, db: DbSession, context: Context
) -> CompanyResponse:
    company = company_service.update_sunat_credentials(db, company_id, data)
    db.commit()
    audit_service.log(
        company.id,
        AuditAction.SOL_CREDENTIALS_UPDATED,
        message=f"usuario SOL {data.sol_user}",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return CompanyResponse.model_validate(company)
