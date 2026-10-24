from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import EntityId, Limit, Offset, get_ledger_service
from app.schemas.ledger import LedgerEntryResponse
from app.services.ledger import LedgerService

router = APIRouter(tags=["Ledger"])
Service = Annotated[LedgerService, Depends(get_ledger_service)]


@router.get("/customers/{customer_id}/ledger", response_model=list[LedgerEntryResponse])
def customer_ledger(customer_id: EntityId, service: Service, offset: Offset = 0, limit: Limit = 20):
    return service.list_for_customer(customer_id, offset, limit)
