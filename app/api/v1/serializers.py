"""Traducción de modelos ORM a los schemas de respuesta.

Hace falta un paso explícito porque el documento guarda al cliente como
`customer_snapshot` —una copia congelada en el momento de la emisión— mientras
que la respuesta lo expone como `customer`. Dejar que Pydantic lo resolviera
solo devolvería `null` en silencio.
"""

from __future__ import annotations

from typing import Any

from app.models.document import ElectronicDocument
from app.schemas.customer import CustomerCreate
from app.schemas.document import DocumentResponse
from app.schemas.document_item import DocumentItemCreate, InstallmentCreate
from app.schemas.invoice import InvoiceResponse


def _customer(document: ElectronicDocument) -> CustomerCreate | None:
    snapshot = document.customer_snapshot
    if snapshot is None:
        return None
    return CustomerCreate(
        document_type=snapshot.document_type,  # type: ignore[arg-type]
        document_number=snapshot.document_number,
        name=snapshot.name,
        address=snapshot.address,
        ubigeo=snapshot.ubigeo,
        country_code=snapshot.country_code,
    )


def document_payload(document: ElectronicDocument) -> dict[str, Any]:
    """Campos comunes a todas las respuestas de comprobante."""
    return {
        "id": document.id,
        "document_type": document.document_type,
        "series": document.series,
        "number": document.number,
        "issue_date": document.issue_date,
        "issue_time": document.issue_time,
        "currency": document.currency,
        "operation_type": document.operation_type,
        "payment_terms": document.payment_terms,
        "customer": _customer(document),
        "items": [
            DocumentItemCreate.model_validate(item)
            for item in sorted(document.items, key=lambda i: i.line_number)
        ],
        "installments": [
            InstallmentCreate.model_validate(installment)
            for installment in sorted(document.installments, key=lambda i: i.installment_number)
        ],
        "subtotal": document.subtotal,
        "discount_total": document.discount_total,
        "taxable_total": document.taxable_total,
        "exempt_total": document.exempt_total,
        "unaffected_total": document.unaffected_total,
        "export_total": document.export_total,
        "free_total": document.free_total,
        "igv_total": document.igv_total,
        "isc_total": document.isc_total,
        "icbper_total": document.icbper_total,
        "other_tax_total": document.other_tax_total,
        "total": document.total,
        "status": document.status,
        "sunat_status": document.sunat_status,
        "sunat_code": document.sunat_code,
        "sunat_description": document.sunat_description,
        "xml_hash": document.xml_hash,
        "filename": document.filename,
        "sent_at": document.sent_at,
        "accepted_at": document.accepted_at,
        "voided_at": document.voided_at,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def to_invoice_response(document: ElectronicDocument) -> InvoiceResponse:
    return InvoiceResponse.model_validate(document_payload(document))


def to_document_response(document: ElectronicDocument) -> DocumentResponse:
    return DocumentResponse.model_validate(document_payload(document))
