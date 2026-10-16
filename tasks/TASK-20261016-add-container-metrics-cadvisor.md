# TASK-20261016-add-container-metrics-cadvisor: Добавить метрики ресурсов контейнеров через cAdvisor

**Type:** feature  
**Size:** M  
**Status:** todo
**GitHub Issue:** #4 — https://github.com/prog-time/observable-sandbox/issues/4

## Что делаем
Сейчас в Prometheus нет метрик `container_*`: видны только `process_*` Python-приложения (job `app`) и `pg_*` от `postgres-exporter`. Потребление CPU, памяти, сети и диска контейнерами `db`, `loki`, `alloy`, `prometheus`, `grafana` и остальными Claude Code через MCP `grafana-test` не видит, только вручную через `docker stats`. Добавляем сервис cAdvisor, scrape-job в Prometheus и панели ресурсов контейнеров в дашборд Grafana.

## Пользователь получает
Как **разработчик, который работает с Claude Code в тестовой среде**, я могу **запросить через `query_prometheus` CPU, память, сеть и диск любого контейнера стенда `logger-test`**, чтобы **диагностировать нехватку ресурсов и утечки без ручного `docker stats`**.

## Готово когда
- [ ] Given тестовый стенд поднят через `make test-up`, when выполнить `docker compose -p logger-test ps`, then сервис `cadvisor` в статусе running/healthy, а образ закреплён конкретной версией (не `latest`), выпущенной не позже 2026-10-02 (ей не меньше двух недель)
- [ ] Given cAdvisor запущен, when открыть Prometheus `/targets` (или `query_prometheus` с `up{job="cadvisor"}`), then target job `cadvisor` в состоянии `up` (значение `1`)
- [ ] Given стенд работает не меньше минуты, when выполнить `sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[1m]))` через MCP `grafana-test`, then в результате есть ряды для контейнеров `app`, `db`, `loki`, `alloy`, `prometheus`, `grafana` проекта `logger-test`
- [ ] Given стенд работает, when запросить `container_memory_working_set_bytes`, `container_network_receive_bytes_total` / `container_network_transmit_bytes_total` и `container_fs_*` (или `container_blkio_*`) для контейнера `db`, then каждая метрика возвращает ненулевые данные; метрики, которые недоступны в Docker Desktop на macOS, перечислены в README/CLAUDE.md
- [ ] Given одновременно запущены `logger-test` и `logger-prod`, when в тестовом Prometheus запросить `count by (container_label_com_docker_compose_project) (container_memory_working_set_bytes)`, then в выдаче только `logger-test`: метрики прод-контейнеров в тестовый Prometheus не попадают
- [ ] Given открыт дашборд `test.logger — приложение` (uid `test-logger-app`), when посмотреть новые панели, then видны CPU и память по контейнерам (по возможности ещё сеть) с разбивкой по сервису compose
- [ ] Given обновлены `CLAUDE.md` и `README.md`, when Claude Code читает раздел «Как смотреть систему», then там перечислены метрики `container_*`, метка для фильтра по сервису и пример PromQL

## Как делаем
- Добавить сервис `cadvisor` в `docker-compose.yml` (базовая сборка, если решим, что он нужен и в проде, иначе в `docker-compose.test.yml`): образ `gcr.io/cadvisor/cadvisor:<vX.Y.Z>` с закреплённой версией, `logging: *logging`, монтирования `/:/rootfs:ro`, `/var/run:/var/run:ro`, `/sys:/sys:ro`, `/var/lib/docker/:/var/lib/docker:ro` (под Linux; для Docker Desktop на macOS проверить, см. Вопросы), при необходимости `privileged: true` и `devices: [/dev/kmsg]`. Флаги: `--docker_only=true`, `--housekeeping_interval=10s` (под `scrape_interval: 10s`), `--store_container_labels=false` + `--whitelisted_container_labels=com.docker.compose.project,com.docker.compose.service`, а также `--disable_metrics=...`, чтобы срезать лишние/дорогие метрики (percpu, tcp/udp, process и т.п.).
- В `docker-compose.test.yml` по аналогии с Prometheus/Loki пробросить UI на `127.0.0.1:8082:8080` (опционально, для человека; Claude смотрит через Prometheus). В прод-оверлей, если cAdvisor там будет, только `restart: unless-stopped`, без портов.
- В `deploy/prometheus/prometheus.yml` добавить job `cadvisor` (`targets: ["cadvisor:8080"]`) с `metric_relabel_configs`: оставить только ряды с `container_label_com_docker_compose_project` равным проекту текущего стенда (cAdvisor видит все контейнеры хоста, а `logger-test` и `logger-prod` могут работать на одном Docker одновременно) и переложить `container_label_com_docker_compose_service` в короткую метку `service`, как в Loki. Prometheus запускается без `-config.expand-env`, поэтому имя проекта придётся либо зашить в конфиг, либо сделать конфиг для каждой среды (см. Вопросы).
- В `deploy/grafana/dashboards/app.json` добавить строку «Контейнеры» с панелями: CPU `sum by (service) (rate(container_cpu_usage_seconds_total{service!=""}[1m]))`, память `sum by (service) (container_memory_working_set_bytes{service!=""})`, сеть RX/TX `rate(container_network_*_bytes_total[1m])`. Логи приложения (id 7, y=24) сдвинуть вниз.
- Проверка на стенде: `make test-up`, `make loadgen`, затем `list_prometheus_metric_names` и `query_prometheus` через MCP `grafana-test`. Обновить таблицы сервисов в `README.md` и раздел метрик в `CLAUDE.md`.

