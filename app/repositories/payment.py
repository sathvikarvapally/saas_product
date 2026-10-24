from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentAttempt


class PaymentAttemptRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, **values) -> PaymentAttempt:
        attempt = PaymentAttempt(**values)
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def get_by_reference(self, provider_reference: str) -> PaymentAttempt | None:
        return self.session.scalar(select(PaymentAttempt).where(
            PaymentAttempt.provider_reference == provider_reference,
        ))

    def list_for_invoice(self, invoice_id: int, offset: int, limit: int) -> list[PaymentAttempt]:
        return list(self.session.scalars(
            select(PaymentAttempt).where(PaymentAttempt.invoice_id == invoice_id)
            .order_by(PaymentAttempt.id).offset(offset).limit(limit)
        ))
