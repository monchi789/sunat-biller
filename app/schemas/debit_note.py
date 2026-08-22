from pydantic import model_validator

from app.schemas.document import DocumentCreateBase, DocumentResponseBase
from app.schemas.document_reference import DocumentReferenceCreate


class DebitNoteCreate(DocumentCreateBase):
    reference: DocumentReferenceCreate

    @model_validator(mode="after")
    def validate_customer(self):
        if self.customer is None:
            raise ValueError("DebitNote requires a customer")
        return self


class DebitNoteResponse(DocumentResponseBase):
    reference: DocumentReferenceCreate
