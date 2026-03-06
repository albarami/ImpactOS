# Sprint 30: Infrastructure Blocker Report

**Date:** 2026-03-06
**Context:** Staging deployment execution blocked by infrastructure prerequisites
**Status:** Code-ready, infrastructure not provisioned

---

## Blocker Matrix

| # | Blocker | Required Variable(s) | Current State | Owner | Action Required |
|---|---------|---------------------|---------------|-------|-----------------|
| B1 | External IdP not provisioned | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` | Empty | Security / Infra | Provision OIDC IdP (e.g., Azure AD, Auth0, Keycloak), create API client, provide JWKS URL |
| B2 | Strong SECRET_KEY not generated | `SECRET_KEY` | Dev default (`dev-secret-change-in-production`) | DevOps | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| B3 | Staging database not provisioned | `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Local Docker defaults (`impactos/impactos@localhost`) | DBA / Infra | Provision PostgreSQL 16 + pgvector, create staging DB + user |
| B4 | Staging Redis not provisioned | `REDIS_URL` | Local Docker default | Infra | Provision Redis 7 instance |
| B5 | Staging object storage not provisioned | `OBJECT_STORAGE_PATH`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | Local MinIO defaults | Infra | Provision S3 or dedicated MinIO with staging credentials |
| B6 | LLM API keys not configured | `ANTHROPIC_API_KEY` (primary) | Empty | DevOps | Obtain API key from Anthropic (or accept copilot SKIP) |
| B7 | Staging DNS/URL not allocated | — | No staging URL | Infra | Allocate `staging.impactos.example.com` or equivalent |

---

## What Code Already Handles

All blockers above are **infrastructure-only** — no code changes are needed:

| Protection | Mechanism | Evidence |
|-----------|-----------|----------|
| Dev defaults rejected in staging | `validate_settings_for_env()` → startup exit(1) | `test_config_guardrails.py` (8 tests) |
| Missing IdP → 401 on all auth | `_validate_jwt_external()` → HTTPException | `test_idp_validation.py` (6+ tests) |
| Missing LLM keys → copilot SKIP | `/api/copilot/status` returns `enabled=false` or `ready=false` | `test_copilot_status.py` (4 tests) |
| Relative storage path rejected | `validate_settings_for_env()` checks `./` prefix | `test_config_guardrails.py` |
| Placeholder DB URL rejected | `validate_settings_for_env()` checks `localhost`, `changeme` | `test_config_guardrails.py` |
| Preflight catches all above | `scripts/staging_preflight.py` → 6 executable checks | `test_staging_preflight.py` (25 tests) |
| Deploy checker validates env file | `scripts/staging_deploy.py check` → 8 prerequisite checks | `test_staging_deploy.py` (48 tests) |

---

## Verified Deployment Path

When infrastructure blockers are resolved, the deployment path is:

```bash
# 1. Configure .env.staging (fill in all real values)
cp .env.staging.example .env.staging
$EDITOR .env.staging

# 2. Validate prerequisites
python scripts/staging_deploy.py check --env-file .env.staging

# 3. Build and start staging stack
make staging-up

# 4. Run preflight
make staging-preflight

# 5. Run smoke tests
make staging-smoke
```

This path has been verified against the dev stack (see evidence below).

---

## Dev Stack Verification Evidence

### Smoke Test (all 6 stages PASS)

```
Stage               Status   Detail
-------------------------------------------------------------------
startup             [PASS]   Server reachable, version=0.1.0
readiness           [PASS]   Server is ready
auth_enforcement    [PASS]   Unauthenticated request correctly returned 401
health_components   [PASS]   All components present: ['api', 'database', 'object_storage', 'redis']
api_schema          [PASS]   OpenAPI schema valid with 109 paths
copilot_smoke       [PASS]   Copilot runtime ready, providers=['LOCAL', 'ANTHROPIC', 'OPENAI', 'OPENROUTER']

Overall: PASS
```

### Preflight (correctly rejects dev environment)

```
Check               Status   Detail
-------------------------------------------------------------------
environment         [FAIL]   ENVIRONMENT is 'dev' -- must be staging or prod for deployment
config_validation   [PASS]   All config validations passed
alembic             [PASS]   Database is at head revision
readiness           [PASS]   Server is ready
health_components   [PASS]   All components present: ['api', 'database', 'object_storage', 'redis']
no_secrets          [PASS]   No secret values detected in report

Overall: FAIL (correctly — dev environment detected)
```

### Deploy Checker (correctly flags all dev defaults)

```
Check                  Status   Detail
-------------------------------------------------------------------
env_file_exists        [PASS]   .env.example exists
environment            [FAIL]   ENVIRONMENT='dev' — must be 'staging' or 'prod'
secret_key             [FAIL]   SECRET_KEY uses dev default — set a real secret
database_url           [FAIL]   DATABASE_URL contains 'localhost' — use real credentials
object_storage         [FAIL]   OBJECT_STORAGE_PATH='./uploads' — relative paths rejected
idp_config             [FAIL]   Missing or placeholder IdP config: JWT_ISSUER, JWT_AUDIENCE, JWKS_URL
minio_credentials      [FAIL]   MinIO credentials are dev defaults
postgres_credentials   [FAIL]   POSTGRES_USER or POSTGRES_PASSWORD is empty

Overall: FAIL (correctly — 7 dev defaults detected)
```

---

## Rollback Command Path

If staging deployment encounters issues after a successful start:

### Quick Rollback (no schema change)

```bash
# Stop API + worker
docker compose -f docker-compose.yml -f docker-compose.staging.yml stop api celery-worker

# Restart with previous image
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d api celery-worker

# Verify
curl -f http://STAGING_URL/readiness
curl -f http://STAGING_URL/health
```

### Rollback with Migration

```bash
# Stop services
docker compose -f docker-compose.yml -f docker-compose.staging.yml stop api celery-worker

# Downgrade one migration
docker compose exec api alembic downgrade -1

# Verify migration state
docker compose exec api alembic current

# Restart
docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d api celery-worker

# Verify
curl -f http://STAGING_URL/readiness
```

### Full Teardown

```bash
# Keep volumes (data preserved)
docker compose -f docker-compose.yml -f docker-compose.staging.yml down

# Destroy volumes (complete reset)
docker compose -f docker-compose.yml -f docker-compose.staging.yml down -v
```

---

## Recommendation

**Status: GO (conditional on infrastructure provisioning)**

All code, tooling, and automation is complete. The deployment path from `.env.staging` to "staging-live" is:

1. `cp .env.staging.example .env.staging` → fill in real values
2. `python scripts/staging_deploy.py check` → validate all 8 prerequisites
3. `make staging-up` → build + start + migrate
4. `make staging-preflight` → verify config + alembic + health
5. `make staging-smoke` → verify startup + auth + schema + copilot

The only remaining work is infrastructure provisioning (B1-B7), which is outside the application codebase.
