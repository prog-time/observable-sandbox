import os

# тесты не должны слать трейсы наружу, даже если контейнер запущен с OTLP-эндпоинтом
os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(
        app_env="unittest",
        database_url="sqlite+pysqlite:///:memory:",
        enable_debug_endpoints=True,
        log_level="WARNING",
    )
    app = create_app(settings)
    # схему в проде создаёт Alembic; для SQLite in-memory — create_all
    Base.metadata.create_all(app.state.engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def customer(client):
    r = client.post("/customers", json={"name": "Alice", "email": "alice@example.com"})
    assert r.status_code == 201
    return r.json()
