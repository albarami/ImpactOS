# Sprint 31: Full-System Staging E2E + Production Readiness Gate

**Date:** 2026-03-06
**Branch:** `phase3-sprint31-full-system-staging-e2e-production-readiness`
**Baseline:** main at `ebd9413` (post-Sprint 30 merge, tag `sprint-30-complete`)

---

## Mission

Close the remaining gap between "backend staging tooling ready" (Sprint 30) and "full-system live-accepted in staging" by hardening frontend auth, extending deployment tooling for all services, building a full-system E2E acceptance harness, and preparing the production-readiness gate.

### Sprint 30 → Sprint 31 Transition

Sprint 30 delivered backend-only staging tooling. Sprint 31 closes these gaps:

| Gap | Sprint 30 State | Sprint 31 Resolution |
|-----|----------------|---------------------|
| G1: Frontend auth | Dev-only CredentialsProvider | Configurable OIDC via `buildProviders()` |
| G2: Frontend staging env | No frontend env template | `frontend/.env.staging.example` created |
| G3: Frontend compose wiring | Frontend excluded from staging | docker-compose.staging.yml extended with frontend env passthrough |
| G4: Full-system E2E harness | No acceptance harness | `scripts/staging_full_e2e.py` with 9 stages |
| G5: Deploy checker frontend | Backend-only checks (8) | Extended to 9 checks with `check_frontend_config()` |
| G6: Worker health | Not verified in smoke | `stage_worker_health()` added as smoke stage 7 |
| G7: Runbook coverage | Backend-only runbook | Updated for full-system deployment |

---

## S31-0: Audit + Gap Analysis

### Pre-Implementation Audit

Audit performed against main at `ebd9413` (Sprint 30 merge commit):

**Baseline:**
- Backend tests: 5,095 collected
- Frontend tests: 359 passed
- Alembic: at head `020_chat_sessions_messages`

**7 Application Gaps Identified (G1-G7):** See table above.

**7 Infrastructure Blockers (B1-B7):** Unchanged from Sprint 30.

| # | Blocker | Status | Owner |
|---|---------|--------|-------|
| B1 | External IdP not provisioned | BLOCKED | Security |
| B2 | Strong SECRET_KEY not generated | Trivial (one command) | DevOps |
| B3 | Staging database not provisioned | BLOCKED | DBA |
| B4 | Staging Redis not provisioned | BLOCKED | Infra |
| B5 | Staging object storage not provisioned | BLOCKED | Infra |
| B6 | LLM API keys not configured | BLOCKED | DevOps |
| B7 | Staging DNS/URL not allocated | BLOCKED | Infra |

**Verdict:** G1-G7 are application-level gaps fixable in this sprint. B1-B7 are external infrastructure blockers requiring provisioning outside the repository.

---

## S31-1: Application Gap Closure (G1-G7)

### G1: Configurable Frontend Auth Provider

**Files:**
- `frontend/src/lib/auth.ts` — `buildProviders()` function
- `frontend/src/lib/__tests__/auth.test.ts` — 9 tests
- `frontend/src/app/login/page.tsx` — OIDC vs credentials login UI

**Implementation:**
- `buildProviders()` reads `NEXTAUTH_PROVIDER` env var
- OIDC mode: generic OAuth provider with `wellKnown` discovery, PKCE + state checks
- Credentials mode: dev-only CredentialsProvider (default)
- Fail-fast on missing OIDC vars at module load time
- JWT callback for OIDC profile mapping (sub → id, name, email)
- Login page reads `NEXT_PUBLIC_AUTH_MODE` to switch UI

**Tests:** 9 tests covering both auth modes, fail-fast, wellKnown URL, DEV_USER_ID format.

### G2-G3: Frontend Staging Env + Compose Wiring

**Files:**
- `frontend/.env.staging.example` — Frontend staging env template
- `.env.staging.example` — Extended with frontend section
- `docker-compose.staging.yml` — Frontend service env passthrough

**Implementation:**
- Frontend env template with NEXTAUTH_SECRET, OIDC vars, NEXT_PUBLIC_API_URL, NEXT_PUBLIC_AUTH_MODE
- Root staging template extended with 10 frontend variables
- docker-compose.staging.yml passes all staging env vars to frontend service via `${}` interpolation
- Frontend included via `--profile frontend-staging` flag

### G5: Deploy Checker Frontend Checks

