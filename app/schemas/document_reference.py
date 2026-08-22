from pydantic import Field, model_validator

from app.schemas.common import (
    BaseSchema,
    CreditNoteReasonType,
    DebitNoteReasonType,
    DocumentType,
)


class DocumentReferenceCreate(BaseSchema):
    reference_document_type: DocumentType
    reference_series: str = Field(pattern=r"^[A-Z]\d{3}$")
    reference_number: int = Field(ge=1, le=99_999_999)
    reason_code: CreditNoteReasonType | DebitNoteReasonType
    reason_description: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_reference_document_type(self) -> "DocumentReferenceCreate":
        allowed = {DocumentType.INVOICE, DocumentType.RECEIPT}
        if self.reference_document_type not in allowed:
            raise ValueError("reference_document_type must be INVOICE or RECEIPT; a note cannot reference another note")
        return self
