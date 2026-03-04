# Sprint 21: Portfolio Optimization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deterministic binary portfolio optimization engine with workspace-scoped API, persistence, and idempotency.

**Architecture:** Exact binary knapsack solver (branch-and-bound / enumeration, max 25 candidates), fail-closed validation, workspace-scoped persistence with `(workspace_id, config_hash)` idempotency, 3 REST endpoints mirroring Sprint 20 path_analytics pattern.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, NumPy (optional), pytest

---

## Task 1: Pydantic Models + Domain Errors

**Files:**
- Create: `src/models/portfolio.py`
- Create: `src/engine/portfolio_optimizer.py` (error classes only)

**Step 1: Write `src/models/portfolio.py`**

7 Pydantic v2 models:

```python
"""Portfolio optimization Pydantic v2 schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PortfolioConfig(BaseModel):
    objective_metric: str = Field(..., min_length=1, max_length=50)
    cost_metric: str = Field(..., min_length=1, max_length=50)
    candidate_run_ids: list[UUID] = Field(..., min_length=1)
    budget: float = Field(..., gt=0)
    min_selected: int = Field(default=1, ge=1)
    max_selected: int | None = Field(default=None, ge=1)
    group_caps: dict[str, int] | None = None


class CandidateItem(BaseModel):
    run_id: UUID
    objective_value: float
    cost: float
    group_key: str | None = None
    selected: bool


class PortfolioOptimizationResponse(BaseModel):
    portfolio_id: str
    workspace_id: str
    model_version_id: str
    config: PortfolioConfig
    selected_run_ids: list[str]
    total_objective: float
    total_cost: float
    solver_method: str
    candidates_evaluated: int
    feasible_count: int
    optimization_version: str
    result_checksum: str
    created_at: datetime


class PortfolioListResponse(BaseModel):
    items: list[PortfolioOptimizationResponse]
    total: int
    limit: int
    offset: int


class CreatePortfolioRequest(BaseModel):
    """Public request schema for POST endpoint."""
    objective_metric: str
    cost_metric: str
    candidate_run_ids: list[str]
    budget: float
    min_selected: int = 1
    max_selected: int | None = None
    group_caps: dict[str, int] | None = None
```

**Step 2: Write domain errors in `src/engine/portfolio_optimizer.py`**

```python
"""Portfolio optimization engine — deterministic binary knapsack.

Pure deterministic solver. No LLM calls, no external solver dependencies.
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base for all portfolio optimization domain errors."""


class PortfolioConfigError(PortfolioError):
    """Invalid portfolio optimization configuration."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INVALID_CONFIG") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


class PortfolioInfeasibleError(PortfolioError):
    """No feasible subset exists under given constraints."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INFEASIBLE") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)
```

**Step 3: Commit**

```bash
git add src/models/portfolio.py src/engine/portfolio_optimizer.py
git commit -m "[sprint21] add pydantic models and domain errors for portfolio optimization"
```

---

## Task 2: Deterministic Portfolio Optimizer Engine (TDD)

**Files:**
- Create: `tests/engine/test_portfolio_optimizer.py`
- Modify: `src/engine/portfolio_optimizer.py`

**Step 1: Write failing tests**

Tests to write (all in `tests/engine/test_portfolio_optimizer.py`):

1. `test_happy_path_selects_optimal` — 3 candidates, budget allows 2, verify optimal pair selected
2. `test_single_candidate_selected` — 1 candidate within budget, selected
3. `test_tiebreak_lexicographic_run_id` — 2 subsets with equal objective, verify run_id ASC wins
4. `test_min_selected_enforced` — min_selected=2 but only 1 fits budget → PORTFOLIO_INFEASIBLE
5. `test_max_selected_enforced` — max_selected=1 limits selection even if more fit budget
6. `test_group_caps_enforced` — group cap limits per-group selections
7. `test_infeasible_no_subset_fits_budget` — all candidates exceed budget → PORTFOLIO_INFEASIBLE
8. `test_empty_candidates_rejected` — empty list → PORTFOLIO_NO_CANDIDATES
9. `test_duplicate_candidates_rejected` — repeated run_id → PORTFOLIO_DUPLICATE_CANDIDATES
10. `test_candidate_limit_exceeded` — 26 candidates → PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED
11. `test_invalid_budget_rejected` — budget=0 → PORTFOLIO_INVALID_CONFIG
12. `test_invalid_max_selected_rejected` — max_selected=0 → PORTFOLIO_INVALID_CONFIG
13. `test_solver_method_reported` — result.solver_method == "exact_binary_knapsack_v1"
14. `test_selected_run_ids_sorted_asc` — output always sorted
15. `test_feasible_count_reported` — feasible_count matches actual feasible subsets

