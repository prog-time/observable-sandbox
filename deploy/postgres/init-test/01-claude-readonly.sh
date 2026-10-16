#!/bin/sh
# Только для тестовой среды: read-only роль, через которую Claude Code смотрит данные.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE claude_ro LOGIN PASSWORD '${CLAUDE_RO_PASSWORD}';
ALTER ROLE claude_ro SET default_transaction_read_only = on;
ALTER ROLE claude_ro SET statement_timeout = '10s';
GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO claude_ro;
GRANT USAGE ON SCHEMA public TO claude_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO claude_ro;
-- таблицы создаёт приложение позже — выдаём права на будущие таблицы
ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public GRANT SELECT ON TABLES TO claude_ro;
GRANT pg_read_all_stats TO claude_ro;
SQL
