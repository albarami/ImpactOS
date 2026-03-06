# ImpactOS — Staging Deployment Runbook

## Purpose

Step-by-step instructions to deploy ImpactOS to a staging environment using Docker Compose with a staging overlay. This runbook converts "code-ready" into "staging-live."

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
| C1 | All tests pass (5016 BE + 350 FE) | `pytest tests/ -q` |
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
# Build images and start services with staging overlay
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build

# Watch API container startup
docker compose logs -f api
```

The API container will:
1. Run `_check_startup_config()` at import time
2. Reject dev defaults for SECRET_KEY, DATABASE_URL, OBJECT_STORAGE_PATH
3. Exit with code 1 if any staging guardrail fails

---

## Step 3: Run Migrations

```bash
docker compose exec api alembic upgrade head
```

Verify:
```bash
docker compose exec api alembic current
# Expected: 020_chat_sessions_messages (head)

docker compose exec api alembic check
# Expected: No new upgrade operations detected
```

---

## Step 4: Run Preflight

```bash
# From inside the API container:
docker compose exec api python scripts/staging_preflight.py \
    --url http://localhost:8000

# Or with JSON output for CI:
docker compose exec api python scripts/staging_preflight.py \
    --json --url http://localhost:8000
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

## Step 6: Seed Data (Optional)

```bash
docker compose exec api python -m scripts.seed
```

---

## Step 7: Verify Endpoints

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
docker compose -f docker-compose.yml -f docker-compose.staging.yml stop api celery-worker

# 2. Deploy previous image tag
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d api celery-worker

# 3. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

### Rollback with Schema Change

```bash
# 1. Stop API + workers
docker compose -f docker-compose.yml -f docker-compose.staging.yml stop api celery-worker

# 2. Rollback migration
docker compose exec api alembic downgrade -1

# 3. Verify migration state
docker compose exec api alembic current

# 4. Deploy previous image tag
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d api celery-worker

# 5. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

### Full Teardown (keep data)

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml down
```

### Full Teardown (destroy data)

```bash
docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| API exits immediately | Startup config validation failed | Check `docker compose logs api` for `Startup config error:` messages |
| 401 on all requests | IdP not configured (JWKS_URL/JWT_ISSUER/JWT_AUDIENCE empty) | Set IdP variables in .env.staging |
| Health check degraded | Database or Redis not reachable | Check `docker compose ps` for unhealthy services |
| Preflight FAIL on environment | ENVIRONMENT still set to "dev" | Verify docker-compose.staging.yml overlay is loaded |
| Copilot SKIP | No LLM API keys configured | Set ANTHROPIC_API_KEY in .env.staging (optional) |
| Preflight FAIL on config_validation | Dev defaults still in .env.staging | Check SECRET_KEY, DATABASE_URL, OBJECT_STORAGE_PATH |
