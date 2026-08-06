# Build from the repo root so libs/ is inside the context:
#   docker build -f apps/data-pipeline/Dockerfile .

FROM python:3.13.12-slim AS builder

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install poetry==2.4.1

WORKDIR /app
# Keep in sync with the path dependencies in apps/data-pipeline/pyproject.toml.
COPY libs/common /app/libs/common
COPY libs/db /app/libs/db
COPY libs/embeddings /app/libs/embeddings
COPY apps/data-pipeline /app/apps/data-pipeline

WORKDIR /app/apps/data-pipeline
RUN poetry install --only main

FROM python:3.13.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --create-home app

# Same absolute layout as the builder so the venv's path-dependency links stay valid.
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/apps/data-pipeline/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
WORKDIR /app/apps/data-pipeline

ENTRYPOINT ["pipeline"]
CMD ["--help"]
