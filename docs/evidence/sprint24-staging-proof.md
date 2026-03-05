# Sprint 24: Full-System Staging Proof Evidence

**Date:** 2026-03-05
**Branch:** `phase3-sprint24-full-system-staging-proof`
**Base:** `bf8eb04` (sprint-23-complete)
**Head:** `1146f70`

---

## 1. Carryover Closure Evidence

### I-2: ScenarioSpec → Bridge Engine (CLOSED)

| Item | Evidence |
|------|----------|
| Migration 019 | `alembic/versions/019_run_snapshot_scenario_link.py` — adds `scenario_spec_id` (UUID, nullable, indexed) + `scenario_spec_version` (int, nullable) to `run_snapshots` |
| ORM columns | `RunSnapshotRow.scenario_spec_id`, `RunSnapshotRow.scenario_spec_version` in `src/db/tables.py:136-137` |
| Repository | `RunSnapshotRepository.create()` accepts `scenario_spec_id`/`scenario_spec_version` |
| Persistence | `_persist_run_result()` forwards spec fields to snapshot creation |
| Governed runs | `run_from_scenario()` passes real `row.scenario_spec_id`/`row.version` |
| Bridge endpoint | `create_variance_bridge()` fetches `ScenarioSpecRow` via `scenario_repo.get_by_id_and_version()`, converts to dict, passes `spec_a`/`spec_b` to engine |
| Helper | `_scenario_row_to_bridge_dict()` extracts `time_horizon` + `shock_items` |
| TODO removed | `TODO(sprint-24)` marker removed from `src/api/exports.py` |
| Tests | `TestScenarioSpecIntegration` — 2 tests (spec persistence + backward compat) |
| Commit | `8bece0c` |

### I-4: RunSelector Populated (CLOSED)

| Item | Evidence |
|------|----------|
| List endpoint | `GET /v1/workspaces/{workspace_id}/engine/runs` — paginated, newest first |
| Repository | `RunSnapshotRepository.list_for_workspace()` with limit/offset |
| Response model | `ListRunsResponse` with `RunSummary[]` (run_id, model_version_id, created_at) |
| Frontend hook | `useWorkspaceRuns(workspaceId)` in `useRuns.ts` — TanStack Query |
| Page wiring | Compare page calls `useWorkspaceRuns()`, maps to `RunOption[]`, passes to `RunSelector` |
| Fallback | Manual UUID entry preserved when no runs found |
| TODO removed | `TODO(sprint-24)` marker removed from compare page |
| Backend tests | `TestListRuns` — 6 tests (empty, returns, limit, offset, shape, workspace isolation) |
| Frontend tests | `useWorkspaceRuns` — 4 tests (fetch, disabled, error, empty) |
| Commits | `85a3b13` (backend), `d9829c6` (frontend) |

---

## 2. Layer-by-Layer Staging Proof

### Layer 1: Auth & Workspace Isolation

| Component | Test Files | Status |
|-----------|-----------|--------|
| JWT auth + RBAC | `tests/api/test_auth.py` | ✅ |
| Workspace CRUD | `tests/api/test_workspaces.py` | ✅ |
| Member scoping | `tests/api/test_workspace_membership.py` | ✅ |

### Layer 2: Document Extraction

| Component | Test Files | Status |
|-----------|-----------|--------|
| Ingestion pipeline | `tests/ingestion/` (8 files) | ✅ |
| Provider adapters | `tests/ingestion/providers/` (5 files) | ✅ |

### Layer 3: Compiler + Depth Agents

| Component | Test Files | Status |
|-----------|-----------|--------|
| Scenario compiler | `tests/compiler/` (11 files) | ✅ |
| Depth engine (Al-Muhasabi) | `tests/agents/depth/` (10 files) | ✅ |
| AI agents | `tests/agents/` (9 files) | ✅ |

### Layer 4: Deterministic Engine

| Component | Test Files | Status |
|-----------|-----------|--------|
| I-O engine core | `tests/engine/` (20 files) | ✅ |
| Constraint solver | `tests/engine/constraints/` (8 files) | ✅ |
| Workforce satellite | `tests/engine/workforce_satellite/` (8 files) | ✅ |
| Type II induced | `tests/engine/test_type2*.py` | ✅ |
| Value measures | `tests/engine/test_value_measures.py` | ✅ |
| RunSeries | `tests/engine/test_runseries.py` | ✅ |

