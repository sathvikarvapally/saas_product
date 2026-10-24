from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.schemas.common import OutputSchema

LedgerEventType = Literal["invoice_created", "payment_success", "payment_failure"]


class LedgerEntryResponse(OutputSchema):
    id: int
    customer_id: int
    invoice_id: int
    event_type: LedgerEventType
    entry_type: LedgerEventType
    description: str
    amount: Decimal
    currency: str
    reference_id: str
    created_at: datetime
