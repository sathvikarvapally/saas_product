from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Plan
from app.repositories.plan import PlanRepository
from app.schemas.plan import PlanCreate, PlanUpdate
from app.db.transactions import write_transaction


class PlanService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = PlanRepository(session)

    def create(self, data: PlanCreate) -> Plan:
        with self.session.begin():
            plan = self.repository.create(**data.model_dump())
        return plan

    def get(self, plan_id: int) -> Plan:
        plan = self.repository.get(plan_id)
        if plan is None:
            raise NotFoundError("Plan not found")
        return plan

    def list(self, offset: int, limit: int) -> list[Plan]:
        return self.repository.list(offset, limit)

    def update(self, plan_id: int, data: PlanUpdate) -> Plan:
        with write_transaction(self.session):
            plan = self.get(plan_id)
            self.repository.update(plan, **data.model_dump(exclude_unset=True))
        return plan
