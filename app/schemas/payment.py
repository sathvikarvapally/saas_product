from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import StringConstraints, model_validator

from app.schemas.common import InputSchema, OutputSchema
from app.schemas.invoice import InvoiceResponse
from app.schemas.plan import Currency, Money

PaymentStatus = Literal["success", "failed"]
ProviderReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
FailureReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class PaymentCreate(InputSchema):
    amount: Money
    currency: Currency
    status: PaymentStatus
    provider_reference: ProviderReference
    failure_reason: FailureReason | None = None

    @model_validator(mode="after")
    def validate_failure_reason(self):
        if self.status == "failed" and self.failure_reason is None:
            raise ValueError("Failed payments require a failure_reason")
        if self.status == "success" and self.failure_reason is not None:
            raise ValueError("Successful payments cannot include a failure_reason")
        return self


class PaymentAttemptResponse(OutputSchema):
    id: int
    invoice_id: int
    amount: Decimal
    currency: str
    status: PaymentStatus
    provider_reference: str
    failure_reason: str | None
    created_at: datetime


class PaymentRecordResponse(OutputSchema):
    payment_attempt: PaymentAttemptResponse
    invoice: InvoiceResponse
