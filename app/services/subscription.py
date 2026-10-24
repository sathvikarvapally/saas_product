from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.billing import next_period_end
from app.db.transactions import write_transaction
from app.models import Subscription
from app.repositories.customer import CustomerRepository
from app.repositories.plan import PlanRepository
from app.repositories.subscription import SubscriptionRepository
from app.schemas.subscription import SubscriptionCreate


class SubscriptionService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = SubscriptionRepository(session)
        self.customers = CustomerRepository(session)
        self.plans = PlanRepository(session)

    def create(self, data: SubscriptionCreate) -> Subscription:
        try:
            with write_transaction(self.session):
                if self.customers.get(data.customer_id) is None:
                    raise NotFoundError("Customer not found")
                plan = self.plans.get(data.plan_id)
                if plan is None:
                    raise NotFoundError("Plan not found")
                if not plan.is_active:
                    raise ConflictError("Cannot subscribe to an inactive plan")
                if self.repository.get_active(data.customer_id, data.plan_id) is not None:
                    raise ConflictError("Customer already has an active subscription to this plan")
                start = datetime.now(timezone.utc)
                subscription = self.repository.create(
                    data.customer_id, data.plan_id, start, next_period_end(start, plan.billing_interval),
                )
        except IntegrityError as error:
            if self.repository.get_active(data.customer_id, data.plan_id) is not None:
                raise ConflictError("Customer already has an active subscription to this plan") from error
            raise
        return subscription

    def get(self, subscription_id: int) -> Subscription:
        subscription = self.repository.get(subscription_id)
        if subscription is None:
            raise NotFoundError("Subscription not found")
        return subscription

    def list(
        self, offset: int, limit: int, customer_id: int | None = None,
        plan_id: int | None = None, status: str | None = None,
    ) -> list[Subscription]:
        return self.repository.list(offset, limit, customer_id, plan_id, status)

    def cancel(self, subscription_id: int) -> Subscription:
        with write_transaction(self.session):
            subscription = self.get(subscription_id)
            if subscription.status == "active":
                self.repository.cancel(subscription, datetime.now(timezone.utc))
        return subscription
