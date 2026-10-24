from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerEntry


class LedgerRepository:
    def __init__(self, session: Session):
        self.session = session

    def append(self, **values) -> LedgerEntry:
        entry = LedgerEntry(**values)
        self.session.add(entry)
        self.session.flush()
        return entry

    def list_for_customer(self, customer_id: int, offset: int, limit: int) -> list[LedgerEntry]:
        return list(self.session.scalars(
            select(LedgerEntry).where(LedgerEntry.customer_id == customer_id)
            .order_by(LedgerEntry.id).offset(offset).limit(limit)
        ))
