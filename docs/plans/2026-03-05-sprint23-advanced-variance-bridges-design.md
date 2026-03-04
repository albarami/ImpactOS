# Sprint 23 Design: Advanced Variance Bridges + Explainability (MVP-23)

Date: 2026-03-05
Status: Approved
Owner: Backend + Frontend

---

## 1. Summary

Sprint 23 delivers deterministic, artifact-linked variance bridge analytics with boardroom-ready explainability UX. Five sub-tasks:

| Task | Scope | Dependencies |
|------|-------|-------------|
| S23-0 | Migration test DSN/ownership normalization (012-017) | None (mandatory first) |
| S23-1 | Advanced deterministic variance bridge engine | S23-0 |
| S23-2 | Persistence + additive API exposure | S23-1 |
| S23-3 | Boardroom explainability frontend | S23-2 |
| S23-4 | Docs, evidence, contract sync | S23-3 |

---

## 2. S23-0: Migration Test Environment Normalization

### Problem

Migration tests 012-017 have inconsistent DSN configuration:
- `test_012`: uses `src.config.settings.get_settings()` (connects as `impactos` user)
- `test_013`: hardcoded `impactos` user DSN
- `test_014`: hardcoded `impactos` user DSN with env override
- `test_015-017`: hardcoded `postgres:Salim1977` superuser DSN

This causes non-deterministic ownership failures when different DB roles own different tables.

### Design

**Single policy:** All migration tests read `MIGRATION_TEST_DSN` from environment. If unset:
- **Local dev:** skip with explicit reason `"MIGRATION_TEST_DSN not set"`
- **CI:** fail hard (CI must set the variable; silent skipping masks real failures)

**Shared helper module:** `tests/migration/pg_migration_helpers.py`

```python
# Core exports:
MIGRATION_TEST_DSN: str | None   # from os.environ
PG_AVAILABLE: bool               # probe result
pg_skip_marker: pytest.MarkDecorator  # skipif(not PG_AVAILABLE, ...)

def alembic_env() -> dict[str, str]   # env with DATABASE_URL set
def run_alembic(*args) -> CompletedProcess
def table_exists(table: str) -> bool
def get_columns(table: str) -> list[str]
def exec_sql(sql: str) -> str
```

**CI enforcement:** helper detects `CI=true` env var. When `CI=true` and `MIGRATION_TEST_DSN` is unset, raise `RuntimeError` instead of skipping.

**Credential safety:** No hardcoded passwords remain in test files. All DSN values come from environment.

### Files changed

- `tests/migration/pg_migration_helpers.py` (new)
- `tests/migration/test_012_runseries_postgres.py` (refactor to use helper)
- `tests/migration/test_013_sg_provenance_postgres.py` (refactor)
- `tests/migration/test_014_assumption_workspace_postgres.py` (refactor)
- `tests/migration/test_015_path_analyses_postgres.py` (refactor)
- `tests/migration/test_016_portfolio_optimization_postgres.py` (refactor)
- `tests/migration/test_017_workshop_sessions_postgres.py` (refactor)

### Tests

- Existing migration suite runs unchanged when `MIGRATION_TEST_DSN` is set
- All 6 files use shared helper (no per-file DSN drift)
- No hardcoded credentials in any test file

---

## 3. S23-1: Advanced Deterministic Variance Bridge Engine

### Current state

`src/export/variance_bridge.py`:
- Accepts free-form `dict` payloads for run_a and run_b
- Boolean detection (changed/not-changed) with equal weight allocation
- No connection to actual DB artifacts (RunSnapshot, ResultSet, ScenarioSpec)
- Stateless, no persistence

### Design

Replace with artifact-linked engine that fetches real DB records.

**Input:** `run_a_id: UUID`, `run_b_id: UUID`, `metric_type: str` (default `"total_output"`)

**Artifact fetching:** Load from DB:
- `RunSnapshotRow` for both runs (version references)
- `ResultSetRow` for both runs filtered by `metric_type` + `series_kind='legacy'`
- `ScenarioSpecRow` linked via run metadata (if available)

