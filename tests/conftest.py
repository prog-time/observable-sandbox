import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(
        app_env="unittest",
        database_url="sqlite+pysqlite:///:memory:",
        enable_debug_endpoints=True,
        log_level="WARNING",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def customer(client):
    r = client.post("/customers", json={"name": "Alice", "email": "alice@example.com"})
    assert r.status_code == 201
    return r.json()