## Файлы
- `docker-compose.yml` — новый сервис `cadvisor` (если он нужен в обеих средах)
- `docker-compose.test.yml` — проброс порта UI cAdvisor на 127.0.0.1 (или сам сервис, если только в тесте)
- `docker-compose.prod.yml` — `restart: unless-stopped` для `cadvisor`, если он нужен в проде
- `deploy/prometheus/prometheus.yml` — job `cadvisor` + `metric_relabel_configs` (фильтр по compose-проекту, метка `service`)
- `deploy/grafana/dashboards/app.json` — панели «CPU / память / сеть по контейнерам»
- `README.md` — строка `cadvisor` в таблице «Состав»
- `CLAUDE.md` — метрики `container_*`, метка `service`, примеры PromQL в «Как смотреть систему»
- ❓ возможно, отдельный `deploy/prometheus/prometheus.prod.yml` или шаблон конфига для каждой среды (зависит от решения по фильтру проекта)

## Не делаем в этой задаче
- Алерты на ресурсы контейнеров (Alertmanager / Grafana alerting)
- node-exporter и метрики хоста/VM Docker Desktop
- Лимиты ресурсов (`deploy.resources.limits`) для сервисов, кроме уже существующего у `app` в проде
- Новые инструменты mcp-grafana или изменение `--enabled-tools`
- Отдельный дашборд под инфраструктуру; если панелей станет слишком много, это отдельная задача

## Вопросы
- ❓ Docker Desktop на macOS: контейнеры живут внутри Linux VM, путей `/var/lib/docker` и `/sys/fs/cgroup` хоста macOS для cAdvisor не существует. Какой набор монтирований реально работает (`/var/run/docker.sock` + `/sys` + `/var/lib/docker` внутри VM, `privileged: true`)? Будут ли `container_fs_*`/`container_blkio_*` и сетевые метрики отдаваться в Docker Desktop (cgroup v2, VirtioFS), или их нужно пометить как «только на Linux»?
- ❓ Нужен ли cAdvisor в проде? Скорее всего да: это мониторинг, Claude к прод-Prometheus доступа не получает. Если да, сервис идёт в базовый `docker-compose.yml`, а порт UI в прод не пробрасывается.
- ❓ Изоляция test/prod: cAdvisor видит все контейнеры Docker-хоста, и при одновременной работе обеих сред тестовый Prometheus (то есть и Claude) увидит ресурсы прод-контейнеров. Фильтровать через `metric_relabel_configs` по `container_label_com_docker_compose_project`? Prometheus не подставляет env в конфиг, поэтому: два файла `prometheus.yml` под каждую среду, общий regex `logger-(test|prod)` плюс отдельный keep в тесте, или запускать cAdvisor с фильтром на своей стороне? Также два cAdvisor на одном хосте (test + prod) дублируют сбор, так что прод-экземпляр тоже нужно фильтровать.
- ❓ Какую версию образа брать: последний стабильный релиз `gcr.io/cadvisor/cadvisor` старше 2026-10-02. Проверить тег на GitHub releases google/cadvisor и наличие multi-arch (arm64 для Apple Silicon) у образа этой версии.
- ❓ Healthcheck для cAdvisor (`wget -qO- http://localhost:8080/healthz`): нужен ли, чтобы `make test-up` с `--wait` его дожидался?
- ❓ Панели ресурсов контейнеров кладём в существующий `app.json` или в отдельный дашборд «Инфраструктура»? По постановке пока `app.json`.

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