Key dataclass for engine input:
```python
@dataclass(frozen=True)
class CandidateRun:
    run_id: UUID
    objective_value: float
    cost: float
    group_key: str | None = None
```

Function signature:
```python
def optimize_portfolio(
    candidates: list[CandidateRun],
    budget: float,
    *,
    min_selected: int = 1,
    max_selected: int | None = None,
    group_caps: dict[str, int] | None = None,
) -> PortfolioResult:
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/engine/test_portfolio_optimizer.py -q
```

Expected: FAIL (function not implemented)

**Step 3: Implement `optimize_portfolio` in `src/engine/portfolio_optimizer.py`**

Implementation approach:
1. Validate inputs (duplicates, empty, limit, budget, caps)
2. Sort candidates by `run_id` ASC
3. If n <= 25: enumerate all 2^n subsets via itertools or recursive branch-and-bound
4. Filter feasible subsets (budget, min/max selected, group caps)
5. Select max objective; tie-break by lexicographic sorted run_ids
6. Return frozen `PortfolioResult`

`PortfolioResult` dataclass:
```python
@dataclass(frozen=True)
class PortfolioResult:
    selected_run_ids: list[UUID]
    total_objective: float
    total_cost: float
    solver_method: str
    candidates_evaluated: int
    feasible_count: int
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/engine/test_portfolio_optimizer.py -q
```

Expected: all PASS

**Step 5: Commit**

```bash
git add src/engine/portfolio_optimizer.py tests/engine/test_portfolio_optimizer.py
git commit -m "[sprint21] implement deterministic portfolio optimization engine"
```

---

## Task 3: Migration 016 + ORM Row

**Files:**
- Create: `alembic/versions/016_portfolio_optimizations.py`
- Modify: `src/db/tables.py` (add PortfolioOptimizationRow)
- Modify: `alembic/env.py` (add migration-managed constraints/indexes)
- Create: `tests/migration/test_016_portfolio_optimization_postgres.py`

**Step 1: Write migration `016_portfolio_optimizations.py`**

Table: `portfolio_optimizations`, 16 columns:
- portfolio_id (UUID PK)
- workspace_id (UUID FK → workspaces)
- model_version_id (UUID, NOT NULL)
- optimization_version (String(20), NOT NULL)
- config_json (FlexJSON, NOT NULL)
- config_hash (String(71), NOT NULL)
- objective_metric (String(50), NOT NULL)
- cost_metric (String(50), NOT NULL)
- budget (Float, NOT NULL)
- min_selected (Integer, NOT NULL)
- max_selected (Integer, nullable)
- candidate_run_ids_json (FlexJSON, NOT NULL)
- selected_run_ids_json (FlexJSON, NOT NULL)
- result_json (FlexJSON, NOT NULL)
- result_checksum (String(71), NOT NULL)
- created_at (DateTime, NOT NULL)

Constraints:
- UNIQUE `(workspace_id, config_hash)` named `uq_portfolio_optimizations_ws_config`
- Composite index `(workspace_id, created_at DESC)` named `ix_portfolio_optimizations_ws_created`

Revision: `016_portfolio_optimizations`, down_revision: `015_path_analyses`

**Step 2: Add `PortfolioOptimizationRow` to `src/db/tables.py`**

Follow PathAnalysisRow pattern. 16 columns matching migration.

**Step 3: Update `alembic/env.py`**

Add to `_MIGRATION_MANAGED_INDEXES`:
- `ix_portfolio_optimizations_ws_created`

Add to `_MIGRATION_MANAGED_CONSTRAINTS`:
- `uq_portfolio_optimizations_ws_config`

**Step 4: Write migration tests**