**Files:**
- `scripts/staging_deploy.py` — `check_frontend_config()` (check 9)
- `tests/scripts/test_staging_deploy.py` — 9 new tests

**Implementation:**
- Returns SKIP if no frontend vars present (frontend not being deployed)
- Validates NEXTAUTH_SECRET: non-empty, not dev default, not placeholder
- When provider=oidc: validates OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET
- Integrated as check 9 in `run_checks()`

**Tests:** 9 tests — all_set_passes, credentials_passes, missing_secret_fails, dev_default_fails, placeholder_fails, oidc_missing_issuer, oidc_missing_client_id, oidc_placeholder_fails, not_included_skip.

### G6: Worker Health Verification

**Files:**
- `scripts/staging_smoke.py` — `stage_worker_health()` (stage 7)
- `tests/scripts/test_staging_smoke.py` — 4 new tests

**Implementation:**
- Checks Redis broker health via `/health` endpoint `checks` key as proxy for Celery worker readiness
- Handles both string ("ok") and dict ({"status": "healthy"}) response formats
- Added as stage 7 in smoke pipeline after copilot_smoke

**Tests:** 4 tests — redis_healthy_passes, redis_unhealthy_fails, health_endpoint_error_fails, connection_error_fails.

### G4: Full-System E2E Acceptance Harness

**Files:**
- `scripts/staging_full_e2e.py` — 9-stage E2E harness
- `tests/scripts/test_staging_full_e2e.py` — 27 tests

**Stages:**

| # | Stage | Description | Prerequisites |
|---|-------|-------------|---------------|
| 1 | `frontend_reachable` | GET frontend URL, expect 200 HTML | Frontend URL |
| 2 | `api_health` | GET /health, all 4 components healthy | API URL |
| 3 | `workspace_access` | Authenticated workspace list/create | Auth token |
| 4 | `document_upload` | Upload test fixture to object storage | Workspace ID |
| 5 | `copilot_reachable` | Copilot runtime status check | API URL |
| 6 | `scenario_run` | Deterministic engine run | Workspace ID, scenarios |
| 7 | `governance_check` | Governance layer reachable | Workspace ID |
| 8 | `export_create` | Export generation from run results | Run ID |
| 9 | `export_download` | Artifact download verification | Export ID |

**Features:**
- `E2EContext` flows IDs (workspace_id, document_id, run_id, export_id) between stages
- Cascade-skip: if API health fails, all downstream stages auto-SKIP
- Auth token from `--auth-token` flag or `$STAGING_AUTH_TOKEN` env var
- `--validate-outputs` flag for output correctness validation
- Table and JSON output modes
- Trace section captures all persisted IDs for provenance

**Tests:** 27 tests covering all 9 stage functions, report structure, cascade, JSON serialization, and trace capture.

### G7: Runbook + Evidence Updates

**Files:**
- `docs/runbooks/staging-deployment.md` — Updated for full-system deployment
- `docs/evidence/sprint31-full-system-staging-e2e.md` — This file
- `docs/evidence/sprint31-production-readiness-gate.md` — Production readiness gate

**Changes to Runbook:**
- Updated scope from "backend only" to "full system"
- Added frontend prerequisites (P7, P8)
- Added full-system build commands with `--profile frontend-staging`
- Added worker_health to expected smoke stages
- Added Step 8: Full-System E2E Acceptance
- Updated "Not Covered" section (removed frontend exclusion)

---

## S31-2: Test Counts

| Suite | Count | Result |
|-------|-------|--------|
| Backend (pytest) | 5,106 passed, 29 skipped | 0 failures |
| Frontend (vitest) | 360 passed (40 files) | 0 failures |
| Staging scripts total | 176 | 0 failures |
| — Deploy tests | 59 | 0 failures |
| — Preflight tests | 25 | 0 failures |
| — Smoke tests | 29 | 0 failures |
| — E2E harness tests | 30 | 0 failures |
| — Seed tests | 33 | 0 failures |
| Alembic current | `020_chat_sessions_messages (head)` | Clean |
| Alembic check | No new upgrade operations | Clean |

---

## S31-3: Infrastructure Blocker Status

### Status: BLOCKED — infrastructure provisioning required

All 7 application gaps (G1-G7) are closed. The remaining blockers are external infrastructure items that cannot be resolved from within the repository:

