# Sprint 24: Go/No-Go Dossier

**Date:** 2026-03-06 (updated post-Sprint 29)
**Prepared by:** Engineering
**Status:** GO (conditional on infrastructure prerequisites only — see Section 7)

---

## 1. Go Criteria Assessment

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | MVP-1 through MVP-23 complete with test evidence | ✅ GO | All 23 MVPs have code + tests. Build tracker shows commits + test counts for each. |
| 2 | No planned build tracker entries remain | ✅ GO | Master Build Plan v2 shows all rows filled. Sprint 24 carryovers I-2 and I-4 closed. |
| 3 | Methodology parity gate: SG benchmark within 0.1% | ✅ GO | Golden-run benchmark tests pass (Sprint 18 evidence). |
| 4 | Sprint 23 carryovers closed | ✅ GO | I-2: ScenarioSpec wired to bridge engine (8bece0c). I-4: RunSelector populated (d9829c6). |
| 5 | Full test suite green | ✅ GO | Backend 4,987 collected, Frontend 350 passed. 0 failures. (Updated post-S29) |
| 6 | OpenAPI spec current | ✅ GO | Regenerated and validated at Sprint 29. |
| 7 | Alembic migrations chain correctly | ✅ GO | Head at 020_chat_sessions_messages, all migrations chain from 001. |
| 8 | Staging preflight automation | ✅ GO | `scripts/staging_preflight.py` — repeatable, structured output. (Sprint 29) |
| 9 | Staging smoke harness | ✅ GO | `scripts/staging_smoke.py` — one-command deployment verification. (Sprint 29) |
| 10 | Non-dev fail-closed paths verified | ✅ GO | All 14 fail-closed paths tested. (Sprint 29 audit) |

**Go criteria: 10/10 met.**

---

## 2. Rollback Strategy

### Database Rollback

```bash
# Step 1: Downgrade migration 019 (scenario_spec_id columns)
python -m alembic downgrade 018_variance_bridge_analyses

# Step 2: If needed, downgrade migration 018 (variance_bridge_analyses table)
python -m alembic downgrade 017_workshop_sessions

# Step 3: Verify
python -m alembic current
```

### Code Rollback

```bash
# Option A: Revert to sprint-23-complete tag
git checkout sprint-23-complete

# Option B: Revert specific Sprint 24 commits (preserves later work)
git revert --no-commit d93cff1..HEAD
git commit -m "revert: roll back Sprint 24 changes"
```

### Rollback Testing

After any rollback:
```bash
python -m pytest tests/ -q --tb=short  # Must pass
python -m alembic check               # Must report no drift
```

### Rollback Time Estimate

| Scenario | Time |
|----------|------|
| Code-only rollback (git revert) | ~5 minutes |
| Code + migration rollback | ~10 minutes |
| Full rollback + verification | ~15 minutes |

---

## 3. Unresolved Risks

### Risk 1: External IdP Integration (MEDIUM)

**Description:** JWT auth is tested with mock tokens. Real external IdP (Azure AD / Auth0) integration has not been live-tested.

**Mitigation:** Set `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL` in staging config. Run auth smoke test with real tokens before production.

**Impact if unresolved:** Users cannot authenticate.

### Risk 2: Real Provider Keys (MEDIUM)

**Description:** AI components (compiler, depth engine) are tested with mocks or dev-mode fallbacks. Real LLM API keys (OpenAI/Anthropic) not configured.

**Mitigation:** The system is designed with fail-closed semantics — non-dev environments require real keys. Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in staging.

**Impact if unresolved:** AI-assisted features (compilation, depth analysis) unavailable. Deterministic engine still works.

### Risk 3: Object Storage Configuration (LOW)

**Description:** S3-compatible object storage is mocked in tests. Real MinIO/S3 not configured for staging.

**Mitigation:** Set non-local object storage config. Export/download pipeline has integration tests but not against real storage.

**Impact if unresolved:** Export downloads fail. Core analysis still works.

### Risk 4: Load Testing Not Performed (LOW)

**Description:** No load/performance testing has been conducted. Concurrent user behavior is untested.

**Mitigation:** The system uses async FastAPI + connection pooling. Expected initial load is 5-10 concurrent users (internal tool). Monitor and scale if needed.

**Impact if unresolved:** Performance degradation under load. Not a launch blocker for internal tool.

### Risk 5: PostgreSQL Migration on Real Data (LOW)

**Description:** Migration 019 adds nullable columns — safe for empty tables. But migration 018 (variance_bridge_analyses) creates a new table — no data loss risk.

