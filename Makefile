# ImpactOS — Development Makefile
# Run `make help` to see available targets.

.DEFAULT_GOAL := help
.PHONY: help up down nuke reset-db migrate seed seed-saudi20 serve test test-fast lint fmt restart-api logs logs-api build-model validate-model

# ---------------------------------------------------------------------------
# Docker Compose — Full Stack
# ---------------------------------------------------------------------------

up: ## Start full stack + run migrations (one command)
	docker compose up -d --build
	@echo "Waiting for API to be healthy..."
	@timeout=60; while [ $$timeout -gt 0 ]; do \
		docker compose exec api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null && break; \
		sleep 2; timeout=$$((timeout - 2)); \
	done
	@docker compose exec api alembic upgrade head
	@echo ""
	@echo "Stack ready:"
	@echo "  API:          http://localhost:8000/docs"
	@echo "  MinIO:        http://localhost:9001  (impactos / impactos-secret)"
	@echo "  Postgres:     localhost:5432"
	@echo "  Redis:        localhost:6379"

down: ## Stop Docker stack (keep volumes)
	docker compose down

nuke: ## Stop stack AND destroy all data volumes
	docker compose down -v
	@echo "All volumes destroyed. Run 'make up' to rebuild from scratch."

restart-api: ## Restart API container only (fast reload)
	docker compose restart api

# ---------------------------------------------------------------------------
# Database Migrations
# ---------------------------------------------------------------------------

migrate: ## Run alembic upgrade head (in API container)
	docker compose exec api alembic upgrade head

reset-db: ## Drop and recreate database (destroys all data)
	docker compose exec postgres dropdb -U impactos --if-exists impactos
	docker compose exec postgres createdb -U impactos impactos
	@echo "Database reset. Run 'make migrate' to recreate tables."

# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

seed: ## Load 5-sector Saudi IO model + sample BoQ into database
	docker compose exec api python -m scripts.seed

seed-saudi20: ## Load 20-sector Saudi IO model into database
	docker compose exec api python -m scripts.seed --profile saudi20

build-model: ## Rebuild synthetic 20-sector model from assumptions
	python -m scripts.build_synthetic_model

validate-model: ## Validate synthetic model (data/curated/saudi_io_synthetic_v1.json)
	python -m scripts.validate_model data/curated/saudi_io_synthetic_v1.json

# ---------------------------------------------------------------------------
# Development (host-based — for faster reload during coding)
# ---------------------------------------------------------------------------

serve: ## Start FastAPI dev server on :8000 (host, not Docker)
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run pytest (uses aiosqlite — no Docker needed)
	python -m pytest tests/

test-fast: ## Run pytest, stop on first failure
	python -m pytest tests/ -x -q

lint: ## Run ruff check + mypy
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

fmt: ## Auto-format with ruff
	ruff check --fix src/ tests/
	ruff format src/ tests/

# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

logs: ## Tail all container logs
	docker compose logs -f

logs-api: ## Tail API container logs
	docker compose logs -f api

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