| # | Blocker | Status | What's Needed | Owner |
|---|---------|--------|---------------|-------|
| B1 | External IdP | BLOCKED | Provision OAuth2/OIDC IdP, configure client app, provide JWT_ISSUER + JWT_AUDIENCE + JWKS_URL + OIDC client credentials | Security |
| B2 | SECRET_KEY | BLOCKED (trivial) | Run `python -c "import secrets; print(secrets.token_urlsafe(64))"` | DevOps |
| B3 | Staging database | BLOCKED | Provision PostgreSQL, provide POSTGRES_USER + POSTGRES_PASSWORD + DATABASE_URL | DBA |
| B4 | Staging Redis | BLOCKED | Provision Redis, provide REDIS_URL | Infra |
| B5 | Object storage | BLOCKED | Provision S3/MinIO, provide MINIO_ACCESS_KEY + MINIO_SECRET_KEY + OBJECT_STORAGE_PATH | Infra |
| B6 | LLM API keys | BLOCKED | Provide ANTHROPIC_API_KEY or equivalent for copilot/extraction/depth | DevOps |
| B7 | DNS/URLs | BLOCKED | Allocate staging DNS for frontend and API, configure NEXT_PUBLIC_API_URL + NEXTAUTH_URL | Infra |

### Resolution Path

When infrastructure is provisioned:
1. `cp .env.staging.example .env.staging` → fill in real values
2. `python scripts/staging_deploy.py check --env-file .env.staging` → all 9 PASS
3. `docker compose ... --profile frontend-staging up -d --build` → full system starts
4. `python scripts/staging_preflight.py --url $API_URL` → all 6 PASS
5. `python scripts/staging_smoke.py --url $API_URL` → all 7 PASS (or 6 PASS + copilot SKIP)
6. `python scripts/staging_full_e2e.py --api-url $API_URL --frontend-url $FE_URL --auth-token $TOKEN` → all 9 PASS (or expected SKIPs)

---

## S31-4: Go/No-Go Status

### Status: CONDITIONAL NO-GO (application ready, infrastructure blocked)

**What Sprint 31 proves:**
1. Frontend auth is configurable — OIDC for staging/prod, credentials for dev only
2. Frontend staging deployment path is wired — env templates, compose passthrough
3. Deploy prerequisite checker validates full system (9 checks: backend + frontend)
4. Smoke harness covers 7 stages including worker health
5. Full-system E2E acceptance harness covers 9 stages (auth → workspace → upload → run → export → download)
6. Runbook updated for full-system deployment
7. All changes are test-covered (27 new E2E + 13 new staging tests)

**What Sprint 31 does NOT prove (requires infrastructure):**
1. Real IdP authentication works end-to-end
2. Frontend renders and functions in staging
3. Real extraction/compile/depth with LLM providers
4. Real deterministic engine runs with persisted outputs
5. Real export generation and artifact download
6. Output correctness against expected results
7. Rollback execution against staging

**Decision rule:**
- If B1-B7 are resolved and the live staging path passes → **GO**
- If G1-G7 are done but infrastructure is missing → **BLOCKED / NO-GO** for full-system acceptance ← **CURRENT STATE**

---

## Sprint 31 Files Delivered

**New:**
- `scripts/staging_full_e2e.py` — 9-stage full-system E2E acceptance harness
- `tests/scripts/test_staging_full_e2e.py` — 27 E2E harness tests
- `frontend/.env.staging.example` — Frontend staging env template
- `frontend/src/lib/__tests__/auth.test.ts` — 9 frontend auth tests
- `docs/evidence/sprint31-full-system-staging-e2e.md` — This file
- `docs/evidence/sprint31-production-readiness-gate.md` — Production readiness gate

**Updated:**
- `frontend/src/lib/auth.ts` — Configurable buildProviders() with OIDC support
- `frontend/src/app/login/page.tsx` — OIDC vs credentials login UI
- `.env.staging.example` — Extended with frontend section
- `docker-compose.staging.yml` — Frontend staging env passthrough
- `scripts/staging_deploy.py` — Extended with check_frontend_config (check 9)
- `scripts/staging_smoke.py` — Extended with stage_worker_health (stage 7)
- `tests/scripts/test_staging_deploy.py` — 9 new frontend check tests
- `tests/scripts/test_staging_smoke.py` — 4 new worker health tests
- `docs/runbooks/staging-deployment.md` — Updated for full-system deployment
- `.gitignore` — Allow .env.staging.example files through exception rules
