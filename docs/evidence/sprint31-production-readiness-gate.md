# Sprint 31: Production Readiness Gate

**Date:** 2026-03-06
**Sprint:** 31 — Full-System Staging E2E + Production Readiness Gate
**Branch:** `phase3-sprint31-full-system-staging-e2e-production-readiness`

---

## Gate Status: IN PROGRESS — awaiting live staging acceptance

Full-system production readiness requires live staging acceptance via `staging_full_e2e.py --strict --validate-outputs` with all 15 stages passing. All application-level code is complete; infrastructure provisioning (B1-B7) is the sole remaining gate.

---

## Application Readiness (All Layers)

### Auth Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Backend JWKS/RS256 auth | READY | `src/api/auth_deps.py` — `_validate_jwt_external()` with `_fetch_jwks_public_key()`, fail-closed on missing config |
| Frontend OIDC provider | READY | `frontend/src/lib/auth.ts` — `buildProviders()` with wellKnown discovery, PKCE+state |
| E2E OIDC client_credentials | READY | `stage_oidc_token()` — discovery + token exchange, strict mode rejects `--auth-token` |
| Fail-fast on missing config | READY | Missing OIDC vars cause module-load failure (not runtime) |
| Dev credentials guard | READY | `CredentialsProvider` only used when `NEXTAUTH_PROVIDER != oidc` |
| Auth matrix enforcement | READY | `test_auth_matrix.py` — 401/403/404 boundary tests |

### Frontend Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Staging env template | READY | `frontend/.env.staging.example` |
| Compose env passthrough | READY | `docker-compose.staging.yml` frontend environment block |
| Login UI modes | READY | `login/page.tsx` — SSO button for OIDC, email form for credentials |
| Deploy checker validates frontend | READY | `check_frontend_config()` — SKIP/PASS/FAIL |
| E2E OIDC provider verification | READY | `stage_frontend_verify()` — strict mode checks `/api/auth/providers` for `impactos-oidc` |

### API Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Startup config validation | READY | `_check_startup_config()` rejects dev defaults in staging |
| Health endpoint (4 components) | READY | `test_health_dependencies.py` |
| Readiness endpoint | READY | `test_readiness.py` |
| OpenAPI schema | READY | 109 paths documented |
| Auth enforcement (401) | READY | `test_auth_matrix.py` |

### Worker Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Celery worker in compose | READY | `docker-compose.yml` celery-worker service |
| Worker health via Redis broker | READY | `stage_worker_health()` in smoke harness |
| Async job processing | READY | Extraction, export generation use Celery tasks |
| E2E worker proof | READY | `stage_extraction_trigger()` + `stage_extraction_wait()` — submit + poll real Celery job |

### Deterministic Engine Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Leontief I-O computation | READY | `src/engine/` — NumPy/SciPy, no LLM calls |
| Math boundary enforcement | READY | `test_llm_client_policy.py` — AI never computes economics |
| Batch run support | READY | `src/api/runs.py` — single and batch run endpoints |
| E2E connected run | READY | `stage_scenario_run()` — uses `scenario_spec_id` from `stage_scenario_build()` (not arbitrary listing) |

### AI/LLM Pipeline Layer

| Check | Status | Evidence |
|-------|--------|----------|
| AI compile (sector mapping) | READY | `stage_ai_compile()` — `POST /compiler/compile` with `document_id` from upload stage |
| Scenario build (connected) | READY | `stage_scenario_build()` — auto-approves AI suggestions as decisions, compiles to shock_items |
| Depth analysis | READY | `stage_depth_analysis()` — uses `scenario_spec_id` from build stage |
| Copilot chat (real LLM) | READY | `stage_copilot_query()` — creates session + sends message + verifies LLM response content/tokens |

### Governance Layer

| Check | Status | Evidence |
|-------|--------|----------|
| NFF claims/evidence/assumptions | READY | `src/api/governance.py` |
| Publication gate | READY | Sandbox → governed gate |
| E2E governance evaluation | READY | `stage_governance_evaluate()` — `POST /governance/claims/extract` + `GET /governance/status/{run_id}`; 0 claims = FAIL |

### Export Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Export generation | READY | `src/api/exports.py` — xlsx/pptx/pdf |
| Artifact download | READY | `GET /exports/{id}/download/{format}` |
| Variance bridge exports | READY | `POST /variance-bridge` |
| E2E export + download | READY | `stage_export_download()` — create + download + verify non-empty content |

### Output Validation Layer

| Check | Status | Evidence |
|-------|--------|----------|
| Golden fixture rules | READY | `scripts/fixtures/e2e_golden.json` — required metric_types, value ranges, non-zero check |
| Persisted data consistency | READY | `stage_output_validation()` — in-memory vs persisted result_set comparison |

