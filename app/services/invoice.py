from datetime import datetime, timedelta
from app.core.billing import next_period_end

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.db.transactions import write_transaction
from app.models import Invoice
from app.repositories.invoice import InvoiceRepository
from app.repositories.plan import PlanRepository
from app.repositories.subscription import SubscriptionRepository
from app.schemas.invoice import InvoiceCreate
from app.services.ledger import LedgerService


class InvoiceService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = InvoiceRepository(session)
        self.subscriptions = SubscriptionRepository(session)
        self.plans = PlanRepository(session)
        self.ledger = LedgerService(session)

    def generate(self, subscription_id: int, data: InvoiceCreate) -> Invoice:
        with write_transaction(self.session):
            subscription = self.subscriptions.get(subscription_id)
            if subscription is None:
                raise NotFoundError("Subscription not found")
            if subscription.status != "active":
                raise ConflictError("Invoices require an active subscription")
            plan = self.plans.get(subscription.plan_id)
            if plan is None:
                raise NotFoundError("Plan not found")
            start = data.period_start if data.period_start is not None else subscription.start_date
            if start < subscription.start_date:
                raise InvalidRequestError("Billing period cannot precede subscription start")
            try:
                end = data.period_end if data.period_end is not None else next_period_end(start, plan.billing_interval)
                due = data.due_date if data.due_date is not None else start + timedelta(days=7)
            except (ValueError, OverflowError) as error:
                raise InvalidRequestError("Billing dates exceed supported datetime range") from error
            if end <= start:
                raise InvalidRequestError("period_end must be after period_start")
            if due < start:
                raise InvalidRequestError("due_date must not precede period_start")
            if self.repository.find_overlap(subscription_id, start, end) is not None:
                raise ConflictError("An invoice already exists for an overlapping billing period")
            invoice = self.repository.create(
                subscription_id=subscription.id, customer_id=subscription.customer_id,
                amount_due=plan.price, currency=plan.currency,
                period_start=start, period_end=end, due_date=due,
            )
            self.ledger.record(invoice, "invoice_created", invoice.amount_due, f"invoice:{invoice.id}")
            self.subscriptions.set_period(subscription, start, end)
        return invoice

    def get(self, invoice_id: int) -> Invoice:
        invoice = self.repository.get(invoice_id)
        if invoice is None:
            raise NotFoundError("Invoice not found")
        return invoice
