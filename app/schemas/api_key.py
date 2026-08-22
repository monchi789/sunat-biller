from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import BaseSchema


class APIKeyCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_future(cls, v: datetime | None) -> datetime | None:
        if v is not None and v <= datetime.now(tz=UTC):
            raise ValueError("expires_at must be a future datetime")
        return v


class APIKeyResponse(BaseSchema):
    id: UUID
    name: str = Field(max_length=100)
    active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class APIKeyCreatedResponse(BaseSchema):
    key: str
