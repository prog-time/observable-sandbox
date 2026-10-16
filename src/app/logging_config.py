"""JSON-логи в stdout: их собирает Alloy и отправляет в Loki."""

import logging
import sys
from contextvars import ContextVar

from opentelemetry import trace
from pythonjsonlogger.json import JsonFormatter

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        ctx = trace.get_current_span().get_span_context()
        record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else None
        record.span_id = format(ctx.span_id, "016x") if ctx.is_valid else None
        return True


def setup_logging(level: str, env: str, sql_level: str = "WARNING") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            static_fields={"env": env},
        )
    )
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # Uvicorn настраивает свои хендлеры до импорта приложения — перенаправляем их в root.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # Access-лог пишет наш middleware (с request_id и длительностью).
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level.upper())