**Driver extraction — based on actual existing artifacts:**

| Driver | Source artifact | Magnitude logic |
|--------|----------------|-----------------|
| PHASING | `ScenarioSpecRow.time_horizon` diff | Count of changed phasing entries |
| IMPORT_SHARE | `ScenarioSpecRow.shock_items` diff (ImportSubstitution shocks) | Count of changed import share shocks |
| MAPPING | `RunSnapshotRow.mapping_library_version_id` diff | 1.0 if different, 0.0 if same |
| CONSTRAINT | `RunSnapshotRow.constraint_set_version_id` diff | 1.0 if different, 0.0 if same |
| MODEL_VERSION | `RunSnapshotRow.model_version_id` diff | 1.0 if different, 0.0 if same |
| FEASIBILITY | `ScenarioSpecRow.shock_items` diff (ConstraintOverride shocks) | Count of changed constraint shocks |
| RESIDUAL | Computed | Enforces strict identity |

**Attribution algorithm:**

1. Compute `total_variance = result_b.values[aggregate_key] - result_a.values[aggregate_key]`
2. Extract per-driver raw magnitudes from metadata diffs (counts/booleans above)
3. If all magnitudes are zero AND `|total_variance| > tolerance`:
   - Assign 100% to RESIDUAL (no false attribution)
4. If magnitudes are nonzero:
   - `weight_i = magnitude_i / sum(magnitudes)`
   - `driver_impact_i = total_variance * weight_i`
   - `residual = total_variance - sum(driver_impacts)` (enforces strict identity)
5. Deterministic driver sort: by `DriverType` enum order, then by `abs(impact)` descending for tie-break

**Strict identity invariant:** `sum(all driver impacts including residual) == total_variance` within tolerance `1e-9`.

**Diagnostics payload:** Each bridge result includes:
- Per-driver: `raw_magnitude`, `weight`, `source_field`, `diff_summary`
- Overall: `checksum` (SHA-256 of canonical JSON), `tolerance_used`, `identity_verified: bool`

### Reason codes for invalid comparisons

| Condition | Reason code |
|-----------|------------|
| run_a not found in workspace | `BRIDGE_RUN_NOT_FOUND` |
| run_b not found in workspace | `BRIDGE_RUN_NOT_FOUND` |
| No ResultSet for metric_type | `BRIDGE_NO_RESULTS` |
| Same run_id for both | `BRIDGE_SAME_RUN` |
| Incompatible model base years | `BRIDGE_INCOMPATIBLE_RUNS` |

### Files changed

- `src/export/variance_bridge.py` (major rewrite)
- `src/models/export.py` (add bridge models)
- `tests/export/test_variance_bridge.py` (rewrite with toy fixtures)

---

## 4. S23-2: Persistence + Additive API

### New table: `variance_bridge_analyses`

```
variance_bridge_analyses
  analysis_id        UUID PK
  workspace_id       UUID FK(workspaces) NOT NULL
  run_a_id           UUID FK(run_snapshots) NOT NULL
  run_b_id           UUID FK(run_snapshots) NOT NULL
  metric_type        VARCHAR(100) NOT NULL
  analysis_version   VARCHAR(50) NOT NULL DEFAULT 'bridge_v1'
  config_json        JSONB NOT NULL          -- full config for reproducibility
  config_hash        VARCHAR(100) NOT NULL   -- SHA-256 of canonical config
  result_json        JSONB NOT NULL          -- full bridge output
  result_checksum    VARCHAR(100) NOT NULL   -- SHA-256 of result
  created_at         TIMESTAMPTZ NOT NULL
  UNIQUE(workspace_id, config_hash)
```

**Config hash computation:** `SHA-256(canonical_json({workspace_id, run_a_id, run_b_id, metric_type, analysis_version}))`.
- **Directional:** `run_a_id` and `run_b_id` are NOT sorted. Bridge A->B is different from B->A.

**Idempotency:** On duplicate `(workspace_id, config_hash)`, catch `IntegrityError`, rollback, return existing record.

### Alembic migration

