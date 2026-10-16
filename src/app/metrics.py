from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
ORDERS_CREATED = Counter("orders_created_total", "Orders created")
ORDER_STATUS_CHANGES = Counter(
    "order_status_changes_total", "Order status transitions", ["to_status"]
)
