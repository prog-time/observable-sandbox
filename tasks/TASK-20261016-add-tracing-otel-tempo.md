# TASK-20261016-add-tracing-otel-tempo: Добавить распределённую трассировку (OpenTelemetry + Grafana Tempo)

**Type:** feature  
**Size:** L  
**Status:** todo
**GitHub Issue:** #6 — https://github.com/prog-time/observable-sandbox/issues/6

## Что делаем
Сейчас запрос прослеживается только по `request_id` в JSON-логах. Не видно, сколько времени ушло на запросы к БД, сериализацию ответа и собственно код обработчика. Добавляем распределённую трассировку: инструментируем FastAPI и SQLAlchemy через OpenTelemetry с OTLP-экспортом в Alloy, Alloy пересылает трейсы в новый сервис Grafana Tempo, Grafana и mcp-grafana получают Tempo как источник данных, а логи и трейсы связываются через `trace_id`. Объём больше одного дня, поэтому это родительская задача: работа разбита на четыре подзадачи, они перечислены в «Связанных задачах».

## Пользователь получает
Как **разработчик (или Claude Code через MCP `grafana-test`)**, я могу **открыть трейс любого запроса по `trace_id` из лога и увидеть разбивку времени по спанам HTTP-обработчика и SQL-запросов**, чтобы **находить причину медленных запросов без догадок по `duration_ms`**.

## Готово когда
- [ ] Given тестовый стенд поднят (`make test-up`), when выполняется `docker compose -p logger-test ps`, then сервис `tempo` в статусе running/healthy, а Alloy принимает OTLP (gRPC 4317 / HTTP 4318) и пересылает трейсы в Tempo
- [ ] Given приложение запущено с заданным OTLP-эндпоинтом, when выполняется `POST /orders`, then в Tempo появляется трейс с корневым серверным спаном `POST /orders` и дочерними спанами SQLAlchemy (по одному на SQL-запрос) с `db.statement`
- [ ] Given любой HTTP-запрос внутри активного спана, when приложение пишет JSON-лог (в том числе `http request` из middleware), then запись содержит поля `trace_id` и `span_id`, и `trace_id` совпадает с трейсом в Tempo
- [ ] Given у корневого спана есть атрибут `request_id`, when ищем трейс в Tempo по этому атрибуту (TraceQL `{ span.request_id = "<id>" }`), then находится тот же трейс, что и по `x-request-id` в Loki
- [ ] Given открыта Grafana (тест и прод), when смотрим источники данных, then есть datasource Tempo с `uid: tempo`, а у Loki настроен derived field `trace_id` со ссылкой на Tempo (переход лог → трейс в один клик)
- [ ] Given у datasource Tempo настроен `tracesToLogsV2` на Loki, when открываем спан в Grafana, then можно перейти к логам этого трейса
- [ ] Given в `docker-compose.test.yml` у `mcp-grafana` в `--enabled-tools` добавлена категория `tempo`, when Claude Code вызывает Tempo-инструменты MCP `grafana-test`, then получает трейс по `trace_id` и результаты поиска TraceQL
- [ ] Given OTLP-эндпоинт не задан (например, `pytest` с SQLite in-memory), when запускаются тесты, then приложение стартует без ошибок и без попыток сетевого экспорта, `make pytest` зелёный
- [ ] Given прод-сборка, when поднимается `logger-prod`, then порты Tempo и OTLP наружу не проброшены (как у Loki и Prometheus сейчас)

