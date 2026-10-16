from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db import Base
from app.migrate import build_config, upgrade


def test_upgrade_matches_models(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'm.db'}"
    cfg = build_config(url)
    upgrade(cfg)

    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
    assert {"customers", "orders", "alembic_version"} <= set(inspect(engine).get_table_names())

    # повторный запуск — no-op; откат и повторный накат работают
    upgrade(cfg)
    command.downgrade(cfg, "base")
    assert "orders" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")


def test_upgrade_stamps_preexisting_schema(tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)  # БД, созданная старым create_all
    upgrade(build_config(url))
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001"