`tests/migration/test_016_portfolio_optimization_postgres.py` — 4 tests:
1. `test_upgrade_creates_table` — table exists after upgrade
2. `test_unique_constraint` — duplicate (workspace_id, config_hash) raises IntegrityError
3. `test_downgrade_removes_table` — table gone after downgrade to `015_path_analyses`
4. `test_re_upgrade` — clean re-upgrade after downgrade

Use explicit revision target `015_path_analyses` for downgrade (not `-1`).

**Step 5: Run migration tests**

```bash
python -m pytest tests/migration/test_016_portfolio_optimization_postgres.py -q
```

**Step 6: Commit**

```bash
git add alembic/versions/016_portfolio_optimizations.py src/db/tables.py alembic/env.py tests/migration/test_016_portfolio_optimization_postgres.py
git commit -m "[sprint21] add migration 016 portfolio_optimizations table + ORM row"
```

---

## Task 4: Portfolio Repository (TDD)

**Files:**
- Create: `src/repositories/portfolio.py`
- Create: `tests/repositories/test_portfolio.py`
- Modify: `src/api/dependencies.py` (add DI factory)

**Step 1: Write failing tests**

`tests/repositories/test_portfolio.py` — 10 tests (x2 backends):
1. `test_create_and_get` — round-trip
2. `test_get_returns_none_for_missing` — unknown ID returns None
3. `test_get_for_workspace_hit` — correct workspace returns row
4. `test_get_for_workspace_wrong_workspace` — cross-workspace returns None
5. `test_get_by_config_for_workspace_hit` — config_hash match
6. `test_get_by_config_for_workspace_miss` — config_hash miss
7. `test_list_for_workspace_multiple` — multiple results
8. `test_list_for_workspace_pagination` — limit/offset
9. `test_list_for_workspace_isolation` — cross-workspace isolation
10. `test_idempotent_config_hash` — same config_hash returns existing row

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/repositories/test_portfolio.py -q
```

**Step 3: Implement `PortfolioRepository`**

5 methods mirroring PathAnalysisRepository:
- `create(**kwargs)` → PortfolioOptimizationRow
- `get(portfolio_id)` → Row | None
- `get_for_workspace(portfolio_id, workspace_id)` → Row | None
- `get_by_config_for_workspace(workspace_id, config_hash)` → Row | None
- `list_for_workspace(workspace_id, *, limit, offset)` → (list[Row], total)

**Step 4: Add DI factory to `src/api/dependencies.py`**

```python
from src.repositories.portfolio import PortfolioRepository

async def get_portfolio_repo(
    session: AsyncSession = Depends(get_async_session),
) -> PortfolioRepository:
    return PortfolioRepository(session)
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/repositories/test_portfolio.py -q
```

**Step 6: Commit**

```bash
git add src/repositories/portfolio.py tests/repositories/test_portfolio.py src/api/dependencies.py
git commit -m "[sprint21] add portfolio repository with workspace scoping"
```

---

## Task 5: API Endpoints + Wiring (TDD)

**Files:**
- Create: `src/api/portfolio.py`
- Create: `tests/api/test_portfolio.py`
- Modify: `src/api/main.py` (mount router)

**Step 1: Write failing tests**

`tests/api/test_portfolio.py` — ~20 tests (x2 backends):

Happy paths:
1. `test_post_creates_201` — valid request returns 201
2. `test_post_idempotent_200` — same config returns 200 with same portfolio_id
3. `test_get_by_id_200` — GET returns created portfolio
4. `test_list_200` — list returns paginated results
5. `test_list_pagination` — limit/offset work correctly

Error precedence (first failure wins):
6. `test_post_no_candidates_422` — empty list → PORTFOLIO_NO_CANDIDATES
7. `test_post_duplicate_candidates_422` — repeated run_id → PORTFOLIO_DUPLICATE_CANDIDATES
8. `test_post_run_not_found_404` — unknown run_id → PORTFOLIO_RUN_NOT_FOUND
9. `test_post_model_mismatch_422` — different model_versions → PORTFOLIO_MODEL_MISMATCH
10. `test_post_metric_not_found_422` — missing ResultSet → PORTFOLIO_METRIC_NOT_FOUND
11. `test_post_invalid_budget_422` — budget <= 0 → PORTFOLIO_INVALID_CONFIG
12. `test_post_candidate_limit_422` — > 25 candidates → PORTFOLIO_CANDIDATE_LIMIT_EXCEEDED
13. `test_post_infeasible_422` — no feasible subset → PORTFOLIO_INFEASIBLE

Workspace isolation:
14. `test_get_wrong_workspace_404` — cross-workspace GET returns 404
15. `test_list_workspace_isolation` — list only returns own workspace

Auth:
16. `test_unauthenticated_401` — no token returns 401
17. `test_nonmember_403` — wrong workspace returns 403/404

Response content:
18. `test_response_contains_model_version_id` — model_version_id in response
19. `test_response_contains_solver_method` — solver_method in response
20. `test_response_selected_run_ids_sorted` — selected_run_ids sorted ASC

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/api/test_portfolio.py -q
```