## Как делаем
- **Инфраструктура:** добавить сервис `tempo` (образ `grafana/tempo`, конфиг `deploy/tempo/tempo.yml`, локальное хранилище на томе `tempo-data`, retention через env по аналогии с `LOKI_RETENTION`) в `docker-compose.yml`. В тесте пробросить порт на `127.0.0.1:3200`, в проде не пробрасывать и добавить `restart: unless-stopped`. В `deploy/alloy/config.alloy` добавить цепочку `otelcol.receiver.otlp` → `otelcol.processor.batch` → `otelcol.exporter.otlp` (в `tempo:4317`, tls insecure). `app` получает `depends_on: [alloy]` или эндпоинт с ретраями.
- **Приложение:** в `requirements.txt` добавить `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy` (версии закрепить). Новый модуль `src/app/tracing.py` с `setup_tracing(settings, app, engine)`: `TracerProvider` с ресурсом `service.name=app` и `deployment.environment=<APP_ENV>`, `BatchSpanProcessor(OTLPSpanExporter)`, `FastAPIInstrumentor.instrument_app(app)`, `SQLAlchemyInstrumentor().instrument(engine=engine)`. Если OTLP-эндпоинт не задан, трейсинг не включается. Настройки добавить в `Settings` (`otel_exporter_otlp_endpoint`, `otel_traces_sampler_ratio` или стандартные `OTEL_*` env), env пробрасывается в `app` через `docker-compose.yml` и `.env.test` / `.env.prod.example`.
- **Связь логов и трейсов:** в `src/app/logging_config.py` расширить фильтр (или добавить новый), чтобы в каждую запись попадали `trace_id`/`span_id` из `opentelemetry.trace.get_current_span()` (hex, 32/16 символов, пусто вне спана). В middleware `observe_requests` (`src/app/main.py`) ставить атрибут `request_id` на текущий спан. Время сериализации отдельно не видно в стандартной FastAPI-инструментации; при необходимости добавить ручные спаны (см. Вопросы).
- **Grafana:** в обоих `datasources.yml` (`provisioning/datasources` и `provisioning/datasources-test`) добавить datasource `Tempo` (`uid: tempo`, `url: http://tempo:3200`, `tracesToLogsV2` → `loki`, `serviceMap` → `prometheus` по желанию). У Loki добавить `jsonData.derivedFields` с `matcherRegex` для `"trace_id":"(\w+)"` и `datasourceUid: tempo`. Grafana получает `depends_on` на `tempo`.
- **MCP и документация:** в `docker-compose.test.yml` дописать `tempo` в `--enabled-tools=...`. В `CLAUDE.md` добавить строку «Трейсы» в таблицу инструментов (datasource UID `tempo`), примеры TraceQL, поля `trace_id`/`span_id` в логах и рецепт «лог → трейс». В `README.md` дописать `tempo` в таблицу сервисов и схему доступа.

## Файлы
- `requirements.txt` — пакеты OpenTelemetry (SDK, OTLP exporter, инструментации FastAPI и SQLAlchemy)
- `src/app/tracing.py` — новый модуль: настройка TracerProvider, экспортёра и инструментаций
- `src/app/config.py` — настройки OTLP-эндпоинта, сэмплинга, имени сервиса
- `src/app/main.py` — вызов `setup_tracing` в `create_app`, атрибут `request_id` на спане в `observe_requests`
- `src/app/db.py` — при необходимости: точка инструментирования engine (`make_engine`)
- `src/app/logging_config.py` — `trace_id`/`span_id` в JSON-логах
- `tests/conftest.py` — фикстура с `InMemorySpanExporter` для тестов трейсинга
- `tests/test_tracing.py` — новый: спаны HTTP и SQL, `trace_id` в логах, отключение без эндпоинта
- `docker-compose.yml` — сервис `tempo`, том `tempo-data`, OTEL-env для `app`, зависимости `grafana`/`alloy`
- `docker-compose.test.yml` — порт Tempo на 127.0.0.1, категория `tempo` в `--enabled-tools` у `mcp-grafana`
- `docker-compose.prod.yml` — `tempo: restart: unless-stopped`, без проброса портов
- `deploy/tempo/tempo.yml` — новый: конфиг Tempo (OTLP receiver, local storage, retention)
- `deploy/alloy/config.alloy` — OTLP receiver → batch → exporter в Tempo
- `deploy/grafana/provisioning/datasources/datasources.yml` — datasource Tempo, derived fields у Loki
- `deploy/grafana/provisioning/datasources-test/datasources.yml` — то же для теста
- `.env.test`, `.env.prod.example` — `TEMPO_RETENTION`, при необходимости `OTEL_*`
- `CLAUDE.md` — Tempo-инструменты MCP, UID `tempo`, примеры TraceQL, связь лог ↔ трейс
- `README.md` — сервис `tempo` в таблице состава, обновлённая схема доступа Claude Code
- `deploy/grafana/dashboards/app.json` — ❓ нужна ли панель или ссылка на трейсы (см. Вопросы)

