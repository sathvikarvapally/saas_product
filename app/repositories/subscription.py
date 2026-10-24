from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Subscription


class SubscriptionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, customer_id: int, plan_id: int, start_date: datetime, period_end: datetime) -> Subscription:
        subscription = Subscription(
            customer_id=customer_id, plan_id=plan_id, start_date=start_date,
            current_period_start=start_date, current_period_end=period_end,
        )
        self.session.add(subscription)
        self.session.flush()
        return subscription

    def get(self, subscription_id: int) -> Subscription | None:
        return self.session.get(Subscription, subscription_id)

    def get_active(self, customer_id: int, plan_id: int) -> Subscription | None:
        return self.session.scalar(select(Subscription).where(
            Subscription.customer_id == customer_id,
            Subscription.plan_id == plan_id,
            Subscription.status == "active",
        ))

    def list(
        self, offset: int, limit: int, customer_id: int | None = None,
        plan_id: int | None = None, status: str | None = None,
    ) -> list[Subscription]:
        query = select(Subscription)
        if customer_id is not None:
            query = query.where(Subscription.customer_id == customer_id)
        if plan_id is not None:
            query = query.where(Subscription.plan_id == plan_id)
        if status is not None:
            query = query.where(Subscription.status == status)
        return list(self.session.scalars(query.order_by(Subscription.id).offset(offset).limit(limit)))

    def cancel(self, subscription: Subscription, cancelled_at: datetime) -> Subscription:
        subscription.status = "cancelled"
        subscription.cancelled_at = cancelled_at
        self.session.flush()
        return subscription

    def set_period(self, subscription: Subscription, start: datetime, end: datetime) -> None:
        if start >= subscription.current_period_start:
            subscription.current_period_start = start
            subscription.current_period_end = end
            self.session.flush()
