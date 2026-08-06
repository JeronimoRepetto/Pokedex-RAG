# Build from the repo root so libs/ is inside the context:
#   docker build -f apps/evals/Dockerfile .

FROM python:3.13.12-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install poetry==2.4.1

WORKDIR /app
COPY libs/common /app/libs/common
COPY apps/evals /app/apps/evals

WORKDIR /app/apps/evals
RUN poetry install --only main

FROM python:3.13.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

# Same absolute layout as the builder so the venv's path-dependency links stay valid.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/apps/evals/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
WORKDIR /app/apps/evals

ENTRYPOINT ["evals"]
CMD ["--help"]