## Не делаем в этой задаче
- Метрики из спанов (span metrics / service graph через Tempo metrics-generator или Alloy connector), exemplars в Prometheus
- Трейсинг `loadgen` как клиента и пропагацию контекста во внешние сервисы (их нет)
- Ручные спаны для бизнес-логики сверх минимально нужного для разбивки «БД / сериализация / код»
- Алерты по трейсам и изменение дашборда `app.json` (если ответ на вопрос ниже не потребует)
- Внешнее объектное хранилище для Tempo (S3/MinIO): только локальный диск

## Вопросы
- ❓ Какую версию `grafana/tempo` закрепить (в стеке Loki 3.3.2, Grafana 11.4.0, Alloy v1.5.1) и какой retention для теста и прода (по аналогии с `LOKI_RETENTION` 72h/720h)?
- ❓ Сэмплинг в проде: 100% или `parentbased_traceidratio` с долей (какой)? В тесте предполагается 100%.
- ❓ «Время на сериализацию» стандартная FastAPI-инструментация отдельным спаном не показывает (есть только `http send`/`receive`). Нужен ручной спан вокруг сериализации ответа или достаточно разницы «корневой спан минус SQL-спаны»?
- ❓ Экспортировать трейсы через Alloy (как в описании задачи) или напрямую в Tempo? Предполагается Alloy; нужен ли тогда OTLP-порт Alloy на 127.0.0.1 в тесте для отладки?
- ❓ Делать ли `trace_id` дополнительно structured metadata в Loki (через `stage.structured_metadata` в Alloy, `allow_structured_metadata: true` уже включён), или достаточно derived field по JSON-полю в строке лога?
- ❓ Нужно проверить, какие именно Tempo-инструменты есть в `grafana/mcp-grafana:1.6.3` в категории `tempo` и совместимы ли они с `--disable-write`; если в 1.6.3 их нет, нужно ли обновлять образ?
- ❓ Включить ли трейсинг при `ENABLE_DEBUG_ENDPOINTS` для `/debug/slow` и `/debug/error` (удобно для демо) и исключать ли `/health` и `/metrics` из трейсов (`excluded_urls`)?
- ❓ Нужна ли в дашборде `app.json` панель с последними медленными трейсами (TraceQL-таблица)?

## Связанные задачи
- Зависит от: —
- Блокирует: —
- Подзадачи (файлы не созданы, завести отдельно):
  1. `TASK-20261016-add-tempo-alloy-otlp` (M): сервис Tempo в compose (база/тест/прод), `deploy/tempo/tempo.yml`, OTLP receiver → Tempo в `deploy/alloy/config.alloy`, env retention
  2. `TASK-20261016-instrument-app-otel` (L): OpenTelemetry SDK, инструментации FastAPI и SQLAlchemy, `src/app/tracing.py`, настройки в `config.py`, атрибут `request_id`, тесты с `InMemorySpanExporter`. Зависит от 1 только для ручной проверки на стенде
  3. `TASK-20261016-link-logs-traces-grafana` (M): `trace_id`/`span_id` в JSON-логах, datasource Tempo и derived fields Loki → Tempo, `tracesToLogsV2` в обоих provisioning. Зависит от 1 и 2
  4. `TASK-20261016-enable-mcp-tempo-docs` (S): категория `tempo` в `--enabled-tools` у `mcp-grafana`, обновление `CLAUDE.md` и `README.md`. Зависит от 3

## Критерии приёмки (Definition of Done)
- [ ] Критерии из "Готово когда" выполнены и покрыты автотестами
- [ ] Линтер и статический анализ зелёные
- [ ] Юнит- и интеграционные тесты зелёные локально (`make pytest`)
- [ ] Документация (README / rules/ / API docs) обновлена, если изменилось поведение
- [ ] Code review пройден
- [ ] Нет регрессий в смежных сценариях
