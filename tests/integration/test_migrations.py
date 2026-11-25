from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from memoria.database.models import Base

from .conftest import TEST_DATABASE_URL, alembic_config


def test_models_match_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_metadata_column_is_jsonb(engine: Engine) -> None:
    columns = {c["name"]: c for c in inspect(engine).get_columns("memories")}
    assert columns["metadata"]["type"].__class__.__name__ == "JSONB"


def test_downgrade_and_upgrade_roundtrip(engine: Engine) -> None:
    assert TEST_DATABASE_URL
    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    assert "memories" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "memories" in inspect(engine).get_table_names()
