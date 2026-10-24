from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import InputSchema, OutputSchema

SubscriptionStatus = Literal["active", "cancelled"]
PositiveId = Annotated[int, Field(gt=0, strict=True)]


class SubscriptionCreate(InputSchema):
    customer_id: PositiveId
    plan_id: PositiveId


class SubscriptionResponse(OutputSchema):
    id: int
    customer_id: int
    plan_id: int
    status: SubscriptionStatus
    start_date: datetime
    current_period_start: datetime
    current_period_end: datetime
    cancelled_at: datetime | None
    created_at: datetime