New migration `018_variance_bridge_analyses` with:
- `upgrade`: create table with FK, UNIQUE, and index on `workspace_id`
- `downgrade`: drop table

### Repository: `VarianceBridgeRepository`

```python
class VarianceBridgeRepository:
    async def create(self, analysis: VarianceBridgeAnalysis) -> VarianceBridgeAnalysis
    async def get(self, workspace_id: UUID, analysis_id: UUID) -> VarianceBridgeAnalysis | None
    async def get_by_config_hash(self, workspace_id: UUID, config_hash: str) -> VarianceBridgeAnalysis | None
    async def list_for_workspace(self, workspace_id: UUID, *, limit: int = 50, offset: int = 0) -> list[VarianceBridgeAnalysis]
```

All reads are workspace-scoped. Cross-workspace access returns `None` (surfaced as 404).

### Additive API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/workspaces/{wid}/variance-bridges` | Compute + persist bridge |
| `GET` | `/v1/workspaces/{wid}/variance-bridges/{analysis_id}` | Retrieve single bridge |
| `GET` | `/v1/workspaces/{wid}/variance-bridges` | List bridges for workspace |

**Legacy compatibility:** `POST /v1/workspaces/{wid}/exports/variance-bridge` remains unchanged. It delegates to the old stateless `VarianceBridge.compare()` with free-form dict payloads. No breaking change.

### Error taxonomy (corrected)

| Condition | HTTP | Reason code | Fail mode |
|-----------|------|-------------|-----------|
| run_a or run_b not in workspace | 404 | `BRIDGE_RUN_NOT_FOUND` | Fail closed |
| No ResultSet for metric_type | 404 | `BRIDGE_NO_RESULTS` | Fail closed |
| Same run_id for both | 422 | `BRIDGE_SAME_RUN` | Reject |
| Incompatible model base years | 422 | `BRIDGE_INCOMPATIBLE_RUNS` | Reject |
| Duplicate config_hash (idempotent) | 200 | n/a | Return existing |
| Analysis not found | 404 | `BRIDGE_NOT_FOUND` | Standard |
| Auth failure | 401 | n/a | Standard |
| Role denial | 403 | n/a | Standard |

**Key correction:** Cross-workspace access uses 404 (BRIDGE_RUN_NOT_FOUND), not 403. 403 is reserved for true role/auth denials only.

### Files changed

- `src/db/tables.py` (add `VarianceBridgeAnalysisRow`)
- `alembic/versions/018_variance_bridge_analyses.py` (new migration)
- `src/models/export.py` (add `VarianceBridgeAnalysis` Pydantic model)
- `src/repositories/exports.py` (add `VarianceBridgeRepository`)
- `src/api/exports.py` (add 3 new endpoints, keep legacy)
- `src/api/dependencies.py` (add DI for new repo)
- `src/api/main.py` (wire router if needed)
- `tests/repositories/test_exports.py` (add repo tests)
- `tests/api/test_exports.py` (add API tests)
- `tests/api/test_exports_quality_wiring.py` (add bridge wiring tests)

---

## 5. S23-3: Boardroom Explainability Frontend

### Current state

No bridge UI exists. The exports page has a manual raw-UUID form for creating exports.

### Design

**New pages:**
- `/w/[workspaceId]/exports/compare` — run comparison flow with selectors
- `/w/[workspaceId]/exports/bridges/[analysisId]` — bridge detail with waterfall + driver cards

**Run comparison flow:**
1. User selects Run A and Run B from dropdowns (populated from workspace runs)
2. Selects metric type (default `total_output`)
3. Clicks "Compare" to compute bridge
4. Result renders as waterfall chart + driver narrative cards

**Waterfall visualization:**
- Horizontal bar chart: start value -> driver impacts (positive green, negative red) -> end value
- Built with existing design system (no new chart library)
- Responsive, accessible (ARIA labels, keyboard nav)

**Driver narrative cards:**
- One card per driver with: type badge, description, impact value, percentage of total
- Sorted in deterministic engine order
- Governance/context metadata: run timestamps, model versions, workspace context

