# ImpactOS — Release Readiness Checklist

## Release Readiness Matrix

| Component | Required Config | Dev Behavior | Staging/Prod Behavior | Fail Mode | Test Evidence |
|---|---|---|---|---|---|
| **Auth (IdP)** | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` | HS256 dev stub | RS256 + JWKS mandatory | 401 fail-closed | `test_idp_validation.py`, `test_deploy_guard.py` |
| **Secret Key** | `SECRET_KEY` | Dev default accepted | Dev default rejected | Startup validation error | `test_config_guardrails.py` |
| **Database** | `DATABASE_URL` | Local default OK | Placeholder creds rejected | Startup validation error | `test_config_guardrails.py` |
| **Object Storage** | `OBJECT_STORAGE_PATH` | `./uploads` OK | Relative path rejected | Startup validation error | `test_config_guardrails.py` |
| **LLM Providers** | `ANTHROPIC_API_KEY` etc. | Optional (local fallback) | Optional (ProviderUnavailableError) | Per-call fail | `test_llm_client_policy.py` |
| **Extraction** | `EXTRACTION_PROVIDER` | `local` OK | Azure DI recommended | Falls back to local | `test_extraction_reliability.py` |
| **Redis** | `REDIS_URL` | Optional (sync mode) | Required for async jobs | Health check degraded | `test_readiness.py` |
| **Role Gates** | (code-enforced) | Active | Active | 403 for insufficient role | `test_role_gates.py`, `test_auth_matrix.py` |
| **Workspace Auth** | (code-enforced) | Active | Active | 401/404 | `test_auth_boundary.py`, `test_workspace_authz.py` |

## Pre-Deploy Preflight Checks

```bash
# 1. Verify environment is not dev
echo $ENVIRONMENT  # must be "staging" or "prod"

# 2. Run config validation
python -c "
from src.config.settings import get_settings, validate_settings_for_env
s = get_settings()
errors = validate_settings_for_env(s)
if errors:
    print('FAIL:', errors)
    exit(1)
print('Config OK for', s.ENVIRONMENT)
"

# 3. Run migrations
python -m alembic upgrade head

# 4. Check readiness
curl -f http://localhost:8000/readiness || echo "NOT READY"

# 5. Smoke test auth
curl -s http://localhost:8000/v1/workspaces \
  -H "Authorization: Bearer INVALID" | grep -q "401"
echo "Auth enforcement: OK"
```

## Rollback Procedure

```bash
# 1. Stop API + workers
docker compose down api celery-worker

# 2. Rollback migration (if schema changed)
python -m alembic downgrade -1

# 3. Deploy previous image tag
docker compose up -d api celery-worker

# 4. Verify rollback
curl -f http://localhost:8000/readiness
curl -f http://localhost:8000/health
```

## Go/No-Go Criteria

| Criteria | Required | How to Verify |
|---|---|---|
| All tests pass | Yes | `pytest tests -q` → 0 failures |
| Alembic at head + clean | Yes | `alembic current` + `alembic check` |
| Config validation passes | Yes | `validate_settings_for_env()` returns `[]` |
| `/readiness` returns 200 | Yes | `curl -f /readiness` |
| Auth enforced on all routes | Yes | `test_auth_matrix.py` passes |
| Role gates on sensitive endpoints | Yes | `test_role_gates.py` passes |
| No dev defaults in non-dev | Yes | `test_config_guardrails.py` passes |
| IdP configured (staging/prod) | Yes | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` set |
| Secret redaction verified | Yes | `test_deploy_guard.py` passes |
| OpenAPI valid | Yes | `openapi.json` parseable |

## MVP-14 Saudi Data Foundation Evidence

### Artifact Validation Matrix

| Field | Source | Validation | Fail Mode |
|---|---|---|---|
| `final_demand_F` | curated IO payload | shape `(n, k)` with `k > 0` and row count `n` | `MODEL_FINAL_DEMAND_DIMENSION_MISMATCH` |
| `imports_vector` | curated IO payload | vector length `n` | `MODEL_IMPORTS_VECTOR_DIMENSION_MISMATCH` |
| `compensation_of_employees` | curated IO payload | vector length `n` | `MODEL_COMPENSATION_VECTOR_DIMENSION_MISMATCH` |
| `gross_operating_surplus` | curated IO payload | vector length `n` | `MODEL_GOS_VECTOR_DIMENSION_MISMATCH` |
| `taxes_less_subsidies` | curated IO payload | vector length `n` | `MODEL_TAX_VECTOR_DIMENSION_MISMATCH` |
| `household_consumption_shares` | curated IO payload | vector length `n`, non-negative, sums to `1.0` | `MODEL_HOUSEHOLD_SHARES_DIMENSION_MISMATCH` / `MODEL_HOUSEHOLD_SHARES_INVALID_SUM` |
| `deflator_series` | curated IO payload | year keys integer-like, values numeric and `> 0` | `MODEL_DEFLATOR_INVALID` |

### MVP-14 Preflight Evidence Checklist

- Model registration with extended artifacts succeeds (`POST /v1/engine/models`).
- Model detail endpoint returns additive fields (`GET /v1/workspaces/{workspace_id}/models/versions/{model_version_id}`).
- Deterministic checksum is stable for identical artifact payloads.
- Malformed extended payloads fail closed with reason codes (HTTP `422`).
- Migration `011_model_data_extended_fields` applied at target environment.
