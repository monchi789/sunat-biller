from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import BaseSchema, DailySummaryItemStatus


class DailySummaryCreate(BaseSchema):
    reference_date: date
    document_ids: list[UUID] = Field(min_length=1, max_length=500)


class DailySummaryItemResponse(BaseSchema):
    document_id: UUID
    item_status: DailySummaryItemStatus
    sunat_item_description: str | None = Field(default=None, max_length=500)


class DailySummaryResponse(BaseSchema):
    id: UUID
    reference_date: date
    identifier: str = Field(max_length=50)
    ticket: str | None = Field(default=None, max_length=100)
    status: str = Field(max_length=50)
    sunat_code: str | None = Field(default=None, max_length=20)
    sunat_description: str | None = Field(default=None, max_length=1000)
    items: list[DailySummaryItemResponse]
    created_at: datetime
