from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import EntityId, Limit, Offset, get_subscription_service
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse, SubscriptionStatus
from app.services.subscription import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])
Service = Annotated[SubscriptionService, Depends(get_subscription_service)]
FilterId = Annotated[int | None, Query(gt=0)]


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(data: SubscriptionCreate, service: Service):
    return service.create(data)


@router.get("", response_model=list[SubscriptionResponse])
def list_subscriptions(
    service: Service, offset: Offset = 0, limit: Limit = 20,
    customer_id: FilterId = None, plan_id: FilterId = None,
    status: SubscriptionStatus | None = None,
):
    return service.list(offset, limit, customer_id, plan_id, status)


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(subscription_id: EntityId, service: Service):
    return service.get(subscription_id)


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
def cancel_subscription(subscription_id: EntityId, service: Service):
    return service.cancel(subscription_id)
