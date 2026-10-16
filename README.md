# test.logger

Тестовый Python-проект для проверки подхода «Claude Code видит систему целиком»:
код, логи, метрики и данные БД. Доступ есть **только в тестовой среде**.

## Состав

| Сервис | Назначение | Тест | Прод |
|---|---|---|---|
| `app` | FastAPI: клиенты и заказы, JSON-логи, `/metrics` | 127.0.0.1:8000, hot-reload | :8080 |
| `db` | PostgreSQL 16 | 127.0.0.1:5432 + роль `claude_ro` | только внутри сети |
| `postgres-exporter` | метрики PostgreSQL | внутри сети | внутри сети |
| `loki` | хранилище логов | 127.0.0.1:3100 | внутри сети |
| `alloy` | сбор stdout контейнеров → Loki; приём трейсов OTLP (4317/4318) → Tempo | 127.0.0.1:12345 | внутри сети |
| `tempo` | хранилище трейсов (Grafana Tempo 2.10, локальный диск) | 127.0.0.1:3200 | внутри сети |
| `prometheus` | метрики | 127.0.0.1:9090 | внутри сети |
| `cadvisor` | метрики ресурсов контейнеров (`container_*`): CPU, память, сеть, диск | 127.0.0.1:8082 | внутри сети |
| `grafana` | дашборды (логи + метрики) | 127.0.0.1:3000, без логина, + datasource PostgreSQL | 127.0.0.1:3001, с паролем |
| `mcp-grafana` | MCP-сервер для Claude Code | 127.0.0.1:8001 | — |
| `adminer` | веб-интерфейс БД | 127.0.0.1:8081 | — |

Сборка состоит из трёх файлов: `docker-compose.yml` (база) + `docker-compose.test.yml` или `docker-compose.prod.yml`.
Проекты называются по-разному (`logger-test` / `logger-prod`), поэтому у них раздельные тома, и обе среды
могут работать одновременно. Alloy собирает логи только своего проекта.

## Быстрый старт

```bash
make test-up      # собрать и поднять тестовый стенд
make loadgen      # 60 секунд трафика (DURATION=120 make loadgen)
make pytest       # тесты внутри контейнера
make migrate      # применить миграции Alembic (идемпотентно; также выполняется при старте app)
make migration MSG="add column"   # сгенерировать новую ревизию по изменениям моделей
open http://localhost:3000   # Grafana → папка test.logger
open http://localhost:8000/docs
open http://localhost:8081      # Adminer: PostgreSQL / db / app / claude_ro (или app для записи)
```

SQL-наблюдаемость (только тест): `pg_stat_statements` (топ запросов через `query_sql`), лог запросов дольше 100 мс
в Loki (`{service="db"} |= "duration:"`), SQL приложения с `request_id` (`SQL_LOG_LEVEL=INFO`) и метрики `pg_stat_statements_*`.
`make test-up` идемпотентно создаёт расширение одноразовым сервисом `db-init`, поэтому существующий том сохраняется
и `make test-reset` не нужен (после смены `shared_preload_libraries` контейнер `db` пересоздаётся автоматически).

Схема БД ведётся миграциями Alembic (`src/app/migrations/`). При старте `app` выполняет `python -m app.migrate upgrade`;
для БД, созданной раньше через `create_all`, базовая ревизия проставляется автоматически (`stamp`), данные сохраняются.

Прод:
```bash
cp .env.prod.example .env.prod   # задать пароли
make prod-up
```

## Как Claude Code получает доступ к тесту

