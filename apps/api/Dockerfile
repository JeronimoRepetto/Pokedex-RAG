# Build from the repo root so libs/ is inside the context:
#   docker build -f apps/api/Dockerfile .

FROM python:3.13.12-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install poetry==2.4.1

WORKDIR /app
# Every path dependency declared in apps/api/pyproject.toml must be copied here or
# `poetry install` fails resolving it — keep this list in sync with that file.
COPY libs/common /app/libs/common
COPY libs/db /app/libs/db
COPY libs/embeddings /app/libs/embeddings
COPY libs/llm-gateway /app/libs/llm-gateway
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

# Shell form on purpose: Cloud Run injects the port to listen on as $PORT and the
# container must honor it. `exec` keeps uvicorn as PID 1 so SIGTERM still shuts it down
# gracefully during a revision rollover.
CMD exec uvicorn api.main:app --factory --host 0.0.0.0 --port ${PORT:-8000}