**Mitigation:** Run `alembic upgrade head` on staging database. Verify with `alembic check`.

**Impact if unresolved:** None — both migrations are additive.

---

## 4. Sprint 24 Deliverables Summary

| Deliverable | Commit | Description |
|------------|--------|-------------|
| Migration 019 | `d93cff1` | scenario_spec_id/version on run_snapshots |
| I-2 closure | `8bece0c` | ScenarioSpec wired through run persistence + bridge engine |
| List-runs API | `85a3b13` | GET /engine/runs with pagination |
| I-4 closure | `d9829c6` | RunSelector populated from workspace runs |
| OpenAPI | `1146f70` | Regenerated with list-runs endpoint |

---

## 5. Post-Launch Items (Not Blocking)

1. **E2E staging smoke test** with real credentials (IdP + LLM + storage)
2. **Load testing** for concurrent scenario analysis workflows
3. **Monitoring dashboard** for API latency + error rates
4. **Backup/restore procedure** verification for PostgreSQL
5. **Frontend deployment** (Next.js build + CDN configuration)

---

## 6. Recommendation (Original Sprint 24)

**CONDITIONAL GO.** All build criteria are met. The system is functionally complete with 4932 tests passing across all layers. The remaining risks are infrastructure/configuration items that can be resolved during staging deployment without code changes.

**Proceed to staging deployment when:**
1. External IdP credentials configured
2. LLM API keys set (or fail-closed behavior accepted for initial deployment)
3. Object storage endpoint configured
4. `alembic upgrade head` succeeds on staging database

---

## 7. Post-Sprint 29 Update

**Date:** 2026-03-06
**Status:** GO

### What Changed Since Sprint 24

| Sprint | What It Added | Tests Added |
|--------|---------------|-------------|
| S25 | Economist Copilot v1 (chat, agent, confirmation gate) | +53 BE, +13 FE |
| S26 | Copilot hardening (all 5 backlog items resolved) | +30 BE, +8 FE |
| S27 | Tool execution (workspace-scoped handlers, safety caps) | +124 BE, +8 FE |
| S28 | Real execution (engine runs, governance exports, narrative) | +106 BE, +14 FE |
| S29 | Staging activation (preflight, smoke, fail-closed audit) | +16 BE |

### Current State

- **Backend tests:** 4,987+ collected, 0 failures
- **Frontend tests:** 350 passed (39 files), 0 failures
- **Alembic:** `020_chat_sessions_messages (head)`, no pending migrations
- **OpenAPI:** Regenerated and validated
- **Tags:** `sprint-25-complete` through `sprint-28-complete` on main

### Risk Resolution

| Original Risk | Current Status |
|---------------|---------------|
| Risk 1: External IdP | **Mitigated.** Preflight script validates JWT config. Fail-closed tests verify 401 on missing IdP. |
| Risk 2: Real Provider Keys | **Mitigated.** Fail-closed tests for compiler, depth, copilot all verified. System degrades gracefully. |
| Risk 3: Object Storage | **Mitigated.** Preflight rejects relative paths in non-dev. Health check monitors storage. |
| Risk 4: Load Testing | **Accepted.** Internal tool with 5-10 concurrent users. Not blocking. |
| Risk 5: PostgreSQL Migration | **Closed.** Migration 020 added (chat tables). All additive, no data loss risk. |

### Remaining Prerequisites

These are **infrastructure configuration** items, not code changes:

1. Set `ENVIRONMENT=staging` or `ENVIRONMENT=prod`
2. Configure external IdP: `JWT_ISSUER`, `JWT_AUDIENCE`, `JWKS_URL`
3. Set strong `SECRET_KEY` (not dev default)
4. Configure `DATABASE_URL` with real credentials
5. Configure `OBJECT_STORAGE_PATH` to absolute or S3 path
6. Set `REDIS_URL` for async job queue
7. Optionally set LLM API keys for AI-assisted features
8. Run `alembic upgrade head` on staging database

### Deployment Verification

```bash
# Preflight (before starting server)
python scripts/staging_preflight.py --json

# Start server, then run smoke
python scripts/staging_smoke.py --json --url http://localhost:8000
```

### Recommendation

**GO.** The system is functionally complete with 4,987+ backend tests and 350 frontend tests. All non-dev fail-closed paths are verified. Staging preflight and smoke automation are in place. The only remaining items are infrastructure configuration — no further code changes are required for deployment.
