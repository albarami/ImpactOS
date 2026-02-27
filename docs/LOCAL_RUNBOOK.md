# ImpactOS — Local Development Runbook

Step-by-step instructions to run ImpactOS on your local machine.

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose plugin)
- **Python 3.11+** with pip
- **Git**
- **Node.js 18+** (for frontend — Phase 2+, not needed yet)

## 1. Clone the Repository

```bash
git clone https://github.com/albarami/ImpactOS.git
cd ImpactOS
```

## 2. Python Environment

```bash
python -m venv .venv

# Linux/Mac:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate

# Install all dependencies (including dev tools)
pip install -e ".[dev]"
```

## 3. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` if needed. The defaults work for local Docker Compose. You only need to fill in LLM API keys if using AI features:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://impactos:impactos@localhost:5432/impactos` | Matches docker-compose |
| `REDIS_URL` | `redis://localhost:6379/0` | Matches docker-compose |
| `MINIO_ENDPOINT` | `localhost:9000` | Matches docker-compose |
| `ANTHROPIC_API_KEY` | (empty) | Required for AI compilation |
| `EXTRACTION_PROVIDER` | `local` | Use `azure_di` for production PDF extraction |

## 4. Start Infrastructure

```bash
make up
```

This starts three Docker containers:
- **PostgreSQL 16 + pgvector** on port 5432
- **Redis 7** on port 6379
- **MinIO** (S3-compatible storage) on port 9000 (console on 9001)

Verify they're running:

```bash
docker compose ps
```

## 5. Run Database Migrations

```bash
make migrate
```

This creates all 20 tables via Alembic.

## 6. Seed Sample Data

```bash
make seed
```

This loads:
- A sample workspace ("Strategic Gears Demo")
- A 3x3 simplified Saudi IO model (Agriculture, Industry, Services)
- A sample BoQ document with 12 realistic line items (NEOM Logistics Zone)

## 7. Start the API Server

```bash
make serve
```

The FastAPI server starts on http://localhost:8000.

**Interactive API docs:** http://localhost:8000/docs

## 8. Verify Everything Works

```bash
# Health check
curl http://localhost:8000/health

# API version
curl http://localhost:8000/api/version
```

## Running Tests

Tests use **aiosqlite in-memory** — no Docker required:

```bash
make test
```

## Other Commands

| Command | Description |
|---------|-------------|
| `make up` | Start Docker stack |
| `make down` | Stop Docker stack |
| `make reset-db` | Drop and recreate database |
| `make migrate` | Run Alembic migrations |
| `make seed` | Load sample data |
| `make serve` | Start FastAPI dev server |
| `make test` | Run pytest |
| `make lint` | Run ruff + mypy |
| `make fmt` | Auto-format code |

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | — |
| API Docs | http://localhost:8000/docs | — |
| MinIO Console | http://localhost:9001 | `impactos` / `impactos-secret` |
| PostgreSQL | localhost:5432 | `impactos` / `impactos` |
| Redis | localhost:6379 | — |

## Troubleshooting

**Port conflicts:** If ports 5432, 6379, or 9000 are in use, stop existing services or change ports in `docker-compose.yml`.

**Database connection errors:** Ensure Docker is running and `make up` completed. Check with `docker compose ps`.

**Test failures after schema changes:** Run `make reset-db && make migrate && make seed` to rebuild from scratch.
