from pydantic import model_validator

from app.schemas.common import IdentityDocumentType
from app.schemas.document import DocumentCreateBase, DocumentResponseBase


class InvoiceCreate(DocumentCreateBase):
    @model_validator(mode="after")
    def validate_customer(self):
        if self.customer is None:
            raise ValueError("Invoice requires a customer")
        if self.customer.document_type != IdentityDocumentType.RUC:
            raise ValueError("Invoice customer must have document_type RUC")
        return self


class InvoiceResponse(DocumentResponseBase):
    pass
