# TASK-20261016-migrate-schema-to-alembic: Перевести управление схемой БД на миграции Alembic

**Type:** refactor  
**Size:** M  
**Status:** todo
**GitHub Issue:** #3 — https://github.com/prog-time/observable-sandbox/issues/3

## Что делаем
Сейчас таблицы `customers` и `orders` создаются через `Base.metadata.create_all(engine)` в `lifespan` (`src/app/main.py`). `create_all` только создаёт отсутствующие таблицы и не меняет существующие, поэтому любое изменение моделей требует пересоздания БД (`make test-reset`), а в проде так нельзя. Переводим управление схемой на Alembic: начальная миграция с текущими таблицами, `alembic upgrade head` при старте контейнера и/или отдельной make-целью, `create_all` уходит из рабочего пути (остаётся только для unit-тестов на SQLite in-memory).

## Пользователь получает
Как **разработчик**, я могу **менять модели SQLAlchemy и выкатывать изменения схемы миграцией Alembic**, чтобы **не пересоздавать БД и не терять данные в тесте и проде**.

## Готово когда
- [ ] Given пустая БД тестового стенда (`make test-reset && make test-up`), when контейнер `app` стартует, then `alembic upgrade head` выполняется от пользователя `app`, создаются таблицы `customers`, `orders` и `alembic_version`, `/health` отвечает 200
- [ ] Given тестовый стенд поднят, when выполняется `make migrate` (или выбранное имя цели), then команда `alembic upgrade head` отрабатывает внутри контейнера `app` и при актуальной схеме ничего не меняет (идемпотентно)
- [ ] Given схема создана миграцией, when Claude выполняет `query_sql` / `list_sql_tables` под ролью `claude_ro`, then `SELECT` по `customers` и `orders` работает (права пришли через `ALTER DEFAULT PRIVILEGES FOR ROLE app`)
- [ ] Given БД после `alembic upgrade head`, when выполняется `alembic check` (или `alembic revision --autogenerate` в dry-режиме), then расхождений между моделями и схемой нет — начальная миграция совпадает с `Base.metadata` (колонки, типы, `unique` на `email`, индексы на `orders.customer_id` и `orders.status`, FK, `server_default=now()`)
- [ ] Given код приложения, when ищем вызовы `create_all`, then в `lifespan`/рабочем пути их нет; остался только путь для unit-тестов на SQLite in-memory
- [ ] Given `make pytest`, when тесты запускаются на `sqlite+pysqlite:///:memory:`, then все существующие тесты в `tests/test_api.py` зелёные без правок
- [ ] Given проверен `alembic downgrade base`, when затем снова `alembic upgrade head`, then схема восстанавливается без ошибок

## Как делаем
- Добавить `alembic` в `requirements.txt` (runtime-зависимость: миграции запускаются и в прод-образе).
- Инициализировать Alembic так, чтобы конфиг и миграции попадали в оба образа и в hot-reload том теста: `docker-compose.test.yml` монтирует только `./src` и `./tests`, а Dockerfile копирует только `src` — поэтому каталог миграций разместить внутри `src/` (например, `src/app/migrations/`) либо явно добавить `COPY`/volume для `alembic.ini` и каталога миграций. `env.py` берёт URL из `app.config.get_settings().database_url` (env `DATABASE_URL`), `target_metadata = Base.metadata` с импортом `app.models`.
- Сгенерировать начальную ревизию (`alembic revision --autogenerate -m "initial customers and orders"`) против пустой PostgreSQL и вычитать её руками: индексы, `unique`, `server_default=sa.text("now()")`, `downgrade` удаляет `orders`, затем `customers`.
- Запуск миграций: при старте контейнера — сменить `CMD` в Dockerfile (test и prod) на `sh -c "alembic upgrade head && uvicorn ..."` или вынести в entrypoint-скрипт; плюс make-цель `migrate: $(TEST) exec app alembic upgrade head` (и при необходимости `migrate-revision` для генерации ревизий). Миграции выполняются под `DATABASE_URL` сервиса `app`, т.е. от `POSTGRES_USER=app` — владелец таблиц `app`, поэтому `ALTER DEFAULT PRIVILEGES FOR ROLE app` из `deploy/postgres/init-test/01-claude-readonly.sh` выдаёт `claude_ro` `SELECT` автоматически; init-скрипт не меняем.
- Убрать `Base.metadata.create_all(engine)` из `lifespan` в `src/app/main.py`. Для unit-тестов: создавать схему в `tests/conftest.py` (через `app.state`/engine) или оставить `create_all` под явным условием только для SQLite — выбрать вариант, не меняющий тесты в `tests/test_api.py`. Обновить строку «Таблицы создаются через `Base.metadata.create_all` при старте (миграций пока нет)» в `CLAUDE.md` и описать `make migrate` в `README.md`.

