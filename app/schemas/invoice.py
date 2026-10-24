from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, field_validator, model_validator

from app.schemas.common import InputSchema, OutputSchema


class InvoiceCreate(InputSchema):
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime | None = None
    due_date: AwareDatetime | None = None

    @field_validator("period_start", "period_end", "due_date")
    @classmethod
    def normalize_utc(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode="after")
    def validate_period(self):
        if self.period_end is not None and self.period_start is None:
            raise ValueError("period_end requires period_start")
        if self.period_start is not None:
            if self.period_end is not None and self.period_end <= self.period_start:
                raise ValueError("period_end must be after period_start")
            if self.due_date is not None and self.due_date < self.period_start:
                raise ValueError("due_date must not precede period_start")
        return self


class InvoiceResponse(OutputSchema):
    id: int
    subscription_id: int
    customer_id: int
    amount_due: Decimal
    amount_paid: Decimal
    currency: str
    status: Literal["draft", "issued", "partially_paid", "paid", "overdue", "void"]
    period_start: datetime
    period_end: datetime
    due_date: datetime
    created_at: datetime
