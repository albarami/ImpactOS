# ImpactOS — Staging Deployment Runbook

## Purpose

Step-by-step instructions to deploy the ImpactOS **backend** (API + Celery worker) to a staging environment using Docker Compose with a staging overlay. This runbook converts "code-ready" into "staging-live."

### Scope

This runbook covers **backend deployment only**: API server, Celery worker, PostgreSQL, Redis, and MinIO. The frontend (Next.js) is excluded from the default staging profile — it requires separate configuration (NEXTAUTH_SECRET, NEXT_PUBLIC_API_URL) and is not yet staging-hardened.

---

## Prerequisites

### Infrastructure (must be provisioned before deployment)

| # | Prerequisite | How to Verify | Owner |
|---|-------------|---------------|-------|
| P1 | Docker Engine ≥ 24.x + Compose v2 | `docker compose version` | DevOps |
| P2 | External IdP (OAuth2/OIDC) | IdP admin console accessible | Security |
| P3 | Strong SECRET_KEY generated | `python -c "import secrets; print(secrets.token_urlsafe(64))"` | DevOps |
| P4 | Database credentials (non-placeholder) | `POSTGRES_USER` + `POSTGRES_PASSWORD` set | DBA |
| P5 | MinIO/S3 credentials (non-dev) | `MINIO_ACCESS_KEY` + `MINIO_SECRET_KEY` set | Infra |
| P6 | LLM API key (optional) | `ANTHROPIC_API_KEY` or equivalent set | DevOps |

### Code (already satisfied)

| # | Check | Verified By |
|---|-------|------------|
| C1 | All tests pass (5066 BE + 350 FE) | `pytest tests/ -q` |
| C2 | Alembic at head, no pending migrations | `alembic current && alembic check` |
| C3 | Preflight script passes in staging config | `python scripts/staging_preflight.py` |
| C4 | OpenAPI schema valid | `GET /openapi.json` |

---

## Step 1: Prepare Environment File

```bash
# Copy the staging template
cp .env.staging.example .env.staging

# Edit .env.staging with real values:
#   - POSTGRES_USER / POSTGRES_PASSWORD (non-placeholder)
#   - SECRET_KEY (strong random, not dev default)
#   - JWT_ISSUER, JWT_AUDIENCE, JWKS_URL (from your IdP)
#   - MINIO_ACCESS_KEY, MINIO_SECRET_KEY (non-dev)
#   - OBJECT_STORAGE_PATH (absolute path, e.g., /data/impactos-storage)
#   - LLM keys (optional — copilot will SKIP if absent)
$EDITOR .env.staging
```

### Validate Prerequisites

```bash
# Run the prerequisite checker
python scripts/staging_deploy.py check --env-file .env.staging
```

This verifies all required variables are set and not using dev defaults.

---

## Step 2: Build and Start Stack

```bash
# Build images and start backend services with staging overlay
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging up -d --build

# Watch API container startup
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging logs -f api
```

The API container will:
1. Run `_check_startup_config()` at import time
2. Reject dev defaults for SECRET_KEY, DATABASE_URL, OBJECT_STORAGE_PATH
3. Exit with code 1 if any staging guardrail fails

Or use the Makefile shortcut:
```bash
make staging-up
```

---

## Step 3: Run Migrations

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api alembic upgrade head
```

Verify:
```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api alembic current
# Expected: shows (head)

docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api alembic check
# Expected: No new upgrade operations detected
```

---

## Step 4: Run Preflight

```bash
# From inside the API container:
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api \
    python scripts/staging_preflight.py --url http://localhost:8000

# Or with JSON output for CI:
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api \
    python scripts/staging_preflight.py --json --url http://localhost:8000
```

Or use the Makefile shortcut (runs from host):
```bash
make staging-preflight
```

Expected: All 6 checks PASS (environment, config_validation, alembic, readiness, health_components, no_secrets).

---

## Step 5: Run Smoke Tests

```bash
# From host (pointing at the exposed port):
python scripts/staging_smoke.py --url http://localhost:8000

# Or with JSON output:
python scripts/staging_smoke.py --json --url http://localhost:8000
```

Or use the Makefile shortcut:
```bash
make staging-smoke
```

Expected stages:
| Stage | Expected |
|-------|----------|
| startup | PASS |
| readiness | PASS |
| auth_enforcement | PASS |
| health_components | PASS |
| api_schema | PASS |
| copilot_smoke | PASS or SKIP (depends on LLM keys) |

---

## Step 6: Verify Worker Health

```bash
# Check celery-worker container status
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging ps celery-worker

# Check worker logs for startup success
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging logs --tail 20 celery-worker
# Expected: "celery@... ready" with no error tracebacks
```

---

## Step 7: Seed Data (Optional)

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api python -m scripts.seed
```

---

## Step 8: Verify Endpoints

```bash
# Health check
curl -s http://localhost:8000/health | python -m json.tool

# Readiness
curl -s http://localhost:8000/readiness | python -m json.tool

# API version
curl -s http://localhost:8000/api/version | python -m json.tool

# Auth enforcement (should return 401)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/v1/workspaces

# OpenAPI schema
curl -s http://localhost:8000/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d[\"paths\"])} paths')"

# Copilot status
curl -s http://localhost:8000/api/copilot/status | python -m json.tool
```

---

## Rollback Procedure

### Quick Rollback (no schema change)

```bash
# 1. Stop API + workers
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging stop api celery-worker

# 2. Restart with current image
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging up -d api celery-worker

# 3. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

### Rollback with Schema Change

```bash
# 1. Stop API + workers
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging stop api celery-worker

# 2. Rollback migration
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api alembic downgrade -1

# 3. Verify migration state
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging exec api alembic current

# 4. Restart services
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging up -d api celery-worker

# 5. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

### Full Teardown (keep data)

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging down
```

### Full Teardown (destroy data)

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
    --env-file .env.staging down -v
```

---

## Not Covered by This Runbook

| Item | Status | Notes |
|------|--------|-------|
| Frontend (Next.js) | Excluded | Requires NEXTAUTH_SECRET, staging NEXT_PUBLIC_API_URL; not staging-hardened |
| Container registry / image tagging | Not implemented | Rollback uses source rebuild, not tagged images |
| External staging database | Infrastructure | This runbook uses Docker Compose Postgres; external DB requires DATABASE_URL override |
| TLS/HTTPS | Not configured | Add a reverse proxy (nginx/caddy) in front of the API for HTTPS |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| API exits immediately | Startup config validation failed | Check `docker compose logs api` for `Startup config error:` messages |
| 401 on all requests | IdP not configured (JWKS_URL/JWT_ISSUER/JWT_AUDIENCE empty) | Set IdP variables in .env.staging |
| Health check degraded | Database or Redis not reachable | Check `docker compose ps` for unhealthy services |
| Preflight FAIL on environment | ENVIRONMENT still set to "dev" | Verify docker-compose.staging.yml overlay is loaded and `--env-file .env.staging` is passed |
| Copilot SKIP | No LLM API keys configured | Set ANTHROPIC_API_KEY in .env.staging (optional) |
| Preflight FAIL on config_validation | Dev defaults still in .env.staging | Check SECRET_KEY, DATABASE_URL, OBJECT_STORAGE_PATH |
| Variable interpolation warnings | Missing `--env-file .env.staging` | Add `--env-file .env.staging` to all `docker compose -f ... -f ...` commands |
