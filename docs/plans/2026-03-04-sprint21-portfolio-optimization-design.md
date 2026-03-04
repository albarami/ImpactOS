# Sprint 21 Design: Portfolio Optimization (MVP-21)

Date: 2026-03-04
Status: Approved
Sprint: 21 (Phase 3 Premium Boardroom)

## Overview

Deterministic binary portfolio optimization over candidate scenario runs.
Given a set of completed runs, select the optimal 0/1 subset that maximizes
a chosen objective metric under budget and cap constraints.

Pure deterministic engine — no LLM, no external solver dependencies.

## Engine: `src/engine/portfolio_optimizer.py`

### Solver

Exact binary knapsack via branch-and-bound or full enumeration.
No greedy fallback. No external MILP dependency.

- **Candidate limit:** max 25. Exceeding fails closed with `PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED`.
- **Minimum selection:** at least 1 run must be selected (`min_selected` defaults to 1).
  The empty set is never a valid solution.

### Inputs

```python
@dataclass(frozen=True)
class CandidateRun:
    run_id: UUID
    objective_value: float   # extracted from ResultSet by objective_metric
    cost: float              # extracted from ResultSet by cost_metric
    group_key: str | None    # optional grouping for per-group caps

candidates: list[CandidateRun]  # pre-validated, unique run_ids
budget: float                    # total cost cap (required, > 0)
min_selected: int                # minimum selections (default 1, >= 1)
max_selected: int | None         # optional cap on number of selected runs
group_caps: dict[str, int] | None  # optional {group_key: max_count}
```

### Metric Source

Both `objective_value` and `cost` are extracted from ResultSet rows for each
candidate run_id. The caller specifies:

- `objective_metric`: str — the `metric_type` to maximize (e.g., "gdp_at_market_price")
- `cost_metric`: str — the `metric_type` used as cost (e.g., "total_investment")

For each candidate run, the API layer queries ResultSet for both metric_types.
If either metric is missing for any candidate, fail closed with
`PORTFOLIO_METRIC_NOT_FOUND`.

### Solver Logic

1. Validate inputs (non-empty, no duplicates, positive budget, sane caps)
2. Sort candidates by `run_id` ASC for deterministic traversal
3. Enumerate/branch-and-bound all feasible subsets where:
   - total cost <= budget
   - count >= min_selected
   - count <= max_selected (if set)
   - per-group counts <= group_caps (if set)
4. Select subset maximizing total `objective_value`
5. **Tie-break:** among equal-objective subsets, select the one whose sorted
   `run_id` list is lexicographically smallest (UUID string comparison)

### Outputs

```python
@dataclass(frozen=True)
class PortfolioResult:
    selected_run_ids: list[UUID]    # sorted ASC
    total_objective: float
    total_cost: float
    solver_method: str              # "exact_binary_knapsack_v1"
    candidates_evaluated: int
    feasible_count: int
```

### Error Taxonomy

```python
class PortfolioError(Exception): ...

class PortfolioConfigError(PortfolioError):
    reason_code: str  # PORTFOLIO_INVALID_CONFIG | PORTFOLIO_NO_CANDIDATES
                      # | PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED
                      # | PORTFOLIO_DUPLICATE_CANDIDATES

class PortfolioInfeasibleError(PortfolioError):
    reason_code: str  # PORTFOLIO_INFEASIBLE
```

## Fail-Closed Validation (API Layer, Before Solver)

Checked in order, first failure wins:

1. **Auth/workspace** — existing auth gate (401/403)
2. **Duplicate candidates** — candidate_run_ids must be unique (422 PORTFOLIO_DUPLICATE_CANDIDATES)
3. **Run existence** — all candidate run_ids must exist in workspace (404 PORTFOLIO_RUN_NOT_FOUND)
4. **Model compatibility** — all candidates share same `model_version_id` (422 PORTFOLIO_MODEL_MISMATCH)
5. **Metric availability** — both objective_metric and cost_metric ResultSets exist for every candidate (422 PORTFOLIO_METRIC_NOT_FOUND)
6. **Config sanity** — budget > 0, min_selected >= 1, max_selected > 0 if provided, group caps > 0 (422 PORTFOLIO_INVALID_CONFIG)
7. **Candidate limit** — len(candidates) <= 25 (422 PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED)

## Models: `src/models/portfolio.py`

Pydantic v2 schemas:

- `PortfolioConfig` — objective_metric, cost_metric, candidate_run_ids, budget,
  min_selected (default 1), max_selected?, group_caps?
- `CandidateItem` — run_id, objective_value, cost, group_key?, selected (bool)
- `PortfolioOptimizationResponse` — portfolio_id, workspace_id, model_version_id,
  config, selected_run_ids, total_objective, total_cost, solver_method,
  candidates_evaluated, feasible_count, optimization_version, created_at
