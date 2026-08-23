"""Emisión de facturas electrónicas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.v1.serializers import to_invoice_response
from app.core.dependencies import Context, CurrentCompany, DbSession, IdempotencyKey
from app.schemas.invoice import InvoiceCreate, InvoiceResponse
from app.services import document_service, invoice_service

router = APIRouter(prefix="/invoices", tags=["Facturas"])

RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": (
            "Comprobante procesado. **Revisa siempre el campo `status`**: un "
            "rechazo de SUNAT también llega como 200, porque es una respuesta "
            "válida del servicio, no un error de la petición.\n\n"
            "- `ACCEPTED` — aceptado, `sunat_code` es `0`.\n"
            "- `ACCEPTED_WITH_OBSERVATION` — aceptado con observaciones (4xxx).\n"
            "- `REJECTED` — rechazado (2xxx). Hay que corregir y emitir uno nuevo.\n"
            "- `SENT` — SUNAT no respondió; el comprobante queda firmado para reintento."
        )
    },
    409: {"description": "Idempotency-Key en uso, o varias series activas sin especificar cuál."},
    422: {"description": "Datos inválidos o importes que no cuadran con el cálculo del servidor."},
}


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_200_OK,
    responses=RESPONSES,
    summary="Emitir una factura",
    description=(
        "Calcula los importes, genera el XML UBL 2.1, lo firma con el certificado "
        "de la empresa y lo envía a SUNAT, todo en la misma llamada.\n\n"
        "**Solo hace falta enviar los datos del negocio**: cantidad, valor unitario "
        "y afectación por línea. El IGV y los totales los calcula el servicio; si "
        "los envías, se verifican contra el cálculo y se rechaza la emisión si no "
        "cuadran (tolerancia ±0.01).\n\n"
        "Usa `X-Idempotency-Key` para que un reintento de red no genere dos facturas."
    ),
)
def emit_invoice(
    data: InvoiceCreate,
    db: DbSession,
    company: CurrentCompany,
    context: Context,
    idempotency_key: IdempotencyKey,
    response: Response,
) -> InvoiceResponse:
    if idempotency_key:
        stored = invoice_service.find_idempotent_response(db, company.id, idempotency_key)
        if stored is not None:
            _, body = stored
            document_id = body.get("id")
            if document_id:
                response.headers["X-Idempotent-Replay"] = "true"
                document = document_service.get_document(db, company.id, UUID(document_id))
                return to_invoice_response(document)

    document = invoice_service.emit_invoice(
        db,
        company,
        data,
        idempotency_key=idempotency_key,
        ip_address=context.ip_address,
        user_agent=context.user_agent,
    )
    return to_invoice_response(document)


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Consultar una factura",
)
def get_invoice(invoice_id: UUID, db: DbSession, company: CurrentCompany) -> InvoiceResponse:
    return to_invoice_response(document_service.get_document(db, company.id, invoice_id))
