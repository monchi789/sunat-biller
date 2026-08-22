from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema


class AuditLogResponse(BaseSchema):
    id: UUID
    company_id: UUID
    document_id: UUID | None = None
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: UUID | None = None
    action: str = Field(min_length=1, max_length=100)
    status: str = Field(max_length=50)
    message: str | None = Field(default=None, max_length=2000)
    ip_address: str | None = Field(default=None, max_length=45)
    user_agent: str | None = Field(default=None, max_length=500)
    created_at: datetime