## Файлы
- `requirements.txt` — добавить `alembic` (зафиксированная версия)
- `alembic.ini` — новый; ❓ расположение (корень проекта vs `src/`) зависит от того, как он попадёт в образ и том
- `src/app/migrations/env.py` — новый, ❓ точный путь каталога миграций; подключение `Base.metadata` и `DATABASE_URL`
- `src/app/migrations/script.py.mako` — новый, шаблон ревизий
- `src/app/migrations/versions/<rev>_initial_customers_and_orders.py` — новый, начальная миграция
- `src/app/main.py` — убрать `create_all` из `lifespan`
- `src/app/db.py` — при необходимости хелпер для создания схемы в тестах
- `tests/conftest.py` — создание схемы на SQLite in-memory для unit-тестов
- `Dockerfile` — `CMD`/entrypoint с `alembic upgrade head` для таргетов `test` и `prod`; при необходимости `COPY alembic.ini`
- `docker-compose.test.yml` — ❓ возможно, дополнительный volume для `alembic.ini`, если он вне `src/`
- `Makefile` — цель `migrate` (и, опционально, `migrate-revision`), добавить в `.PHONY`
- `CLAUDE.md` — заменить упоминание `create_all`, описать работу с миграциями
- `README.md` — раздел/строка про `make migrate`

## Не делаем в этой задаче
- Изменения самих моделей `Customer`/`Order` и любые новые таблицы/колонки
- Изменения роли `claude_ro` и `deploy/postgres/init-test/01-claude-readonly.sh`
- Прогон миграций на прод-стенде (`make prod-*` Claude не запускает); только подготовка образа и инструкции
- Отдельный сервис/джоб миграций в compose и CI-проверку миграций
- Перевод unit-тестов с SQLite на PostgreSQL

## Вопросы
- ❓ Запуск миграций: при каждом старте контейнера (CMD/entrypoint), только make-целью, или оба варианта? Для прода — автоматически при старте или вручную перед выкаткой?
- ❓ Существующие БД (тестовый том `logger-test_db-data` и прод), где таблицы уже созданы `create_all`: делаем `alembic stamp head` (нужна make-цель/инструкция) или для теста достаточно `make test-reset`? Для прода нужен документированный шаг `stamp`.
- ❓ Где разместить `alembic.ini` и каталог миграций: внутри `src/app/` (попадает в образ и hot-reload том без правок compose) или в корне с правкой Dockerfile/compose?
- ❓ Как оставить `create_all` для unit-тестов: в `tests/conftest.py` после `create_app` (нужен доступ к engine — через `app.state`?) или условием в `lifespan` для `sqlite`-URL / отдельным флагом в `Settings`?
- ❓ Нужна ли make-цель для генерации новых ревизий (`alembic revision --autogenerate`) и от чьего имени её запускать в контейнере (`appuser` должен иметь право записи в смонтированный `./src`)?

## Связанные задачи
- Зависит от: —
- Блокирует: —

## Критерии приёмки (Definition of Done)
- [ ] Поведение не изменилось — все существующие тесты зелёные без правок
- [ ] Публичное API / контракты не сломаны (или явно версионированы)
- [ ] Линтер и статический анализ зелёные
- [ ] Сложность и дублирование в изменённых модулях снизились
- [ ] Code review подтверждает улучшение читаемости
- [ ] Документация обновлена, если менялись имена/структура
