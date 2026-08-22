from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, DocumentType


class DocumentSeriesCreate(BaseSchema):
    document_type: DocumentType
    series: str = Field(pattern=r"^[A-Z]\d{3}$")
    current_number: int = Field(ge=0, le=99_999_999)


class DocumentSeriesUpdate(BaseSchema):
    active: bool | None = None


class DocumentSeriesResponse(BaseSchema):
    id: UUID
    company_id: UUID
    document_type: DocumentType
    series: str = Field(pattern=r"^[A-Z]\d{3}$")
    current_number: int = Field(ge=0, le=99_999_999)
    active: bool
