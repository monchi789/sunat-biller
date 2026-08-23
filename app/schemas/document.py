from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.schemas.common import (
    BaseSchema,
    CurrencyCode,
    DocumentStatus,
    DocumentType,
    OperationType,
    PaymentTerms,
    SunatStatus,
)
from app.schemas.customer import CustomerCreate
from app.schemas.document_item import DocumentItemCreate, InstallmentCreate


class DocumentCreateBase(BaseSchema):
    series: str | None = Field(
        default=None,
        pattern=r"^[A-Z]\d{3}$",
        description=(
            "Serie a usar, p. ej. `F001`. Si se omite y la empresa tiene una sola "
            "serie activa para el tipo de documento, se usa esa."
        ),
    )
    issue_date: date
    issue_time: time | None = None
    currency: CurrencyCode
    operation_type: OperationType = OperationType.DOMESTIC_SALE
    payment_terms: PaymentTerms = PaymentTerms.CASH
    installments: list[InstallmentCreate] | None = Field(default=None, max_length=36)
    customer: CustomerCreate | None = None
    items: list[DocumentItemCreate] = Field(min_length=1, max_length=500)


class DocumentResponseBase(BaseSchema):
    id: UUID

    document_type: DocumentType
    series: str = Field(pattern=r"^[A-Z]\d{3}$")
    number: int = Field(ge=1, le=99_999_999)

    issue_date: date
    issue_time: time | None = None
    currency: CurrencyCode
    operation_type: OperationType
    payment_terms: PaymentTerms
    installments: list[InstallmentCreate]

    customer: CustomerCreate | None = None
    items: list[DocumentItemCreate]

    subtotal: Decimal = Field(max_digits=18, decimal_places=2)
    discount_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    taxable_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    exempt_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    unaffected_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    export_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    free_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    igv_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    isc_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    icbper_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    other_tax_total: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    total: Decimal = Field(gt=0, max_digits=18, decimal_places=2)

    status: DocumentStatus

    sunat_status: SunatStatus | None = None
    sunat_code: str | None = Field(default=None, max_length=20)
    sunat_description: str | None = Field(default=None, max_length=1000)

    xml_hash: str | None = Field(default=None, pattern=r"^[A-Za-z0-9+/=]{20,}$")
    filename: str | None = Field(default=None, max_length=255)

    sent_at: datetime | None = None
    accepted_at: datetime | None = None
    voided_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


class DocumentResponse(DocumentResponseBase):
    pass
