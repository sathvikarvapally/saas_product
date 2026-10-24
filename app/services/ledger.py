from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Invoice, LedgerEntry
from app.repositories.customer import CustomerRepository
from app.repositories.ledger import LedgerRepository
from app.schemas.ledger import LedgerEventType


class LedgerService:
    def __init__(self, session: Session):
        self.repository = LedgerRepository(session)
        self.customers = CustomerRepository(session)

    def record(
        self, invoice: Invoice, event_type: LedgerEventType,
        amount: Decimal, reference_id: str,
    ) -> LedgerEntry:
        """Append within the invoice/payment service transaction; never commit here."""
        return self.repository.append(
            customer_id=invoice.customer_id, invoice_id=invoice.id,
            event_type=event_type, amount=amount, currency=invoice.currency,
            reference_id=reference_id,
            description=f"{event_type} for invoice {invoice.id}",
        )

    def list_for_customer(self, customer_id: int, offset: int, limit: int) -> list[LedgerEntry]:
        if self.customers.get(customer_id) is None:
            raise NotFoundError("Customer not found")
        return self.repository.list_for_customer(customer_id, offset, limit)
