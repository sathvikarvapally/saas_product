from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import EntityId, Limit, Offset, get_customer_service
from app.schemas.customer import CustomerCreate, CustomerResponse
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])
Service = Annotated[CustomerService, Depends(get_customer_service)]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(data: CustomerCreate, service: Service):
    return service.create(data)


@router.get("", response_model=list[CustomerResponse])
def list_customers(service: Service, offset: Offset = 0, limit: Limit = 20):
    return service.list(offset, limit)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: EntityId, service: Service):
    return service.get(customer_id)
