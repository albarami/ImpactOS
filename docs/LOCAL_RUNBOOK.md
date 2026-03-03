# ImpactOS — Local Development Runbook

Step-by-step instructions to run ImpactOS on your local machine.

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose plugin)
- **Python 3.11+** with pip (for running tests on host)
- **Git**
- **Node.js 18+** (for frontend — Phase 2+, not needed yet)

## 1. Clone the Repository

```bash
git clone https://github.com/albarami/ImpactOS.git
cd ImpactOS
```

## 2. Python Environment (for local testing)

```bash
python -m venv .venv

# Linux/Mac:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate

# Install all dependencies (including dev tools)
pip install -e ".[dev]"
```

> **Note:** The Python environment is only needed for running tests on the host. The API server and worker run inside Docker containers.

## 3. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` if needed. The defaults work for local Docker Compose. You only need to fill in LLM API keys if using AI features:

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://impactos:impactos@localhost:5432/impactos` | Auto-overridden inside Docker |
| `REDIS_URL` | `redis://localhost:6379/0` | Auto-overridden inside Docker |
| `MINIO_ENDPOINT` | `localhost:9000` | Auto-overridden inside Docker |
| `ANTHROPIC_API_KEY` | (empty) | Required for AI compilation |
| `OBJECT_STORAGE_PATH` | `./uploads` | Local path for dev, S3 URI for prod |
| `EXTRACTION_PROVIDER` | `local` | Use `azure_di` for production PDF extraction |

## 4. Start the Full Stack

```bash
make up
```

This builds and starts **five Docker services** and runs database migrations automatically:
- **PostgreSQL 16 + pgvector** on port 5432
- **Redis 7** on port 6379
- **MinIO** (S3-compatible storage) on port 9000 (console on 9001)
- **MinIO Init** (one-shot: creates the `impactos-data` bucket, then exits)
- **API** (FastAPI on port 8000)
- **Celery Worker** (background job processing)

Migrations are run automatically inside the API container — no separate step needed.

Verify they're running:

```bash
docker compose ps
```

## 5. Seed Sample Data (optional)

```bash
make seed
```

This loads (idempotent — safe to run multiple times):
- A sample workspace ("Strategic Gears Demo")
- A **5-sector Saudi IO model** (AGRI, MINING, MANUF, CONSTR, SERVICES)
- Satellite coefficients (jobs, imports, value-added per sector)
- Employment coefficients (direct jobs, indirect multiplier)
- A sample BoQ document with 12 realistic line items (NEOM Logistics Zone)

## 6. Verify Everything Works

```bash
# Health check (covers API + database + Redis + object storage)
curl http://localhost:8000/health

# API version
curl http://localhost:8000/api/version
```

The `/health` endpoint checks four components: API, database (PostgreSQL), Redis, and object storage (the `OBJECT_STORAGE_PATH` directory). It returns `"status": "ok"` when all are reachable, or `"status": "degraded"` with per-component details otherwise.

**Interactive API docs:** http://localhost:8000/docs

## Running Tests

Tests use **aiosqlite in-memory** — they do NOT need Docker running:

```bash
make test          # Full suite
make test-fast     # Stop on first failure (-x -q)
```

## All Commands

| Command | Description |
|---------|-------------|
| `make up` | Build + start full stack + run migrations |
| `make down` | Stop Docker stack (keep data volumes) |
| `make nuke` | Stop stack AND destroy all data volumes |
| `make restart-api` | Restart API container only (fast reload) |
| `make migrate` | Run Alembic migrations (in API container) |
| `make reset-db` | Drop and recreate database |
| `make seed` | Load 5-sector Saudi IO model + sample BoQ |
| `make serve` | Start FastAPI dev server on host (for faster reload) |
| `make test` | Run pytest (aiosqlite, no Docker needed) |
| `make test-fast` | Run pytest, stop on first failure |
| `make lint` | Run ruff check + mypy |
| `make fmt` | Auto-format code with ruff |
| `make build-model` | Rebuild synthetic 20-sector model from assumptions |
| `make validate-model` | Validate `data/synthetic/saudi_io_synthetic_v1.json` |
| `make logs` | Tail all container logs |
| `make logs-api` | Tail API container logs |

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| FastAPI | http://localhost:8000 | — |
| API Docs | http://localhost:8000/docs | — |
| MinIO Console | http://localhost:9001 | `impactos` / `impactos-secret` |
| PostgreSQL | localhost:5432 | `impactos` / `impactos` |
| Redis | localhost:6379 | — |

