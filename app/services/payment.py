from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.transactions import write_transaction
from app.models import Invoice, PaymentAttempt
from app.repositories.invoice import InvoiceRepository
from app.repositories.payment import PaymentAttemptRepository
from app.schemas.payment import PaymentCreate
from app.services.ledger import LedgerService


class PaymentService:
    def __init__(self, session: Session):
        self.session = session
        self.invoices = InvoiceRepository(session)
        self.repository = PaymentAttemptRepository(session)
        self.ledger = LedgerService(session)

    def record(self, invoice_id: int, data: PaymentCreate) -> dict[str, Invoice | PaymentAttempt]:
        try:
            with write_transaction(self.session):
                invoice = self.invoices.get(invoice_id)
                if invoice is None:
                    raise NotFoundError("Invoice not found")
                if self.repository.get_by_reference(data.provider_reference) is not None:
                    raise ConflictError("Provider reference has already been recorded")
                if invoice.status in ("draft", "void"):
                    raise ConflictError("Payments require a non-draft, non-void invoice")
                if data.currency != invoice.currency:
                    raise ConflictError("Payment currency must match invoice currency")
                if data.status == "success" and data.amount > invoice.amount_due - invoice.amount_paid:
                    raise ConflictError("Payment exceeds the invoice's remaining unpaid amount")
                attempt = self.repository.create(invoice_id=invoice.id, **data.model_dump())
                if data.status == "success":
                    self.invoices.apply_payment(invoice, data.amount)
                event_type = "payment_success" if data.status == "success" else "payment_failure"
                self.ledger.record(invoice, event_type, data.amount, f"payment:{attempt.id}")
        except IntegrityError as error:
            if self.repository.get_by_reference(data.provider_reference) is not None:
                raise ConflictError("Provider reference has already been recorded") from error
            raise
        return {"payment_attempt": attempt, "invoice": invoice}

    def list_for_invoice(self, invoice_id: int, offset: int, limit: int) -> list[PaymentAttempt]:
        if self.invoices.get(invoice_id) is None:
            raise NotFoundError("Invoice not found")
        return self.repository.list_for_invoice(invoice_id, offset, limit)
