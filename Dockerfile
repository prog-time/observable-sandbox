FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/src
WORKDIR /srv
RUN useradd --create-home --uid 1000 appuser
COPY requirements.txt .
RUN pip install -r requirements.txt

# Тестовый образ: dev-зависимости, тесты, hot-reload (исходники монтируются томом)
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY src ./src
COPY tests ./tests
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/srv/src"]

# Прод-образ: только runtime-зависимости и код
FROM base AS prod
COPY src ./src
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
