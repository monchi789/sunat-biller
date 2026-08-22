from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class IdempotencyResponse(BaseSchema):
    id: UUID
    key: str = Field(min_length=1, max_length=255)
    document_id: UUID | None = None
    response_status: int = Field(ge=100, le=599)
    created_at: datetime
    expires_at: datetime | None = None
