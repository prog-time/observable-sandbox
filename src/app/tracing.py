"""Трассировка OpenTelemetry: спаны FastAPI и SQLAlchemy уходят по OTLP/HTTP в Alloy → Tempo.

Включается только при заданном OTEL_EXPORTER_OTLP_ENDPOINT; остальное читается SDK из стандартных OTEL_* переменных.
"""

import logging
import os

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy import Engine

from app.config import Settings

logger = logging.getLogger("app")

EXCLUDED_URLS = "health,metrics"


class DropOrphanSqlSpans(SpanProcessor):
    """Отбрасывает SQL-спаны без родителя (запросы вне HTTP-запроса, напр. SELECT 1 из /health, который исключён из трассировки)."""

    def __init__(self, inner: SpanProcessor):
        self._inner = inner

    def on_start(self, span, parent_context=None):
        self._inner.on_start(span, parent_context=parent_context)

    def on_end(self, span):
        if span.parent is None and "sqlalchemy" in span.instrumentation_scope.name:
            return
        self._inner.on_end(span)

    def shutdown(self):
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000):
        return self._inner.force_flush(timeout_millis)


def instrument(app: FastAPI, engine: Engine, provider: TracerProvider) -> None:
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls=EXCLUDED_URLS)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)


def uninstrument(app: FastAPI, engine: Engine) -> None:
    FastAPIInstrumentor.uninstrument_app(app)
    SQLAlchemyInstrumentor().uninstrument()


def setup_tracing(app: FastAPI, engine: Engine, settings: Settings) -> TracerProvider | None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return None
    if getattr(app.state, "tracer_provider", None) is not None:
        return app.state.tracer_provider  # идемпотентность (uvicorn --reload, повторный вызов)

    # service.name, deployment.environment и сэмплер SDK берёт из OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES / OTEL_TRACES_SAMPLER*
    provider = TracerProvider(resource=Resource.create())
    provider.add_span_processor(DropOrphanSqlSpans(BatchSpanProcessor(OTLPSpanExporter())))
    instrument(app, engine, provider)
    app.state.tracer_provider = provider
    logger.info("tracing enabled", extra={"otlp_endpoint": os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]})
    return provider


def shutdown_tracing(app: FastAPI) -> None:
    provider = getattr(app.state, "tracer_provider", None)
    if provider is not None:
        provider.shutdown()  # сбрасывает буфер BatchSpanProcessor
        app.state.tracer_provider = None
