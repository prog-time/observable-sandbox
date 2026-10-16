TEST = docker compose -p logger-test --env-file .env.test -f docker-compose.yml -f docker-compose.test.yml
PROD = docker compose -p logger-prod --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: help test-up test-down test-reset test-logs test-ps pytest loadgen migrate migration prod-up prod-down prod-ps prod-logs

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

# ---------- тестовая среда ----------
test-up: ## поднять тестовый стенд (+ идемпотентно создать pg_stat_statements)
	$(TEST) run --rm db-init
	$(TEST) up -d --build --wait --scale db-init=0
test-down: ## остановить тестовый стенд (данные сохраняются)
	$(TEST) down
test-reset: ## остановить и удалить данные тестового стенда
	$(TEST) down -v
test-ps: ## статус контейнеров
	$(TEST) ps
test-logs: ## docker-логи приложения
	$(TEST) logs -f --tail=100 app
pytest: ## прогнать тесты внутри тестового контейнера
	$(TEST) exec app pytest -q
loadgen: ## сгенерировать трафик 60 секунд (DURATION=...)
	$(TEST) exec app python -m app.loadgen --seconds $(or $(DURATION),60)

migrate: ## применить миграции Alembic в тестовом контейнере (идемпотентно)
	$(TEST) exec app python -m app.migrate upgrade
migration: ## новая ревизия по изменениям моделей: make migration MSG="add x"
	@test -n "$(MSG)" || (echo 'Укажите MSG="описание"' && exit 1)
	$(TEST) exec app python -m app.migrate revision "$(MSG)"

# ---------- прод ----------
prod-up: ## поднять прод (нужен .env.prod)
	@test -f .env.prod || (echo "Создайте .env.prod из .env.prod.example" && exit 1)
	$(PROD) up -d --build --wait
prod-down:
	$(PROD) down
prod-ps:
	$(PROD) ps
prod-logs:
	$(PROD) logs -f --tail=100 app
