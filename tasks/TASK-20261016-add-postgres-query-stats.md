# TASK-20261016-add-postgres-query-stats: Включить наблюдаемость SQL-запросов в тестовой среде

**Type:** feature  
**Size:** M  
**Status:** todo
**GitHub Issue:** #5 — https://github.com/prog-time/observable-sandbox/issues/5

## Что делаем
Сейчас Claude Code не видит, какие SQL-запросы приложение отправляет в PostgreSQL. Логгер `sqlalchemy.engine` приглушён до `WARNING` (`src/app/logging_config.py`), расширения `pg_stat_statements` нет (в `pg_extension` 0 строк), лог медленных запросов выключен (`log_min_duration_statement = -1`). Поэтому медленные запросы, N+1 и недостающие индексы найти нельзя. В тестовой среде (`logger-test`) включаем `pg_stat_statements`, лог медленных запросов и метрики `pg_stat_statements` в Prometheus.

## Пользователь получает
Как **Claude Code (через MCP `grafana-test`)**, я могу **увидеть топ запросов по времени и числу вызовов (`query_sql`), строки медленных запросов в Loki и метрики запросов в Prometheus**, чтобы **находить медленные запросы, N+1 и недостающие индексы без доступа к проду**.

## Готово когда
- [ ] Given тестовый стенд поднят с нуля (`make test-reset && make test-up`), when выполнить `SHOW shared_preload_libraries` через `query_sql` (datasource `postgres`, роль `claude_ro`), then в результате есть `pg_stat_statements`
- [ ] Given тестовый стенд поднят, when выполнить `SELECT extname FROM pg_extension WHERE extname = 'pg_stat_statements'` под `claude_ro`, then возвращается одна строка
- [ ] Given прогнан `make loadgen`, when под `claude_ro` выполнить `SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY total_exec_time DESC`, then видны запросы приложения к таблицам `customers`/`orders` с полным текстом (не `<insufficient privilege>`)
- [ ] Given тестовый стенд поднят, when выполнить `SHOW log_min_duration_statement`, then значение `200ms`
- [ ] Given выполнен запрос длительностью больше 200 мс (например `SELECT pg_sleep(0.3)` под ролью `app` или тяжёлый запрос приложения), when запросить в Loki `{service="db"} |= "duration:"`, then находится строка с длительностью и текстом запроса
- [ ] Given прогнан `make loadgen`, when через `list_prometheus_metric_names` / `query_prometheus` запросить `pg_stat_statements_*`, then метрики есть и содержат ненулевые значения (например `pg_stat_statements_calls_total`)
- [ ] Given запущен прод-стенд по `docker-compose.prod.yml`, when сравнить конфигурацию, then `db` и `postgres-exporter` в проде не изменились (без `shared_preload_libraries`, без коллектора stat_statements)
- [ ] Given стенд, поднятый раньше со старым томом `db-data` (init-скрипты повторно не запускаются), when выполнить шаг из документации, then расширение создаётся без удаления данных (или в документации прямо сказано, что нужен `make test-reset`)

## Как делаем
1. **`docker-compose.test.yml`, сервис `db`:** задать `command` с параметрами `postgres -c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track=all -c log_min_duration_statement=200ms` (при необходимости `-c track_io_timing=on`). Изменение только в тестовом override, базовый `docker-compose.yml` не трогаем.
2. **Новый init-скрипт `deploy/postgres/init-test/02-pg-stat-statements.sql`:** `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` в базе `${POSTGRES_DB}`. Скрипт выполняется после `01-claude-readonly.sh` (порядок по имени). Права для `claude_ro`: у роли уже есть `GRANT pg_read_all_stats` (в `01-claude-readonly.sh`), этого хватает, чтобы читать текст чужих запросов. View `pg_stat_statements` по умолчанию доступен PUBLIC. Проверить это и при необходимости добавить явный `GRANT SELECT`.
3. **`docker-compose.test.yml`, сервис `postgres-exporter`:** включить коллектор флагом `--collector.stat_statements` (в образе v0.16.0 он по умолчанию выключен). Если выбранная версия поддерживает, добавить `--collector.stat_statements.include_query` и ограничить длину и число запросов. Scrape-джоб `postgres` в `deploy/prometheus/prometheus.yml` уже есть, менять его не нужно.
4. **Логи:** Alloy уже собирает stdout контейнера `db` с меткой `service="db"`. Строки PostgreSQL не JSON, поэтому `stage.json` их пропускает. Проверить, что строки `LOG:  duration: … ms  statement: …` (и `execute <unnamed>` / `DETAIL: parameters:` от psycopg) приходят в Loki целиком. Парсинг длительности в метку не добавляем.
5. **Документация:** в `CLAUDE.md` (раздел «Как смотреть систему») и `README.md` описать, как смотреть запросы: `query_sql` по `pg_stat_statements`, LogQL `{service="db"} |= "duration:"`, метрики `pg_stat_statements_*`, сброс статистики. Отдельно указать, что на существующем томе нужен `make test-reset` или ручной `CREATE EXTENSION`.

