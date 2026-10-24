from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.main import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        yield engine, config
    finally:
        engine.dispose()
        get_settings.cache_clear()


@pytest.fixture
def session(database):
    with Session(database[0]) as session:
        yield session


@pytest.fixture
def client(database):
    def test_session():
        with Session(database[0], expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = test_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
