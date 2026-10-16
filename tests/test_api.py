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
