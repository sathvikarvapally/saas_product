from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import EntityId, Limit, Offset, get_plan_service
from app.schemas.plan import PlanCreate, PlanResponse, PlanUpdate
from app.services.plan import PlanService

router = APIRouter(prefix="/plans", tags=["Plans"])
Service = Annotated[PlanService, Depends(get_plan_service)]


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanCreate, service: Service):
    return service.create(data)


@router.get("", response_model=list[PlanResponse])
def list_plans(service: Service, offset: Offset = 0, limit: Limit = 20):
    return service.list(offset, limit)


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: EntityId, service: Service):
    return service.get(plan_id)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(plan_id: EntityId, data: PlanUpdate, service: Service):
    return service.update(plan_id, data)
