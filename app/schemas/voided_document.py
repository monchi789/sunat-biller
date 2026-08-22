from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class VoidedDocumentItemCreate(BaseSchema):
    document_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class VoidedDocumentCreate(BaseSchema):
    reference_date: date
    items: list[VoidedDocumentItemCreate] = Field(min_length=1, max_length=500)


class VoidedDocumentItemResponse(BaseSchema):
    document_id: UUID
    reason: str = Field(max_length=500)


class VoidedDocumentResponse(BaseSchema):
    id: UUID
    reference_date: date
    identifier: str = Field(max_length=50)
    ticket: str | None = Field(default=None, max_length=100)
    status: str = Field(max_length=50)
    sunat_code: str | None = Field(default=None, max_length=20)
    sunat_description: str | None = Field(default=None, max_length=1000)
    items: list[VoidedDocumentItemResponse]
    created_at: datetime
