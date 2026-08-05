# Build from the repo root so libs/ is inside the context:
#   docker build -f apps/api/Dockerfile .

FROM python:3.13.12-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install poetry==2.4.1

WORKDIR /app
COPY libs/common /app/libs/common
COPY libs/db /app/libs/db
COPY apps/api /app/apps/api

WORKDIR /app/apps/api
RUN poetry install --only main

FROM python:3.13.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/apps/api/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
WORKDIR /app/apps/api
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
