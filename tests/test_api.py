from prometheus_client import REGISTRY


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "x-request-id" in r.headers


def test_duplicate_customer_email(client, customer):
    r = client.post("/customers", json={"name": "Alice 2", "email": customer["email"]})
    assert r.status_code == 409


def test_order_lifecycle(client, customer):
    r = client.post("/orders", json={"customer_id": customer["id"], "amount": "99.90"})
    assert r.status_code == 201
    order = r.json()
    assert order["status"] == "new"

    r = client.patch(f"/orders/{order['id']}/status", json={"status": "paid"})
    assert r.status_code == 200
    assert r.json()["status"] == "paid"

    r = client.patch(f"/orders/{order['id']}/status", json={"status": "new"})
    assert r.status_code == 409

    r = client.get("/orders", params={"status": "paid"})
    assert [o["id"] for o in r.json()] == [order["id"]]


def test_order_for_unknown_customer(client):
    r = client.post("/orders", json={"customer_id": 999, "amount": "10"})
    assert r.status_code == 404


def test_metrics_exposed(client, customer):
    client.post("/orders", json={"customer_id": customer["id"], "amount": "5"})
    body = client.get("/metrics").text
    assert "http_requests_total" in body
    assert "orders_created_total" in body


def test_debug_error_returns_500(client):
    assert client.get("/debug/error").status_code == 500


def _requests_count(method, route, status):
    value = REGISTRY.get_sample_value(
        "http_requests_total", {"method": method, "route": route, "status": status}
    )
    return value or 0


def test_route_label_for_service_routes(client):
    cases = [
        ("/openapi.json", "/openapi.json", "200"),
        ("/docs", "/docs", "200"),
        ("/redoc", "/redoc", "200"),
        ("/no-such-path", "unmatched", "404"),
    ]
    for path, route, status in cases:
        before = _requests_count("GET", route, status)
        assert client.get(path).status_code == int(status)
        assert _requests_count("GET", route, status) == before + 1, path


def test_route_label_is_template_not_actual_path(client, customer):
    r = client.post("/orders", json={"customer_id": customer["id"], "amount": "5"})
    order_id = r.json()["id"]
    before = _requests_count("PATCH", "/orders/{order_id}/status", "200")
    client.patch(f"/orders/{order_id}/status", json={"status": "paid"})
    assert _requests_count("PATCH", "/orders/{order_id}/status", "200") == before + 1
    assert _requests_count("PATCH", f"/orders/{order_id}/status", "200") == 0


def test_route_label_for_wrong_method_is_template(client):
    before = _requests_count("DELETE", "/openapi.json", "405")
    assert client.delete("/openapi.json").status_code == 405
    assert _requests_count("DELETE", "/openapi.json", "405") == before + 1
