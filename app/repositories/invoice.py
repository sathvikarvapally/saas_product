from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Invoice


class InvoiceRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, **values) -> Invoice:
        invoice = Invoice(**values)
        self.session.add(invoice)
        self.session.flush()
        return invoice

    def get(self, invoice_id: int) -> Invoice | None:
        return self.session.get(Invoice, invoice_id)

    def apply_payment(self, invoice: Invoice, amount: Decimal) -> Invoice:
        invoice.amount_paid += amount
        invoice.status = "paid" if invoice.amount_paid == invoice.amount_due else "partially_paid"
        self.session.flush()
        return invoice

    def find_overlap(self, subscription_id: int, start: datetime, end: datetime) -> Invoice | None:
        return self.session.scalar(select(Invoice).where(
            Invoice.subscription_id == subscription_id,
            Invoice.period_start < end,
            Invoice.period_end > start,
        ).limit(1))