## Файлы
- `docker-compose.test.yml`: `command` для `db` (shared_preload_libraries, pg_stat_statements.track, log_min_duration_statement), флаги коллектора для `postgres-exporter`
- `deploy/postgres/init-test/02-pg-stat-statements.sql`: новый, `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`
- `deploy/postgres/init-test/01-claude-readonly.sh`: только если для `claude_ro` понадобится явный `GRANT` (сейчас уже есть `pg_read_all_stats`)
- `CLAUDE.md`: инструкции для Claude, как искать медленные запросы и N+1
- `README.md`: краткое описание и шаг пересоздания тестовой БД
- `src/app/logging_config.py`: не меняем, `sqlalchemy.engine` остаётся на `WARNING` (см. Вопросы)
- ❓ тесты: `tests/` работают на SQLite in-memory (`tests/conftest.py`), поэтому автотест для pg_stat_statements туда не ложится. Формат проверки см. в Вопросах

## Не делаем в этой задаче
- Включение в прод (`docker-compose.prod.yml`, прод-`db`, прод-`postgres-exporter`), только по решению из «Вопросов»
- Сам поиск и исправление медленных запросов, N+1 и индексов: это отдельные задачи по результатам наблюдения
- Дашборд Grafana для `pg_stat_statements` в `deploy/grafana/dashboards/`
- Парсинг логов PostgreSQL в Alloy (метки `duration_ms`, уровень и т.п.)
- `auto_explain` и автоматические планы запросов
- Миграции схемы (их в проекте пока нет, таблицы создаёт `Base.metadata.create_all`)

## Вопросы
- ❓ Включать ли `pg_stat_statements` и `log_min_duration_statement` в проде? По умолчанию только тест. В проде роли `claude_ro` и MCP нет, но метрики в прод-Prometheus и slow log могли бы пригодиться человеку. Нужен рестарт прод-`db`.
- ❓ Порог `log_min_duration_statement`: 200ms или ниже (50–100ms), чтобы ловить N+1 из множества быстрых запросов? N+1 по slow log не видно, его видно по `calls` в `pg_stat_statements`.
- ❓ Нужно ли в тесте поднимать `sqlalchemy.engine` до `INFO` (через env, например `SQL_LOG_LEVEL`), чтобы SQL попадал в Loki с `request_id`? Это даст привязку запросов к HTTP-запросу, но сильно увеличит объём логов.
- ❓ Коллектор `stat_statements` в postgres-exporter v0.16.0: поддерживает ли эта версия `include_query` и лимиты, или нужно обновлять образ (тогда обновлять и в проде, потому что образ задан в базовом `docker-compose.yml`)?
- ❓ Что делать с текущим томом `db-data` тестовой среды: допустим `make test-reset` (данные теста теряются) или нужен идемпотентный способ создать расширение на живой БД (например `docker compose -p logger-test exec db psql …`)?
- ❓ Как проверять критерии автоматически: smoke-скрипт / make-цель (например `make test-check-sql-stats`) против поднятого стенда или ручная проверка через MCP `grafana-test`?
- ❓ Нужен ли Claude способ сбрасывать статистику (`pg_stat_statements_reset()`)? Под `claude_ro` (read-only) это недоступно без отдельного `GRANT EXECUTE`.

## Связанные задачи
- Зависит от: —
- Блокирует: —

## Критерии приёмки (Definition of Done)
- [ ] Критерии из "Готово когда" выполнены и покрыты автотестами
- [ ] Линтер и статический анализ зелёные
- [ ] Юнит- и интеграционные тесты зелёные локально
- [ ] Документация (README / rules/ / API docs) обновлена, если изменилось поведение
- [ ] Code review пройден
- [ ] Нет регрессий в смежных сценариях