Без самописных скриптов — через готовый [mcp-grafana](https://github.com/grafana/mcp-grafana):

```
Claude Code ──MCP──> mcp-grafana ──> Grafana (тест) ──> Loki / Prometheus / Tempo / PostgreSQL (claude_ro)
```

1. **`.mcp.json`** подключает сервер `grafana-test` (`http://127.0.0.1:8001/mcp`); `.claude/settings.json` включает его и разрешает его инструменты.
2. **`mcp-grafana`** запущен с `--disable-write` (без изменения дашбордов и алертов) и набором инструментов `search,datasource,prometheus,loki,dashboard,navigation,sql,tempo`.
3. **PostgreSQL** подключён в тестовую Grafana под ролью `claude_ro` — только чтение, `statement_timeout=10s`. Запись блокирует сама БД, а не MCP.
4. **`CLAUDE.md`** описывает инструменты, метки и правила; запуск `make prod-*`, `-p logger-prod` и чтение `.env.prod` запрещены в `.claude/settings.json`.
   Compose для `logger-test` разрешён только узким списком (`ps`, `logs`, `config`, `top`, `images`, `exec app pytest`); `down -v`, `exec db`, `make test-reset` запрещены, остальное требует подтверждения. Правила префиксные (best-effort), реальная защита — роль `claude_ro`.

Почему прод недоступен не только по правилам: сервиса `mcp-grafana` в прод-сборке нет, прод-Grafana не знает о PostgreSQL и требует пароль, порты БД, Loki и Prometheus не проброшены, роли `claude_ro` нет.

При первом запуске Claude Code в каталоге проекта может спросить подтверждение для MCP-сервера из `.mcp.json`; проверить подключение — `/mcp`.

## Трассировка

```
app ──OTLP/HTTP :4318──> alloy ──OTLP/gRPC :4317──> tempo <── Grafana (datasource `tempo`) <── MCP (инструменты `*_tempo_*`)
```

- Приложение отправляет спаны в Alloy (`OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318`); Alloy (`otelcol.receiver.otlp` → `otelcol.processor.batch` → `otelcol.exporter.otlp`) пересылает их в Tempo. Порты OTLP наружу не публикуются; в тесте для отладки открыт только HTTP API Tempo `127.0.0.1:3200` (`/ready`, `/api/traces/<trace_id>`). Метрики Tempo собирает Prometheus (job `tempo`).
- Сэмплинг задаётся `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` в env-файле: тест — `always_on` (100%), прод — `parentbased_traceidratio` с долей `0.1`. Хранение — `TEMPO_RETENTION` (тест 72h, прод 720h), данные в томе `tempo-data`.
- Образ Tempo закреплён на 2.10.x: ветка 3.x требует Kafka-совместимую очередь, а здесь нужен однобинарный режим с локальным диском. Образ distroless, healthcheck не задан.
- В приложении (`src/app/tracing.py`) трассировка включается только при заданном `OTEL_EXPORTER_OTLP_ENDPOINT` (в pytest и при локальном запуске выключена). Инструментированы FastAPI (серверный спан на запрос, `/health` и `/metrics` исключены) и SQLAlchemy (спан на каждый SQL с `db.statement`). `request_id` записывается атрибутом серверного спана, а `trace_id`/`span_id` попадают в каждую JSON-строку лога (`null` вне спана): по `x-request-id` трейс ищется TraceQL `{ span.request_id = "<id>" }`.
- Лог → трейс: в Grafana (Explore → Loki) у строки лога с `trace_id` есть ссылка `TraceID` на Tempo; из спана в Tempo можно перейти к логам этого трейса. Claude Code делает то же через `get_tempo_trace` / `search_tempo_traces`.
- После правки `deploy/prometheus/prometheus.yml` или `deploy/alloy/config.alloy` перезапустите соответствующий сервис (`docker compose -p logger-test restart prometheus`): `make test-up` не перезапускает контейнеры при изменении смонтированных файлов.

## API

- `POST /customers`, `GET /customers`, `GET /customers/{id}`
- `POST /orders`, `GET /orders?status=&customer_id=`, `GET /orders/{id}`, `PATCH /orders/{id}/status`
  (переходы: new → paid|cancelled, paid → shipped|cancelled)
- `GET /health`, `GET /metrics`
- Только в тесте: `GET /debug/error` (500 со стектрейсом), `GET /debug/slow?ms=1500`
