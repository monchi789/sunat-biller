"""Consulta y descarga de comprobantes emitidos."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.api.v1.serializers import to_document_response
from app.core.dependencies import CurrentCompany, DbSession, Paginated
from app.core.errors import NotFoundError
from app.models.document import ElectronicDocument
from app.schemas.common import DocumentStatus, DocumentType, FileType, PaginatedResponse
from app.schemas.document import DocumentResponse
from app.services import document_service, file_storage_service

router = APIRouter(prefix="/documents", tags=["Comprobantes"])


@router.get(
    "",
    response_model=PaginatedResponse[DocumentResponse],
    summary="Listar comprobantes",
    description="Todos los filtros son opcionales y se combinan entre sí.",
)
def list_documents(
    db: DbSession,
    company: CurrentCompany,
    pagination: Paginated,
    document_type: Annotated[DocumentType | None, Query(description="Catálogo 01.")] = None,
    status: Annotated[DocumentStatus | None, Query(description="Estado interno.")] = None,
    series: Annotated[str | None, Query(pattern=r"^[A-Z]\d{3}$")] = None,
    issue_date_from: Annotated[date | None, Query()] = None,
    issue_date_to: Annotated[date | None, Query()] = None,
) -> PaginatedResponse[DocumentResponse]:
    documents, total = document_service.list_documents(
        db,
        company.id,
        offset=pagination.offset,
        limit=pagination.page_size,
        document_type=document_type.value if document_type else None,
        status=status.value if status else None,
        series=series,
        issue_date_from=issue_date_from,
        issue_date_to=issue_date_to,
    )
    return PaginatedResponse(
        items=[to_document_response(d) for d in documents],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Obtener un comprobante",
)
def get_document(document_id: UUID, db: DbSession, company: CurrentCompany) -> DocumentResponse:
    return to_document_response(document_service.get_document(db, company.id, document_id))


def _download(document: ElectronicDocument, file_type: FileType, label: str) -> Response:
    stored = next((f for f in document.files if f.file_type == file_type.value), None)
    if stored is None:
        raise NotFoundError(
            f"El comprobante no tiene {label} almacenado.",
            {"document_id": str(document.id), "status": document.status},
        )
    return Response(
        content=file_storage_service.read(stored.storage_path),
        media_type=stored.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{stored.filename}"'},
    )


@router.get(
    "/{document_id}/xml",
    summary="Descargar el XML firmado",
    description="El XML UBL 2.1 tal cual se envió a SUNAT, con la firma incrustada.",
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}}},
)
def download_xml(document_id: UUID, db: DbSession, company: CurrentCompany) -> Response:
    document = document_service.get_document(db, company.id, document_id)
    return _download(document, FileType.XML, "XML firmado")


@router.get(
    "/{document_id}/cdr",
    summary="Descargar el CDR",
    description=(
        "La Constancia de Recepción que devolvió SUNAT. Solo existe si el "
        "comprobante llegó a ser aceptado o rechazado."
    ),
    response_class=Response,
    responses={200: {"content": {"application/xml": {}}}},
)
def download_cdr(document_id: UUID, db: DbSession, company: CurrentCompany) -> Response:
    document = document_service.get_document(db, company.id, document_id)
    return _download(document, FileType.CDR, "CDR")
