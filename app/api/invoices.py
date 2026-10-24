from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import EntityId, get_invoice_service
from app.schemas.invoice import InvoiceCreate, InvoiceResponse
from app.services.invoice import InvoiceService

router = APIRouter(tags=["Invoices"])
Service = Annotated[InvoiceService, Depends(get_invoice_service)]


@router.post(
    "/subscriptions/{subscription_id}/invoices",
    response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED,
)
def generate_invoice(subscription_id: EntityId, service: Service, data: InvoiceCreate | None = None):
    return service.generate(subscription_id, data if data is not None else InvoiceCreate())


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: EntityId, service: Service):
    return service.get(invoice_id)
