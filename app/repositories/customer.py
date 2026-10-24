from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer


class CustomerRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, **values) -> Customer:
        customer = Customer(**values)
        self.session.add(customer)
        self.session.flush()
        return customer

    def get(self, customer_id: int) -> Customer | None:
        return self.session.get(Customer, customer_id)

    def get_by_email(self, email: str) -> Customer | None:
        return self.session.scalar(select(Customer).where(Customer.email == email))

    def list(self, offset: int, limit: int) -> list[Customer]:
        return list(self.session.scalars(select(Customer).order_by(Customer.id).offset(offset).limit(limit)))
