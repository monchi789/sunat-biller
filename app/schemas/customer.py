from pydantic import Field, model_validator

from app.schemas.common import BaseSchema, IdentityDocumentType


class CustomerCreate(BaseSchema):
    document_type: IdentityDocumentType
    document_number: str = Field(min_length=1, max_length=15)
    name: str = Field(min_length=1, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    ubigeo: str | None = Field(default=None, pattern=r"^\d{6}$")
    country_code: str = Field(default="PE", pattern=r"^[A-Z]{2}$")

    @model_validator(mode="after")
    def validate_document_number(self) -> "CustomerCreate":
        doc_type = self.document_type
        doc_number = self.document_number
        if doc_type == IdentityDocumentType.DNI and not (len(doc_number) == 8 and doc_number.isdigit()):
            raise ValueError("DNI must be exactly 8 numeric digits")
        if doc_type == IdentityDocumentType.RUC and not (len(doc_number) == 11 and doc_number.isdigit()):
            raise ValueError("RUC must be exactly 11 numeric digits")
        return self
