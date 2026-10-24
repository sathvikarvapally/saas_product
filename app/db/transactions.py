from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def write_transaction(session: Session) -> Iterator[None]:
    """Serialize SQLite read/check/write operations before reading billing state."""
    with session.begin():
        if session.get_bind().dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield
