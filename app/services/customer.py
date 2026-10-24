from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Customer
from app.repositories.customer import CustomerRepository
from app.schemas.customer import CustomerCreate


class CustomerService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = CustomerRepository(session)

    def create(self, data: CustomerCreate) -> Customer:
        # Input normalizes email; the unique constraint also handles concurrent inserts.
        try:
            with self.session.begin():
                if self.repository.get_by_email(data.email) is not None:
                    raise ConflictError("A customer with this email already exists")
                customer = self.repository.create(**data.model_dump())
        except IntegrityError as error:
            # The failed transaction has rolled back before this query.
            if self.repository.get_by_email(data.email) is not None:
                raise ConflictError("A customer with this email already exists") from error
            raise
        return customer

    def get(self, customer_id: int) -> Customer:
        customer = self.repository.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    def list(self, offset: int, limit: int) -> list[Customer]:
        return self.repository.list(offset, limit)