## Common Workflows

**Fresh start from scratch:**
```bash
make nuke && make up && make seed
```

**After changing source code:**
```bash
make restart-api    # Rebuilds if Dockerfile changed
```

**After changing DB schema:**
```bash
make migrate        # Run new Alembic migrations in container
```

**Host-based development (faster reload):**
```bash
make up             # Start infrastructure
make serve          # Run API on host (uses localhost:5432 etc.)
```

## End-to-End Workflow

The primary API workflow is:

1. **Upload** a document (BoQ, CAPEX plan) to a workspace.
2. **Extract** structured data — routed by `ExtractionRouter` to `LocalPdfProvider` or `AzureDIProvider` (via Celery). Spreadsheets are always handled locally.
3. **Compile from document** — `POST /v1/workspaces/{id}/scenarios/{id}/compile` with `document_id`. The older payload-based `line_items` field is deprecated; use `document_id` to load stored extraction results.
4. **Run** the deterministic I-O engine to compute impacts.
5. **Export** — governed exports are gated on both NFF claim status (all claims resolved) and quality provenance (synthetic fallback data blocks governed export).

### Extraction Providers

PDF extraction is handled by a provider-based architecture in `src/ingestion/providers/`:

| Provider | When Used |
|----------|-----------|
| `LocalPdfProvider` | Default for all PDFs; always used for RESTRICTED classification |
| `AzureDIProvider` | Used for PUBLIC/CONFIDENTIAL/INTERNAL when Azure DI is configured |
| `LocalSpreadsheetProvider` | Always used for CSV/Excel files |

Set `EXTRACTION_PROVIDER=azure_di` and provide Azure DI credentials to enable cloud extraction. Async extraction jobs run via Celery.

### Validate Synthetic Model

```bash
make validate-model   # Validates data/synthetic/saudi_io_synthetic_v1.json
make build-model      # Rebuild synthetic model from assumptions
```

## MVP-14 Saudi Data Foundation Loading

Register a model with extended Phase 2-E prerequisite fields (additive):

```bash
curl -X POST http://localhost:8000/v1/engine/models \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{
    "Z": [[10,1],[2,12]],
    "x": [100,200],
    "sector_codes": ["S1","S2"],
    "base_year": 2023,
    "source": "saudi-curated-test",
    "final_demand_F": [[100,50,30,20],[60,40,20,10]],
    "imports_vector": [10,15],
    "compensation_of_employees": [20,30],
    "gross_operating_surplus": [15,25],
    "taxes_less_subsidies": [3,4],
    "household_consumption_shares": [0.4,0.6],
    "deflator_series": {"2023": 1.0, "2024": 1.02}
  }'
```

If artifact shapes are invalid, registration fails with HTTP `422` and a stable
`reason_code` (for example `MODEL_IMPORTS_VECTOR_DIMENSION_MISMATCH`).

## Troubleshooting

**Port conflicts:** If ports 5432, 6379, 8000, or 9000 are in use, stop existing services or change ports in `docker-compose.yml`.

**Database connection errors:** Ensure Docker is running and `make up` completed. Check with `docker compose ps` and `make logs-api`.

**Test failures after schema changes:** Run `make reset-db && make migrate && make seed` to rebuild from scratch.

**API won't start in Docker:** Check `make logs-api` for errors. Ensure `.env` file exists (`cp .env.example .env`).
