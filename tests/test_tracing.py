import json
import logging
import re

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.tracing import DropOrphanSqlSpans, instrument, setup_tracing, uninstrument


@pytest.fixture
def traced():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(DropOrphanSqlSpans(SimpleSpanProcessor(exporter)))
    settings = Settings(
        app_env="unittest", database_url="sqlite+pysqlite:///:memory:", enable_debug_endpoints=True, log_level="INFO"
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    instrument(app, app.state.engine, provider)
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            exporter.clear()
            yield c, exporter
    finally:
        uninstrument(app, app.state.engine)


def test_orders_request_produces_server_and_sql_spans(traced):
    client, exporter = traced
    r = client.get("/orders")
    assert r.status_code == 200
    spans = exporter.get_finished_spans()
    server = [s for s in spans if s.attributes.get("http.route") == "/orders"]
    assert len(server) == 1
    sql = [s for s in spans if s.attributes.get("db.statement") or s.attributes.get("db.query.text")]
    assert sql
    assert {s.context.trace_id for s in sql} == {server[0].context.trace_id}
    assert server[0].attributes["request_id"] == r.headers["x-request-id"]


def test_request_id_from_header_is_span_attribute(traced):
    client, exporter = traced
    client.get("/orders", headers={"x-request-id": "abc123"})
    server = [s for s in exporter.get_finished_spans() if s.attributes.get("http.route") == "/orders"]
    assert server[0].attributes["request_id"] == "abc123"


def test_health_and_metrics_are_not_traced(traced):
    client, exporter = traced
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
    assert exporter.get_finished_spans() == ()


def test_log_inside_request_has_trace_id(traced, caplog):
    client, exporter = traced
    with caplog.at_level(logging.INFO, logger="app"):
        client.get("/orders")
    rec = next(r for r in caplog.records if r.getMessage() == "http request")
    assert re.fullmatch(r"[0-9a-f]{32}", rec.trace_id)
    assert re.fullmatch(r"[0-9a-f]{16}", rec.span_id)
    server = [s for s in exporter.get_finished_spans() if s.attributes.get("http.route") == "/orders"]
    assert rec.trace_id == format(server[0].context.trace_id, "032x")


def test_log_outside_span_has_null_trace_id(capsys):
    create_app(Settings(database_url="sqlite+pysqlite:///:memory:", log_level="INFO"))
    logging.getLogger("app").info("no span")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["trace_id"] is None and line["span_id"] is None


def test_tracing_is_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    assert setup_tracing(app, app.state.engine, app.state.settings) is None
    assert getattr(app.state, "tracer_provider", None) is None
