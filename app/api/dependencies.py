from typing import Annotated

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.customer import CustomerService
from app.services.plan import PlanService
from app.services.subscription import SubscriptionService
from app.services.invoice import InvoiceService
from app.services.ledger import LedgerService
from app.services.payment import PaymentService

DatabaseSession = Annotated[Session, Depends(get_db)]
EntityId = Annotated[int, Path(gt=0)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def get_plan_service(session: DatabaseSession) -> PlanService:
    return PlanService(session)


def get_customer_service(session: DatabaseSession) -> CustomerService:
    return CustomerService(session)


def get_subscription_service(session: DatabaseSession) -> SubscriptionService:
    return SubscriptionService(session)


def get_invoice_service(session: DatabaseSession) -> InvoiceService:
    return InvoiceService(session)


def get_ledger_service(session: DatabaseSession) -> LedgerService:
    return LedgerService(session)


def get_payment_service(session: DatabaseSession) -> PaymentService:
    return PaymentService(session)
