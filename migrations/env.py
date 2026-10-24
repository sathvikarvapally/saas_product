"""Alembic uses the same environment configuration and metadata as the app."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401 -- registers entities with Base.metadata

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    if type_ == "type" and obj.__class__.__name__ == "UTCDateTime":
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
        compare_type=True, render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata,
            compare_type=True, render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
