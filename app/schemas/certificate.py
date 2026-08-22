from datetime import datetime
from uuid import UUID

from fastapi import UploadFile
from pydantic import Field

from app.schemas.common import BaseSchema


class CertificateCreate(BaseSchema):
    file: UploadFile
    password: str = Field(min_length=1, max_length=255)


class CertificateResponse(BaseSchema):
    id: UUID
    serial_number: str | None = Field(default=None, max_length=255)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    active: bool
    created_at: datetime
