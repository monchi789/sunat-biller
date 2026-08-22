from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, SubmissionType, SunatEnvironment, SunatStatus


class SunatSubmissionResponse(BaseSchema):
    id: UUID
    filename: str = Field(max_length=255)
    environment: SunatEnvironment
    submission_type: SubmissionType
    ticket: str | None = Field(default=None, max_length=100)
    status: SunatStatus
    sunat_code: str | None = Field(default=None, max_length=20)
    sunat_description: str | None = Field(default=None, max_length=1000)
    sent_at: datetime | None = None
    responded_at: datetime | None = None
