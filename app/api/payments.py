from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import EntityId, Limit, Offset, get_payment_service
from app.schemas.payment import PaymentAttemptResponse, PaymentCreate, PaymentRecordResponse
from app.services.payment import PaymentService

router = APIRouter(prefix="/invoices/{invoice_id}/payments", tags=["Payments"])
Service = Annotated[PaymentService, Depends(get_payment_service)]


@router.post("", response_model=PaymentRecordResponse, status_code=status.HTTP_201_CREATED)
def record_payment(invoice_id: EntityId, data: PaymentCreate, service: Service):
    return service.record(invoice_id, data)


@router.get("", response_model=list[PaymentAttemptResponse])
def list_payments(invoice_id: EntityId, service: Service, offset: Offset = 0, limit: Limit = 20):
    return service.list_for_invoice(invoice_id, offset, limit)
