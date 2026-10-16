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
- Метрики контейнеров (cAdvisor, job `cadvisor`): `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes` / `container_memory_usage_bytes` / `container_memory_rss`, `container_network_receive_bytes_total` / `container_network_transmit_bytes_total`, `container_fs_reads_bytes_total` / `container_fs_writes_bytes_total`, `container_blkio_device_usage_total`, `container_spec_memory_limit_bytes`, `container_oom_events_total`, `container_pressure_*`. Фильтр по сервису compose — метка `service` (app, db, loki, alloy, prometheus, grafana, …); в тестовый Prometheus попадают только контейнеры проекта `logger-test` (прод отфильтрован).
  Примеры PromQL: `sum by (service) (rate(container_cpu_usage_seconds_total{service!=""}[1m]))` (ядра CPU), `container_memory_working_set_bytes{service="db"}` (память, байты).
  Docker Desktop (macOS): нет `container_fs_usage_bytes` / `container_fs_limit_bytes` (размер файловой системы контейнера); `container_fs_reads/writes_bytes_total` и `container_blkio_*` есть. На Linux-хосте эти метрики, как ожидается, доступны (не проверялось). UI cAdvisor для человека: http://localhost:8082.
- `query_prometheus` с `queryType: instant` требует `endTime: "now"`.
- `query_sql` дописывает `LIMIT 100`. БД доступна только на чтение (роль `claude_ro`), менять данные — только через API приложения.
- Каждый ответ API содержит заголовок `x-request-id` — по нему в Loki видна вся цепочка запроса.
- После перезапуска `app` счётчики Prometheus обнуляются. Нет данных → `make loadgen` (60 с трафика с ошибками и медленными запросами).
- SQL-запросы (только тест):
  - Статистика: `query_sql` по `pg_stat_statements` (полный текст запросов доступен, `claude_ro` имеет `pg_read_all_stats`), например
    `SELECT calls, round(mean_exec_time::numeric,2) AS ms, left(query,100) AS q FROM pg_stat_statements ORDER BY total_exec_time DESC` — топ по времени; сортировка по `calls` помогает найти N+1. Сбросить статистику ролью `claude_ro` нельзя.
  - Медленные запросы (>100ms): `{service="db"} |= "duration:"` в Loki (строки PostgreSQL не JSON, метки `service="db"`).
  - Все SQL приложения с `request_id` (`SQL_LOG_LEVEL=INFO` в `.env.test`): `{service="app", logger="sqlalchemy.engine.Engine"}`; в проде `WARNING`, запросы не пишутся.
  - Метрики: `pg_stat_statements_*` (например `pg_stat_statements_calls_total`), коллектор включён только в тесте.
  - `SHOW ...` через `query_sql` не работает (дописывается `LIMIT`) — используйте `SELECT ... FROM pg_settings`.
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
- `deploy/prometheus/scrape.d-test|prod/cadvisor.yml` — job cAdvisor со своим фильтром compose-проекта для каждой среды (изоляция test/prod на одном Docker-хосте)
- `src/app/migrate.py`, `src/app/migrations/` — миграции Alembic (без `alembic.ini`, конфиг собирается в коде; URL — из `DATABASE_URL`).
- Схема БД управляется миграциями Alembic; `create_all` используется только в `tests/conftest.py` (SQLite in-memory).

## Миграции

- Контейнер `app` (test и prod) при старте выполняет `python -m app.migrate upgrade`, затем uvicorn. Если таблицы есть, а `alembic_version` нет (БД создана старым `create_all`), базовая ревизия `0001` проставляется через `stamp`, затем `upgrade head`.
- Изменили модели в `src/app/models.py` → `make migration MSG="описание"` (autogenerate внутри тестового контейнера, файл появится в `src/app/migrations/versions/`) → **вычитать и поправить руками** → `make migrate` (или перезапуск `app`) → `make pytest`.
- `make migrate` идемпотентен. Миграции идут от пользователя `app`, поэтому `claude_ro` получает `SELECT` на новые таблицы через `ALTER DEFAULT PRIVILEGES`.
- Миграции должны работать и на SQLite (`render_as_batch`): `tests/test_migrations.py` проверяет, что `upgrade head` не расходится с моделями. Для `server_default` используй `sa.func.now()`, а не `sa.text("now()")`.

## Соглашения

- Логи — через `logging.getLogger(__name__)`, контекст передавать в `extra={...}` (попадёт в JSON-поля).
- Новые метрики — в `src/app/metrics.py`; метка `route` — шаблон пути, не фактический URL.
