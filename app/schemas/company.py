from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class CompanyBase(BaseSchema):
    business_name: str = Field(min_length=1, max_length=255)
    commercial_name: str | None = Field(default=None, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    ubigeo: str = Field(pattern=r"^\d{6}$")
    department: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")


class CompanyCreate(CompanyBase):
    ruc: str = Field(pattern=r"^\d{11}$")

    @field_validator("ruc")
    @classmethod
    def validate_ruc_check_digit(cls, v: str) -> str:
        """
        Validates the RUC check digit using SUNAT's modulo-11 algorithm.
        Factors applied to the first 10 digits: [5, 4, 3, 2, 7, 6, 5, 4, 3, 2].
        The 11th digit must match: 11 - (sum % 11), where 10 → 0 and 11 → 1.
        """
        factors = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        total = sum(int(v[i]) * factors[i] for i in range(10))
        remainder = total % 11
        expected = 11 - remainder
        if expected == 10:
            expected = 0
        elif expected == 11:
            expected = 1
        if int(v[10]) != expected:
            raise ValueError("Invalid RUC: check digit does not match.")
        return v


class CompanyUpdate(BaseSchema):
    business_name: str | None = Field(default=None, min_length=1, max_length=255)
    commercial_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    ubigeo: str | None = Field(default=None, pattern=r"^\d{6}$")
    department: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    active: bool | None = None


class CompanyResponse(CompanyBase):
    id: UUID
    ruc: str = Field(pattern=r"^\d{11}$")
    active: bool
    created_at: datetime
    updated_at: datetime


class CompanySunatCredentialsUpdate(BaseSchema):
    sol_user: str = Field(min_length=1, max_length=50)
    sol_password: str = Field(min_length=8, max_length=100)
