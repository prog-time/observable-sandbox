# TASK-20261016-narrow-compose-permissions: Сузить права Claude Code на docker compose в тестовой среде

**Type:** feature  
**Size:** S  
**Status:** todo
**GitHub Issue:** #2 — https://github.com/prog-time/observable-sandbox/issues/2

## Что делаем
Сейчас в `.claude/settings.json` правило `Bash(docker compose -p logger-test:*)` разрешает без подтверждения любую compose-команду для тестового стенда. Через него Claude может выполнить `exec db psql -U app` и получить полную запись в БД в обход read-only роли `claude_ro`, а может и `down -v`, что удалит все тестовые тома. Заменяем широкое правило на явный список безопасных команд. Остальные команды будут требовать подтверждения, а разрушительные попадут в `deny`.

## Пользователь получает
Как **разработчик, работающий с Claude Code в test.logger**, я могу **оставить Claude на тестовом стенде без постоянного присмотра**, чтобы **он только читал данные (логи, метрики, БД через `claude_ro`) и не мог случайно изменить или удалить данные тестовой БД**.

## Готово когда
- [ ] Given обновлённый `.claude/settings.json`, when Claude выполняет `docker compose -p logger-test ps`, `logs` или `exec app pytest` (и полную форму из Makefile с `--env-file .env.test -f ...`), then команда идёт без запроса подтверждения
- [ ] Given обновлённый `.claude/settings.json`, when Claude пытается выполнить `docker compose -p logger-test ... down -v` (или `--volumes`), then команда запрещена правилом `deny`
- [ ] Given обновлённый `.claude/settings.json`, when Claude пытается выполнить `docker compose -p logger-test ... exec db psql -U app` (или любой `exec db ...`), then команда запрещена или требует подтверждения пользователя
- [ ] Given обновлённый `.claude/settings.json`, when Claude выполняет другую compose-команду, которой нет в allow-списке (`restart`, `stop`, `rm`, `run`, `exec app sh` и т.п.), then Claude Code запрашивает подтверждение
- [ ] Given обновлённый `.claude/settings.json`, when пользователь запускает `make test-up`, `make test-down`, `make test-ps`, `make pytest`, `make loadgen`, then они работают как раньше без подтверждения, а `make test-reset` (`down -v`) требует подтверждения или запрещён
- [ ] Given обновлённые правила, when читаешь `CLAUDE.md` и `README.md`, then там описано, какие compose-команды Claude может запускать сам

## Как делаем
- Удалить из `permissions.allow` широкое правило `Bash(docker compose -p logger-test:*)`.
- Добавить узкие allow-правила для read-only и тестовых операций: `ps`, `logs`, `config`, `top`, `images`, `exec app pytest`. Учесть, что в Makefile команда записана в полной форме `docker compose -p logger-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml <cmd>`, и префиксные правила должны покрывать обе формы (короткую из `CLAUDE.md` и полную).
- Добавить в `permissions.deny` правила для `down -v` / `down --volumes`, `exec db` (psql под `app`/`postgres`), `make test-reset`, `volume rm` для томов `logger-test_*`. Порядок `deny` → `ask` → `allow` проверить на практике.
- Всё, что не попало ни в allow, ни в deny, по умолчанию запрашивает подтверждение. При необходимости явно добавить в `ask` `down`, `restart`, `stop`, `up` без make.
- Обновить раздел про доступ Claude в `CLAUDE.md` (и пункт 4 в `README.md`): перечислить разрешённые команды и то, что запись в БД идёт только через API приложения.

## Файлы
- `.claude/settings.json` — замена широкого правила на узкие allow/deny (основное изменение)
- `CLAUDE.md` — раздел «Как смотреть систему»: какие compose-команды разрешены
- `README.md` — раздел «Как Claude Code получает доступ к тесту», п. 4
- `Makefile` — только ссылка: цели `test-*`, `pytest`, `loadgen` задают реальную форму команд (не меняем, если не понадобится)
- ❓ автотесты для правил permissions — в проекте подходящего механизма нет (`tests/test_api.py` проверяет только API)

## Не делаем в этой задаче
- Изменение прав роли `claude_ro` и init-скрипта `deploy/postgres/init-test/01-claude-readonly.sh`
- Изменение доступа Adminer (вход под `app` для человека остаётся)
- Правила для прод-стенда: `deny` для `logger-prod` уже есть и не трогаем его
- Перевод `mcp-grafana` или Grafana на другие учётные данные

## Вопросы
- ❓ `exec db ...` целиком в `deny` или в `ask`? Например, `exec db psql -U claude_ro` безопасен, но запретить весь `exec db` проще и надёжнее.
- ❓ `make test-reset` (`down -v`) в `deny` или в `ask`? Человеку иногда нужно сбросить стенд, но запускает его сам человек, а не Claude.
- ❓ `exec app python -m app.loadgen` (через `make loadgen`) оставляем. А произвольный `exec app python ...`/`exec app sh`? У контейнера `app` в `DATABASE_URL` пароль владельца БД, так что это тоже обход `claude_ro`. Предлагается `ask`.
- ❓ Насколько надёжно префиксное сопоставление Claude Code справляется с флагами между `-p logger-test` и подкомандой (`--env-file`, `-f`)? Это надо проверить вручную, а возможно, стоит договориться о единой форме команды.
- ❓ `up -d --build` напрямую через compose (не через `make test-up`) — разрешать или `ask`?

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
