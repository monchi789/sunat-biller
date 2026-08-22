from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, FileType


class DocumentFileResponse(BaseSchema):
    id: UUID
    document_id: UUID
    file_type: FileType
    filename: str = Field(max_length=255)
    mime_type: str = Field(max_length=100)
    file_size: int = Field(gt=0, le=20_000_000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
