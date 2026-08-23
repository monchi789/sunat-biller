"""Series de numeración de comprobantes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.dependencies import AdminOnly, Context, DbSession
from app.schemas.series import DocumentSeriesCreate, DocumentSeriesResponse, DocumentSeriesUpdate
from app.services import audit_service, company_service, series_service
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/companies/{company_id}/series", tags=["Series"])


@router.post(
    "",
    response_model=DocumentSeriesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una serie",
    description=(
        "El formato es una letra y tres dígitos: `F001` para facturas, `B001` "
        "para boletas. `current_number` es el último correlativo ya emitido; "
        "déjalo en 0 para que la primera factura sea la `00000001`."
    ),
    dependencies=[AdminOnly],
)
def create_series(
    company_id: UUID, data: DocumentSeriesCreate, db: DbSession, context: Context
) -> DocumentSeriesResponse:
    company_service.get_company(db, company_id)
    series = series_service.create_series(
        db, company_id, data.document_type.value, data.series, data.current_number
    )
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.SERIES_CREATED,
        entity_type="DocumentSeries",
        entity_id=series.id,
        message=f"{data.document_type.value}-{data.series}",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return DocumentSeriesResponse.model_validate(series)


@router.get(
    "",
    response_model=list[DocumentSeriesResponse],
    summary="Listar series",
    dependencies=[AdminOnly],
)
def list_series(company_id: UUID, db: DbSession) -> list[DocumentSeriesResponse]:
    return [
        DocumentSeriesResponse.model_validate(s) for s in series_service.list_series(db, company_id)
    ]


@router.patch(
    "/{series_id}",
    response_model=DocumentSeriesResponse,
    summary="Activar o desactivar una serie",
    description="Una serie desactivada deja de entregar correlativos.",
    dependencies=[AdminOnly],
)
def update_series(
    company_id: UUID,
    series_id: UUID,
    data: DocumentSeriesUpdate,
    db: DbSession,
    context: Context,
) -> DocumentSeriesResponse:
    series = series_service.get_series(db, company_id, series_id)
    if data.active is not None:
        series = series_service.set_active(db, company_id, series_id, data.active)
    db.commit()
    audit_service.log(
        company_id,
        AuditAction.SERIES_UPDATED,
        entity_type="DocumentSeries",
        entity_id=series_id,
        message=f"active={series.active}",
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return DocumentSeriesResponse.model_validate(series)
