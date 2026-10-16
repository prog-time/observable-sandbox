"""Запуск миграций Alembic без alembic.ini.

    python -m app.migrate upgrade            # применить миграции (stamp базовой ревизии для БД, созданных create_all)
    python -m app.migrate revision "msg"     # autogenerate новой ревизии по app.models
    python -m app.migrate stamp <rev>        # вручную проставить ревизию
"""

import argparse
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.config import get_settings
from app.db import make_engine
from app.logging_config import setup_logging

logger = logging.getLogger("app.migrate")

# Первая ревизия: таблицы customers и orders, как их раньше создавал create_all
BASELINE_REVISION = "0001"
BASELINE_TABLES = {"customers", "orders"}


def build_config(database_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    url = database_url or get_settings().database_url
    # configparser трактует % как интерполяцию
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade(cfg: Config) -> None:
    engine = make_engine(cfg.get_main_option("sqlalchemy.url").replace("%%", "%"))
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    if "alembic_version" not in tables and BASELINE_TABLES & tables:
        logger.info(
            "tables exist without alembic_version (created by create_all): stamping baseline",
            extra={"revision": BASELINE_REVISION, "existing_tables": sorted(tables)},
        )
        command.stamp(cfg, BASELINE_REVISION)
    logger.info("running alembic upgrade head")
    command.upgrade(cfg, "head")
    logger.info("alembic upgrade head finished")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="app.migrate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("upgrade")
    rev = sub.add_parser("revision")
    rev.add_argument("message")
    st = sub.add_parser("stamp")
    st.add_argument("revision")
    args = parser.parse_args(argv)

    settings = get_settings()
    setup_logging(settings.log_level, settings.app_env, settings.sql_log_level)
    cfg = build_config()
    if args.cmd == "upgrade":
        upgrade(cfg)
    elif args.cmd == "revision":
        command.revision(cfg, message=args.message, autogenerate=True)
    elif args.cmd == "stamp":
        command.stamp(cfg, args.revision)


if __name__ == "__main__":
    main()
