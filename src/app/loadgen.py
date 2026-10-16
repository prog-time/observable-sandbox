"""Генератор трафика для тестовой среды: наполняет БД, логи и метрики.

Запуск: make loadgen   (или python -m app.loadgen --base-url http://localhost:8000 --seconds 60)
"""

import argparse
import random
import time
import uuid

import httpx


def run(base_url: str, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    stats = {"ok": 0, "client_err": 0, "server_err": 0}
    with httpx.Client(base_url=base_url, timeout=15) as client:
        customer_ids: list[int] = []
        order_ids: list[int] = []
        while time.monotonic() < deadline:
            action = random.choices(
                ["customer", "order", "status", "list", "missing", "error", "slow"],
                weights=[10, 30, 20, 25, 8, 3, 4],
            )[0]
            if action == "customer" or not customer_ids:
                r = client.post(
                    "/customers",
                    json={"name": f"User {uuid.uuid4().hex[:6]}", "email": f"{uuid.uuid4().hex[:10]}@example.com"},
                )
                if r.status_code == 201:
                    customer_ids.append(r.json()["id"])
            elif action == "order":
                r = client.post(
                    "/orders",
                    json={"customer_id": random.choice(customer_ids), "amount": round(random.uniform(5, 500), 2)},
                )
                if r.status_code == 201:
                    order_ids.append(r.json()["id"])
            elif action == "status" and order_ids:
                r = client.patch(
                    f"/orders/{random.choice(order_ids)}/status",
                    json={"status": random.choice(["paid", "shipped", "cancelled"])},
                )
            elif action == "missing":
                r = client.get(f"/orders/{random.randint(10**6, 10**7)}")
            elif action == "error":
                r = client.get("/debug/error")
            elif action == "slow":
                r = client.get("/debug/slow", params={"ms": random.randint(300, 2500)})
            else:
                r = client.get("/orders", params={"limit": 20})

            if r.status_code >= 500:
                stats["server_err"] += 1
            elif r.status_code >= 400:
                stats["client_err"] += 1
            else:
                stats["ok"] += 1
            time.sleep(random.uniform(0.05, 0.3))
    print(stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    run(args.base_url, args.seconds)
