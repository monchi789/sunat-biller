from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, DocumentType


class DocumentSeriesCreate(BaseSchema):
    document_type: DocumentType
    series: str = Field(pattern=r"^[A-Z]\d{3}$")
    current_number: int = Field(
        default=0, ge=0, le=99_999_999,
        description="Último correlativo emitido. 0 para empezar en F001-00000001.",
    )


class DocumentSeriesUpdate(BaseSchema):
    active: bool | None = None


class DocumentSeriesResponse(BaseSchema):
    id: UUID
    company_id: UUID
    document_type: DocumentType
    series: str = Field(pattern=r"^[A-Z]\d{3}$")
    current_number: int = Field(default=0, ge=0, le=99_999_999)
    active: bool
