# Shortcuts for local development. Targets work from Git Bash on Windows.
# COMPONENTS grows as components land.

# Poetry lives in ~/.local/bin, which Git Bash doesn't always inherit on Windows.
export PATH := $(HOME)/.local/bin:$(PATH)

COMPONENTS := libs/common libs/db libs/embeddings libs/llm-gateway apps/data-pipeline apps/api

.PHONY: up down ps logs lint format test check

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f

lint:
	@set -e; for c in $(COMPONENTS); do \
		echo "== $$c"; \
		(cd $$c && poetry run ruff check . && poetry run ruff format --check .); \
	done

format:
	@set -e; for c in $(COMPONENTS); do \
		echo "== $$c"; \
		(cd $$c && poetry run ruff format .); \
	done

test:
	@set -e; for c in $(COMPONENTS); do \
		echo "== $$c"; \
		(cd $$c && poetry run pytest -q); \
	done

check: lint test
