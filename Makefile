# Shortcuts for local development. Targets work from Git Bash on Windows.
# COMPONENTS grows as components land.

# Poetry lives in ~/.local/bin, which Git Bash doesn't always inherit on Windows.
export PATH := $(HOME)/.local/bin:$(PATH)

COMPONENTS := libs/common libs/db libs/embeddings libs/llm-gateway apps/data-pipeline apps/api apps/evals

# apps/web is a Node component: pnpm, not Poetry, so it has its own targets.
WEB := apps/web

.PHONY: up down ps logs lint format test check web-dev web-lint web-test web-build \
        demo demo-stop status

up:
	docker compose up -d

down:
	docker compose down

# --- one-command demo -------------------------------------------------------------
#
# `make demo` brings the whole stack up and waits until it actually answers, so a cold
# machine (after a reboot, or after `make demo-stop`) is one command away from a
# working Pokédex. `make demo-stop` puts it back to zero running cost.
#
# The database lives in the `pgdata` Docker volume, which SURVIVES both of these —
# ingested data and embeddings are never lost by stopping the stack. Only `docker
# compose down -v` would delete them, which is why no target here passes -v.

demo:
	docker compose up -d --build db api
	@echo "waiting for the API to answer..."
	@for i in $$(seq 1 60); do \
		if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then \
			echo "API ready on http://127.0.0.1:8000"; break; \
		fi; sleep 2; \
	done
	@curl -fsS http://127.0.0.1:8000/health || (echo "API did not come up; try 'make logs'" && exit 1)
	@echo ""
	@echo "Now start the UI:  make web-dev   (http://localhost:3000)"

demo-stop:
	docker compose stop
	@echo "Stopped. Data is kept in the pgdata volume; 'make demo' brings it all back."

# What is actually running, and does the corpus have data in it?
status:
	@docker compose ps
	@docker compose exec -T db psql -U $${POSTGRES_USER:-pokedex} -d $${POSTGRES_DB:-pokedex} \
		-c "SELECT (SELECT count(*) FROM pokemon) AS pokemon, \
		           (SELECT count(*) FROM documents) AS documents, \
		           (SELECT count(*) FROM embeddings) AS embeddings, \
		           (SELECT count(*) FROM type_effectiveness) AS type_effectiveness;" \
		|| echo "database not reachable (is it up? 'make demo')"

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

web-dev:
	cd $(WEB) && pnpm dev

web-lint:
	cd $(WEB) && pnpm lint && pnpm format:check && pnpm typecheck

web-test:
	cd $(WEB) && pnpm test

web-build:
	cd $(WEB) && pnpm build

# Everything: Python components plus the web app.
check: lint test web-lint web-test