**Step 3: Implement `src/api/portfolio.py`**

3 endpoints with `_RawConfig` pattern for explicit error codes:
- POST: validate → check idempotency → extract metrics → solve → persist → 201/200
- GET by ID: workspace-scoped lookup → 200/404
- GET list: paginated workspace-scoped query

Helpers:
- `_config_hash(config, optimization_version)` — SHA-256 of canonical JSON
- `_result_checksum(result_json, optimization_version)` — SHA-256
- `_row_to_response(row)` — ORM → Pydantic

`OPTIMIZATION_VERSION = "portfolio_v1"`

**Step 4: Mount router in `src/api/main.py`**

```python
from src.api.portfolio import router as portfolio_router
app.include_router(portfolio_router)
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/api/test_portfolio.py -q
```

**Step 6: Commit**

```bash
git add src/api/portfolio.py tests/api/test_portfolio.py src/api/main.py
git commit -m "[sprint21] expose workspace-scoped portfolio optimization api"
```

---

## Task 6: Verification + Docs + OpenAPI

**Files:**
- Modify: `openapi.json` (regenerate)
- Modify: `docs/evidence/release-readiness-checklist.md`
- Modify: `docs/ImpactOS_Master_Build_Plan_v2.md`
- Modify: `docs/plans/2026-03-03-full-system-completion-master-plan.md`

**Step 1: Run full verification suite**

```bash
python -m pytest tests/engine/test_portfolio_optimizer.py tests/repositories/test_portfolio.py tests/api/test_portfolio.py tests/migration/test_016_portfolio_optimization_postgres.py -q
python -m pytest tests -q
python -m alembic current
python -m alembic heads
python -m alembic check
python -m ruff check --select I001,F401,F841,B905 src/engine/portfolio_optimizer.py src/models/portfolio.py src/repositories/portfolio.py src/api/portfolio.py
python -m ruff format --check src/engine/portfolio_optimizer.py src/models/portfolio.py src/repositories/portfolio.py src/api/portfolio.py tests/engine/test_portfolio_optimizer.py tests/repositories/test_portfolio.py tests/api/test_portfolio.py tests/migration/test_016_portfolio_optimization_postgres.py
```

**Step 2: Regenerate OpenAPI**

```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```

**Step 3: Update release checklist and tracker docs**

Add Sprint 21 section to `docs/evidence/release-readiness-checklist.md`.
Update MVP-21 row in `docs/ImpactOS_Master_Build_Plan_v2.md`.
Update `docs/plans/2026-03-03-full-system-completion-master-plan.md` — mark Sprint 21 done.

**Step 4: Lint/format fix any issues in Sprint 21 files**

**Step 5: Commit**

```bash
git add openapi.json docs/evidence/release-readiness-checklist.md docs/ImpactOS_Master_Build_Plan_v2.md docs/plans/2026-03-03-full-system-completion-master-plan.md
git commit -m "[sprint21] refresh sprint21 evidence and openapi"
```

---

## Task 7: Code Review + Push + PR

**Step 1: Request code review using `superpowers:requesting-code-review`**

Two-stage review:
1. Spec compliance: design doc vs implementation
2. Code quality: patterns, edge cases, naming

**Step 2: Apply review findings using `superpowers:receiving-code-review`**

**Step 3: Push and open PR using `superpowers:finishing-a-development-branch`**

```bash
git push origin phase3-sprint21-portfolio-optimization
gh pr create --base main --head phase3-sprint21-portfolio-optimization --title "Sprint 21: MVP-21 Portfolio Optimization"
```

Do NOT merge. PR must be review-ready.
