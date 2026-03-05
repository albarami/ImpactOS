# Sprint 24: Go/No-Go Dossier

**Date:** 2026-03-05
**Prepared by:** Engineering
**Status:** CONDITIONAL GO (see unresolved risks)

---

## 1. Go Criteria Assessment

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | MVP-1 through MVP-23 complete with test evidence | ✅ GO | All 23 MVPs have code + tests. Build tracker shows commits + test counts for each. |
| 2 | No planned build tracker entries remain | ✅ GO | Master Build Plan v2 shows all rows filled. Sprint 24 carryovers I-2 and I-4 closed. |
| 3 | Methodology parity gate: SG benchmark within 0.1% | ✅ GO | Golden-run benchmark tests pass (Sprint 18 evidence). |
| 4 | Sprint 23 carryovers closed | ✅ GO | I-2: ScenarioSpec wired to bridge engine (8bece0c). I-4: RunSelector populated (d9829c6). |
| 5 | Full test suite green | ✅ GO | Backend 4625 passed, Frontend 307 passed. 0 failures. |
| 6 | OpenAPI spec current | ✅ GO | Regenerated at 1146f70 with all endpoints including list-runs. |
| 7 | Alembic migrations chain correctly | ✅ GO | Head at 019, all migrations chain from 001. |

**Go criteria: 7/7 met.**

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

## 6. Recommendation

**CONDITIONAL GO.** All build criteria are met. The system is functionally complete with 4932 tests passing across all layers. The remaining risks are infrastructure/configuration items that can be resolved during staging deployment without code changes.

**Proceed to staging deployment when:**
1. External IdP credentials configured
2. LLM API keys set (or fail-closed behavior accepted for initial deployment)
3. Object storage endpoint configured
4. `alembic upgrade head` succeeds on staging database
