from datetime import date as Date
from decimal import Decimal

from pydantic import Field

from app.schemas.common import BaseSchema, PriceType, TaxAffectationType, UnitCode


class DocumentItemCreate(BaseSchema):
    line_number: int = Field(ge=1)
    product_code: str | None = Field(default=None, max_length=100)
    description: str = Field(min_length=1, max_length=500)

    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    unit_code: UnitCode

    unit_value: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=6)

    discount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    subtotal: Decimal = Field(max_digits=18, decimal_places=2)

    taxable_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    igv_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    isc_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    icbper_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2, default=Decimal(0))
    other_tax_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    total: Decimal = Field(max_digits=18, decimal_places=2)

    tax_affectation: TaxAffectationType
    price_type: PriceType


class InstallmentCreate(BaseSchema):
    installment_number: int = Field(ge=1)
    due_date: Date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