- `PortfolioListResponse` — items, total, limit, offset

## Persistence: Migration 016 + Repository

### Table: `portfolio_optimizations`

| Column | Type | Notes |
|--------|------|-------|
| portfolio_id | UUID PK | |
| workspace_id | UUID FK | workspaces.workspace_id |
| model_version_id | UUID | shared model version across all candidates |
| optimization_version | String(20) | e.g., "portfolio_v1" |
| config_json | JSONB | full config including metrics + caps |
| config_hash | String(71) | SHA-256 of canonical config |
| objective_metric | String(50) | metric_type maximized |
| cost_metric | String(50) | metric_type used as cost |
| budget | Float | total cost cap |
| min_selected | Integer | minimum selections |
| max_selected | Integer NULL | optional cap |
| candidate_run_ids_json | JSONB | canonical sorted list of UUIDs |
| selected_run_ids_json | JSONB | solver output (sorted) |
| result_json | JSONB | full PortfolioResult serialization |
| result_checksum | String(71) | SHA-256 of result_json + optimization_version |
| created_at | DateTime | UTC |

**Constraints:**
- UNIQUE on `(workspace_id, config_hash)` — idempotency key
- Composite index on `(workspace_id, created_at DESC)`

### config_hash Computation

SHA-256 of canonical JSON containing (all fields, sorted keys):
- sorted candidate_run_ids (as strings)
- objective_metric
- cost_metric
- budget
- min_selected
- max_selected (null if not set)
- group_caps (sorted keys, null if not set)
- optimization_version

### Idempotency: Race-Safe

1. Compute config_hash from request
2. SELECT existing row by (workspace_id, config_hash)
3. If found → return 200 with existing result
4. If not found → solve, INSERT with ON CONFLICT (workspace_id, config_hash) DO NOTHING
5. If INSERT returned 0 rows (concurrent race) → SELECT again and return 200

### Repository: `PortfolioRepository`

5 methods mirroring PathAnalysisRepository:
- `create(...)` → PortfolioOptimizationRow
- `get(portfolio_id)` → Row | None
- `get_for_workspace(portfolio_id, workspace_id)` → Row | None
- `get_by_config_for_workspace(workspace_id, config_hash)` → Row | None
- `list_for_workspace(workspace_id, *, limit, offset)` → (list[Row], total)

## API: `src/api/portfolio.py`

3 workspace-scoped endpoints:

- `POST /v1/workspaces/{workspace_id}/portfolio/optimize` — 201 new / 200 idempotent
- `GET  /v1/workspaces/{workspace_id}/portfolio/{portfolio_id}` — 200 / 404
- `GET  /v1/workspaces/{workspace_id}/portfolio` — paginated list (limit/offset)

### Reason Code Matrix

| Condition | HTTP | Reason Code |
|-----------|------|-------------|
| Invalid config (budget <= 0, etc.) | 422 | PORTFOLIO_INVALID_CONFIG |
| Empty candidate list | 422 | PORTFOLIO_NO_CANDIDATES |
| Duplicate candidate run_ids | 422 | PORTFOLIO_DUPLICATE_CANDIDATES |
| Too many candidates (> 25) | 422 | PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED |
| Candidate run_id not found in workspace | 404 | PORTFOLIO_RUN_NOT_FOUND |
| Candidates have different model_version_id | 422 | PORTFOLIO_MODEL_MISMATCH |
| Metric not found for candidate | 422 | PORTFOLIO_METRIC_NOT_FOUND |
| No feasible subset under constraints | 422 | PORTFOLIO_INFEASIBLE |
| Portfolio result not found | 404 | PORTFOLIO_NOT_FOUND |
| Auth failure | 401/403 | (existing auth codes) |

## Testing

### Engine tests (`tests/engine/test_portfolio_optimizer.py`)
- Happy path: deterministic optimal portfolio
- Tie-break determinism: same objective → lexicographic run_id ASC
- min_selected enforced (empty set rejected)
- Infeasible request → explicit reason code
- Candidate limit exceeded → explicit reason code
- Duplicate candidates → explicit reason code
- group_caps enforcement

### Repository tests (`tests/repositories/test_portfolio.py`)
- Create/get/list round-trip
- Workspace isolation
- Idempotent replay (same config_hash returns existing)
- Pagination

### API tests (`tests/api/test_portfolio.py`)
- Happy path 201 + idempotent 200
- All fail-closed paths with expected HTTP + reason codes
- Auth/workspace boundary
- Model mismatch detection
- Metric not found detection

### Migration tests (`tests/migration/test_016_portfolio_optimization_postgres.py`)
- Table creation, unique constraint, downgrade, re-upgrade
