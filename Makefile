# ImpactOS — Development Makefile
# Run `make help` to see available targets.

.DEFAULT_GOAL := help
.PHONY: help up down reset-db migrate seed test lint fmt serve

# ---------------------------------------------------------------------------
# Docker Compose
# ---------------------------------------------------------------------------

up: ## Start Docker stack (Postgres, Redis, MinIO)
	docker compose up -d
	@echo "Waiting for services..."
	@docker compose exec postgres pg_isready -U impactos -q && echo "Postgres ready" || echo "Postgres not ready yet"
	@echo "Stack running. Postgres :5432  Redis :6379  MinIO :9000 (console :9001)"

down: ## Stop Docker stack
	docker compose down

reset-db: ## Drop and recreate database (destroys all data)
	docker compose exec postgres dropdb -U impactos --if-exists impactos
	docker compose exec postgres createdb -U impactos impactos
	@echo "Database reset. Run 'make migrate' to recreate tables."

# ---------------------------------------------------------------------------
# Database Migrations
# ---------------------------------------------------------------------------

migrate: ## Run alembic upgrade head
	python -m alembic upgrade head

# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------

seed: ## Load sample 3x3 IO model + sample BoQ into database
	python -m scripts.seed

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

serve: ## Start FastAPI dev server on :8000
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test: ## Run pytest (uses aiosqlite — no Docker needed)
	python -m pytest tests/

lint: ## Run ruff check + mypy
	ruff check src/ tests/
	mypy src/ --ignore-missing-imports

fmt: ## Auto-format with ruff
	ruff check --fix src/ tests/
	ruff format src/ tests/

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'
