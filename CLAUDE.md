# test.logger

Учебный Python-сервис (FastAPI + SQLAlchemy + PostgreSQL) с полной обвязкой наблюдаемости.
Цель проекта — чтобы Claude Code видел систему целиком: код, логи, метрики и данные в БД.

## Среды

| | Тест (`logger-test`) | Прод (`logger-prod`) |
|---|---|---|
| Запуск | `make test-up` | `make prod-up` |
| Env-файл | `.env.test` (в репо) | `.env.prod` (не в репо) |
| Образ app | target `test`, hot-reload из `./src` | target `prod` |
| Порты | всё на 127.0.0.1 | только app `:8080`, Grafana `127.0.0.1:3001` |
| Доступ Claude | **да** | **нет — не трогать** |

**Правило: работай только с тестовой средой.** Никогда не запускай `make prod-*`,
`docker compose -p logger-prod ...` и не читай `.env.prod`.

## Как смотреть систему (тестовая среда)

Логи, метрики и данные БД доступны через MCP-сервер **`grafana-test`** (mcp-grafana, `.mcp.json`).
Он работает только в тестовой сборке — сначала `make test-up`.

| Что | Инструмент | Datasource UID |
|---|---|---|
| Логи | `query_loki_logs`, `query_loki_patterns`, `list_loki_label_values` | `loki` |
| Метрики | `query_prometheus`, `query_prometheus_histogram`, `list_prometheus_metric_names` | `prometheus` |
| БД | `query_sql`, `list_sql_tables`, `describe_sql_table` | `postgres` |
| Дашборды | `search_dashboards`, `get_dashboard_summary` | — |

- Метки логов: `service` (app, db, loki, …), `level` (DEBUG/INFO/WARNING/ERROR), `logger`, `project`, `env`.
  Примеры LogQL: `{service="app", level="ERROR"}`, `{service="app"} | json | duration_ms > 1000`, `{project="logger-test"} |= "<request_id>"`.
- Метрики приложения: `http_requests_total{route,status}`, `http_request_duration_seconds`, `orders_created_total`, `order_status_changes_total`; БД — `pg_*`.
- `query_prometheus` с `queryType: instant` требует `endTime: "now"`.
- `query_sql` дописывает `LIMIT 100`. БД доступна только на чтение (роль `claude_ro`), менять данные — только через API приложения.
- Каждый ответ API содержит заголовок `x-request-id` — по нему в Loki видна вся цепочка запроса.
- После перезапуска `app` счётчики Prometheus обнуляются. Нет данных → `make loadgen` (60 с трафика с ошибками и медленными запросами).
- Состояние контейнеров: `docker compose -p logger-test ps`. Тесты: `make pytest`.
- Adminer (http://localhost:8081) — веб-интерфейс БД для человека; Claude использует `query_sql`.

### Что Claude может запускать сам

Правила в `.claude/settings.json` (короткая форма `docker compose -p logger-test ...` и полная из Makefile с `--env-file .env.test -f ...`):

- Без подтверждения: `ps`, `logs`, `config`, `top`, `images`, `exec app pytest` (в т.ч. `exec -T`), а также `make test-up`, `make test-down`, `make test-ps`, `make pytest`, `make loadgen`.
- Запрещено: `down -v` / `down --volumes`, любой `exec db ...`, `make test-reset`, `docker volume rm logger-test_*` (человек может запустить `make test-reset` в своём терминале).
- Всё остальное (`up` напрямую, `restart`, `stop`, `rm`, `run`, `exec app sh`, `exec app python ...`) требует подтверждения.
- Запись в БД — только через API приложения.
- Оговорка: правила `deny` префиксные, поэтому это best-effort защита (лишние флаги перед подкомандой меняют префикс). Реальные гарантии — read-only роль `claude_ro` и недоступность прода.

## Цикл работы

1. Изменить код в `src/app/` — uvicorn в тесте перезагрузится сам.
2. `make pytest`.
3. Дёрнуть API / `make loadgen`.
4. Проверить результат через MCP `grafana-test`: логи, метрики, данные.

## Структура

- `src/app/main.py` — фабрика приложения, middleware логирования/метрик, `/health`, `/metrics`
- `src/app/api/` — роуты: `customers`, `orders`, `debug` (только при `ENABLE_DEBUG_ENDPOINTS=true`)
- `src/app/models.py` — модели и допустимые переходы статусов заказа
- `src/app/logging_config.py` — JSON-логи в stdout, `request_id` через contextvar
- `src/app/metrics.py` — метрики Prometheus
- `deploy/` — конфиги Loki, Alloy, Prometheus, Grafana (в `datasources-test` — с PostgreSQL), init-скрипт БД для теста
- Таблицы создаются через `Base.metadata.create_all` при старте (миграций пока нет).

## Соглашения

- Логи — через `logging.getLogger(__name__)`, контекст передавать в `extra={...}` (попадёт в JSON-поля).
- Новые метрики — в `src/app/metrics.py`; метка `route` — шаблон пути, не фактический URL.