---

## Deployment Tooling Readiness

| Tool | Checks/Stages | Status |
|------|---------------|--------|
| `staging_deploy.py` | 9 checks (env, environment, secret_key, database_url, object_storage, idp_config, minio_creds, postgres_creds, frontend_config) | READY |
| `staging_preflight.py` | 6 checks (environment, config_validation, alembic, readiness, health_components, no_secrets) | READY |
| `staging_smoke.py` | 7 stages (startup, readiness, auth_enforcement, health_components, api_schema, copilot_smoke, worker_health) | READY |
| `staging_full_e2e.py` | 15 stages (oidc_token, frontend_verify, api_health, workspace_access, document_upload, extraction_trigger, extraction_wait, ai_compile, scenario_build, depth_analysis, scenario_run, governance_evaluate, copilot_query, export_download, output_validation) + `--strict` + `--validate-outputs` + `--oidc-*` | READY |

---

## Infrastructure Blockers (External)

| # | Blocker | Severity | Resolution Owner | Estimated Effort |
|---|---------|----------|-----------------|-----------------:|
| B1 | External IdP (OAuth2/OIDC) | Critical | Security | 2-4 hours (if using Azure AD / Auth0 / Keycloak) |
| B2 | Strong SECRET_KEY | Trivial | DevOps | 1 minute |
| B3 | Staging PostgreSQL | Critical | DBA | 1-2 hours |
| B4 | Staging Redis | Critical | Infra | 30 minutes |
| B5 | Staging object storage (S3/MinIO) | Critical | Infra | 1 hour |
| B6 | LLM API keys | Important | DevOps | 10 minutes (if account exists) |
| B7 | Staging DNS/URLs | Important | Infra | 1 hour |

**Total estimated infra provisioning time:** 6-9 hours (one-time setup).

---

## Rollback Readiness

| Rollback Type | Command | Status |
|---------------|---------|--------|
| Quick (no schema change) | `docker compose ... stop api celery-worker && docker compose ... up -d` | DOCUMENTED |
| Migration rollback | `alembic downgrade -1` | DOCUMENTED |
| Full teardown (keep data) | `docker compose ... down` | DOCUMENTED |
| Full teardown (destroy data) | `docker compose ... down -v` | DOCUMENTED |
| Rollback execution proof | Not yet executed | BLOCKED (requires staging infra) |

---

## Secret Ownership + Rotation

| Secret | Generation Method | Rotation Path |
|--------|------------------|---------------|
| SECRET_KEY | `python -c "import secrets; print(secrets.token_urlsafe(64))"` | Regenerate + restart API |
| NEXTAUTH_SECRET | `python -c "import secrets; print(secrets.token_urlsafe(64))"` | Regenerate + restart frontend |
| POSTGRES_PASSWORD | Generate via password manager | Rotate in DB + update .env.staging |
| MINIO_SECRET_KEY | Generate via password manager | Rotate in MinIO admin + update .env.staging |
| OIDC_CLIENT_SECRET | Provided by IdP admin | Rotate in IdP + update .env.staging |
| ANTHROPIC_API_KEY | Anthropic dashboard | Rotate in dashboard + update .env.staging |

---

## GO Criteria

Sprint 31 reaches GO when ALL of the following are verified against live staging:

- [ ] OIDC token acquired via real IdP client_credentials grant
- [ ] Frontend reachable at staging URL with OIDC provider configured
- [ ] API health returns all 4 components healthy
- [ ] Auth enforcement: unauthenticated → 401, unauthorized → 403
- [ ] Authenticated workspace access succeeds
- [ ] Document upload to real object storage succeeds
- [ ] Extraction via real provider completes (Celery worker proof)
- [ ] AI compile via real LLM produces sector mapping suggestions
- [ ] Scenario built from AI compile output with auto-approved decisions
- [ ] Deterministic engine run produces persisted results using compiled scenario
- [ ] Governance extracts claims and evaluates NFF status for run
- [ ] Copilot chat interaction with real LLM produces response
- [ ] Export generated and downloadable
- [ ] Output correctness validated against golden fixture rules
- [ ] Rollback rehearsed (or justified limitation documented)
- [ ] All staging scripts pass against live staging

**Exact GO command:**
```bash
python scripts/staging_full_e2e.py \
    --api-url $API_URL \
    --frontend-url $FE_URL \
    --oidc-issuer $OIDC_ISSUER \
    --oidc-client-id $OIDC_CLIENT_ID \
    --oidc-client-secret $OIDC_SECRET \
    --strict --validate-outputs
```

**Current state:** All application code is complete. Waiting on infrastructure provisioning (B1-B7) to run live acceptance.
