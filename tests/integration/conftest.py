import os
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from memoria.api.dependencies import get_namespace
from memoria.database.session import get_db
from memoria.main import app

ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if Path(str(item.fspath)).is_relative_to(Path(__file__).parent):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL is not set"))


def _ensure_database_exists(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


def alembic_config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    assert TEST_DATABASE_URL
    _ensure_database_exists(TEST_DATABASE_URL)
    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE memories"))
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def act_as() -> Callable[[str], None]:
    """Switch the caller identity, simulating a different configured namespace."""

    def _act_as(namespace: str) -> None:
        app.dependency_overrides[get_namespace] = lambda: namespace

    return _act_as
