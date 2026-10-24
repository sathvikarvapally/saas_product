from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan


class PlanRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, **values) -> Plan:
        plan = Plan(**values)
        self.session.add(plan)
        self.session.flush()
        return plan

    def get(self, plan_id: int) -> Plan | None:
        return self.session.get(Plan, plan_id)

    def list(self, offset: int, limit: int) -> list[Plan]:
        return list(self.session.scalars(select(Plan).order_by(Plan.id).offset(offset).limit(limit)))

    def update(self, plan: Plan, **values) -> Plan:
        for field, value in values.items():
            setattr(plan, field, value)
        self.session.flush()
        return plan