**CTA links (correction #7):**
- Runs list page: "Compare Runs" CTA linking to `/exports/compare`
- Exports list page: "New Variance Bridge" CTA linking to `/exports/compare`
- No raw UUID entry in primary path (UUIDs only in URL params, not user-facing forms)

**Empty/error states:**
- No runs available: message with link to create runs
- Bridge computation failed: show reason code in user-friendly language
- Loading: skeleton cards

**Hooks:**
- `useCreateVarianceBridge(workspaceId)` — POST to create bridge
- `useVarianceBridge(workspaceId, analysisId)` — GET single bridge
- `useVarianceBridges(workspaceId)` — GET list of bridges

### Files changed

- `frontend/src/app/w/[workspaceId]/exports/compare/page.tsx` (new)
- `frontend/src/app/w/[workspaceId]/exports/bridges/[analysisId]/page.tsx` (new)
- `frontend/src/app/w/[workspaceId]/exports/page.tsx` (add CTA)
- `frontend/src/app/w/[workspaceId]/runs/page.tsx` (add CTA, if exists)
- `frontend/src/lib/api/hooks/useExports.ts` (add bridge hooks)
- `frontend/src/lib/api/schema.ts` (add bridge types)
- `frontend/src/components/exports/WaterfallChart.tsx` (new)
- `frontend/src/components/exports/DriverCard.tsx` (new)
- `frontend/src/components/exports/RunSelector.tsx` (new)
- `frontend/src/components/exports/__tests__/WaterfallChart.test.tsx` (new)
- `frontend/src/components/exports/__tests__/DriverCard.test.tsx` (new)
- `frontend/src/components/exports/__tests__/RunSelector.test.tsx` (new)

---

## 6. S23-4: Docs, Evidence, Contract Sync

- Update `docs/ImpactOS_Master_Build_Plan_v2.md` with MVP-23 row
- Update `docs/plans/2026-03-03-full-system-completion-master-plan.md` with Sprint 23 evidence
- Update `docs/evidence/release-readiness-checklist.md` with variance-bridge section
- Regenerate `openapi.json` and verify validity
- Document migration-test normalization policy in test docstrings

---

## 7. Hard Constraints Verification

| # | Constraint | How satisfied |
|---|-----------|---------------|
| 1 | FastAPI + repo + DI + SQLAlchemy + deterministic | All new code follows existing patterns |
| 2 | No AI/LLM in bridge | Pure arithmetic from metadata diffs |
| 3 | No breaking API changes | Legacy endpoint untouched; new endpoints are additive |
| 4 | Auth behavior unchanged | Same `require_workspace_member` + 401/403/404 semantics |
| 5 | Workspace scoping strict | All queries filtered by workspace_id |
| 6 | Invalid bridge fails closed | Explicit reason codes for all failure paths |
| 7 | Legacy endpoint backward-compatible | `POST /exports/variance-bridge` unchanged |
| 8 | No credentials in code | DSN from env only; no secrets logged |
| 9 | Migration normalization first | S23-0 completed before any feature edits |

---

## 8. Design Corrections Applied

All 7 user corrections are incorporated:

1. **404 not 403 for cross-workspace:** `BRIDGE_RUN_NOT_FOUND` returns 404. 403 only for role/auth.
2. **Directional config_hash:** `run_a_id`/`run_b_id` NOT sorted in hash computation.
3. **Driver extraction from actual artifacts:** Based on `RunSnapshotRow`, `ResultSetRow`, `ScenarioSpecRow` fields that exist in the schema.
4. **`analysis_version` + `config_json` added:** Table includes both for reproducibility and forward compatibility.
5. **Strict identity with zero-magnitude handling:** All-zero magnitudes + nonzero variance = 100% RESIDUAL. Deterministic sort by enum order + abs(impact) tie-break.
6. **CI enforcement:** `MIGRATION_TEST_DSN` required in CI (fail hard, not silent skip).
7. **Frontend CTA links:** Compare CTA on runs and exports pages; no raw UUID entry path.
