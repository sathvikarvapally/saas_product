"""Required assignment paths share the existing service implementations."""
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import EntityId, get_invoice_service, get_payment_service, get_subscription_service
from app.schemas.invoice import InvoiceCreate, InvoiceResponse
from app.schemas.payment import PaymentCreate, PaymentRecordResponse
from app.schemas.subscription import PositiveId, SubscriptionResponse
from app.services.invoice import InvoiceService
from app.services.payment import PaymentService
from app.services.subscription import SubscriptionService

router = APIRouter()


class InvoiceGenerateRequest(InvoiceCreate):
    subscription_id: PositiveId


class PaymentRecordRequest(PaymentCreate):
    invoice_id: PositiveId


@router.patch("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse, tags=["Subscriptions"])
def cancel_subscription(subscription_id: EntityId, service: Annotated[SubscriptionService, Depends(get_subscription_service)]):
    return service.cancel(subscription_id)


@router.post("/invoices/generate", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED, tags=["Invoices"])
def generate_invoice(data: InvoiceGenerateRequest, service: Annotated[InvoiceService, Depends(get_invoice_service)]):
    return service.generate(data.subscription_id, InvoiceCreate(**data.model_dump(exclude={"subscription_id"})))


@router.post("/payments/record", response_model=PaymentRecordResponse, status_code=status.HTTP_201_CREATED, tags=["Payments"])
def record_payment(data: PaymentRecordRequest, service: Annotated[PaymentService, Depends(get_payment_service)]):
    return service.record(data.invoice_id, PaymentCreate(**data.model_dump(exclude={"invoice_id"})))