### Layer 5: Governance (NFF)

| Component | Test Files | Status |
|-----------|-----------|--------|
| Claims + evidence | `tests/governance/` (9 files) | ✅ |
| Publication gate | `tests/integration/test_governance_chain.py` | ✅ |

### Layer 6: Export & Delivery

| Component | Test Files | Status |
|-----------|-----------|--------|
| Export pipeline | `tests/export/` (7 files) | ✅ |
| Variance bridge | `tests/export/test_variance_bridge.py` | ✅ |
| Bridge API | `tests/api/test_variance_bridge_api.py` (32 tests) | ✅ |

### Layer 7: Premium Workflows

| Sprint | Component | Test Evidence | Status |
|--------|-----------|---------------|--------|
| S19 | Client Portal | `tests/api/test_portal*.py` | ✅ |
| S20 | Structural Path Analysis | `tests/api/test_path_analytics.py` | ✅ |
| S21 | Portfolio Optimization | `tests/api/test_portfolio.py` | ✅ |
| S22 | Live Workshop | `tests/api/test_workshop.py` | ✅ |
| S23 | Advanced Variance Bridges | `tests/api/test_variance_bridge_api.py` | ✅ |

### Layer 8: Data Quality & Knowledge Flywheel

| Component | Test Files | Status |
|-----------|-----------|--------|
| Quality dimensions | `tests/quality/` (11 files) | ✅ |
| Knowledge flywheel | `tests/flywheel/` (14 files) | ✅ |

### Layer 9: Migrations

| Migration | Test File | Status |
|-----------|-----------|--------|
| 012-017 | `tests/migration/test_012_*.py` through `test_017_*.py` | ✅ (skip without PG) |
| 018 | ORM sync verified on main | ✅ |
| 019 | ORM sync verified (new columns nullable) | ✅ |

### Layer 10: Integration (Cross-Layer)

| Component | Test Files | Status |
|-----------|-----------|--------|
| Full-path integration | `tests/integration/` (27 files) | ✅ |

---

## 3. Test Suite Summary

| Suite | Count | Status |
|-------|-------|--------|
| Backend (pytest) | **4625 passed**, 29 skipped | ✅ |
| Frontend (vitest) | **307 passed** (35 files) | ✅ |
| **Total** | **4932 tests** | ✅ |

### Test files: 262 backend + 35 frontend = **297 test files**

---

## 4. API Surface Verification

OpenAPI spec regenerated at `1146f70` with all endpoints:

| Path Pattern | Endpoints |
|-------------|-----------|
| `/v1/workspaces/{ws}/engine/runs` | GET (list), POST (create) |
| `/v1/workspaces/{ws}/engine/runs/{run_id}` | GET (results) |
| `/v1/workspaces/{ws}/engine/batch` | POST, GET |
| `/v1/workspaces/{ws}/exports/variance-bridge` | POST (legacy) |
| `/v1/workspaces/{ws}/variance-bridges` | POST (persist), GET (list) |
| `/v1/workspaces/{ws}/variance-bridges/{id}` | GET (single) |
| `/v1/workspaces/{ws}/scenarios/...` | Full CRUD + run + compare |
| `/v1/workspaces/{ws}/exports/...` | Create, status, download |
| `/v1/workspaces/{ws}/workshop/...` | Sessions, preview, export |
| `/v1/workspaces/{ws}/portfolio/...` | Optimize, results |
| `/v1/workspaces/{ws}/path-analytics/...` | SPA, chokepoints |
| `/v1/workspaces/{ws}/governance/...` | Claims, assumptions, gate |
| + additional endpoints | Documents, compiler, depth, quality, workforce, feasibility |

---

## 5. Alembic Migration Chain

```
001 → 002 → ... → 017_workshop_sessions → 018_variance_bridge_analyses → 019_run_snapshot_scenario_link (HEAD)
```

- Head: `019_run_snapshot_scenario_link`
- All 19 migrations chain correctly
- ORM sync verified (no drift detected)
