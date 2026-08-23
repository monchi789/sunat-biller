"""Carga de certificados digitales."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile, status

from app.core.config import settings
from app.core.dependencies import AdminOnly, Context, DbSession
from app.schemas.certificate import CertificateResponse
from app.services import audit_service, certificate_service, company_service
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/companies/{company_id}/certificates", tags=["Certificados"])


@router.post(
    "",
    response_model=CertificateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un certificado digital",
    description=(
        "Recibe el `.pfx` o `.p12` como `multipart/form-data`. Se valida que sea "
        "RSA de al menos 2048 bits y que no esté vencido.\n\n"
        "Solo puede haber **un certificado activo por empresa**: al subir uno "
        "nuevo, el anterior se desactiva automáticamente.\n\n"
        "El contenido del archivo y su contraseña nunca vuelven a salir por la API.\n\n"
        "**Para probar contra BETA** no hace falta un certificado registrado en "
        "SUNAT: uno autofirmado sirve. Genera uno con `make test-cert`."
    ),
    dependencies=[AdminOnly],
)
async def upload_certificate(
    company_id: UUID,
    db: DbSession,
    context: Context,
    file: Annotated[UploadFile, File(description="Certificado .pfx o .p12")],
    password: Annotated[str, Form(description="Contraseña del certificado")],
) -> CertificateResponse:
    company_service.get_company(db, company_id)

    content = await file.read()
    certificate = certificate_service.upload_certificate(
        db, company_id, file.filename or "certificado.pfx", content, password
    )
    db.commit()

    audit_service.log(
        company_id,
        AuditAction.CERTIFICATE_UPLOADED,
        entity_type="DigitalCertificate",
        entity_id=certificate.id,
        message=f"serie {certificate.serial_number}, vence {certificate.valid_until}",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return CertificateResponse.model_validate(certificate)


@router.get(
    "",
    response_model=list[CertificateResponse],
    summary="Listar certificados",
    dependencies=[AdminOnly],
)
def list_certificates(company_id: UUID, db: DbSession) -> list[CertificateResponse]:
    return [
        CertificateResponse.model_validate(c)
        for c in certificate_service.list_certificates(db, company_id)
    ]


@router.delete(
    "/{certificate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dar de baja un certificado",
    dependencies=[AdminOnly],
)
def delete_certificate(
    company_id: UUID, certificate_id: UUID, db: DbSession, context: Context
) -> None:
    certificate_service.delete_certificate(db, company_id, certificate_id)
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.CERTIFICATE_DELETED,
        entity_type="DigitalCertificate",
        entity_id=certificate_id,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )


# `settings` se importa para que el límite de tamaño quede documentado en OpenAPI.
router.__doc__ = f"Tamaño máximo del certificado: {settings.MAX_CERTIFICATE_SIZE_MB} MB."
