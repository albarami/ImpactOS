# Sprint 20: Structural Path Analysis + Chokepoint Analytics — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add deterministic on-demand Structural Path Analysis (power series A^k decomposition) and Rasmussen chokepoint analytics as workspace-scoped, run-linked, idempotent endpoints.

**Architecture:** New engine module (`structural_path.py`) computes SPA/chokepoints from LoadedModel matrices. Results persist in `path_analyses` table keyed by `(run_id, config_hash)` for idempotency. Three additive API endpoints (POST compute, GET by ID, GET list) mounted under `/v1/workspaces/{workspace_id}/path-analytics`. Fully additive — no changes to existing endpoints.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, NumPy/SciPy, SQLAlchemy async, Alembic, pytest-asyncio

**Design doc:** `docs/plans/2026-03-04-sprint20-structural-path-analytics-design.md`

**Baseline:** `sprint-19-complete` — 4,347 passed, 4 skipped, 0 failed

---

## Task 1: Pydantic Models + Engine Domain Errors

Schema-first per CLAUDE.md. Define all data structures before any service logic.

**Files:**
- Create: `src/models/path.py`
- Create: `src/engine/structural_path.py` (domain errors only, no math yet)

**Spec:**

Create `src/models/path.py` with these Pydantic v2 models:

```python
from pydantic import Field
from uuid import UUID
from src.models.base import ImpactOSBase

class PathAnalysisConfig(ImpactOSBase):
    """Typed config for SPA computation. Validated bounds, stable OpenAPI."""
    max_depth: int = Field(default=6, ge=0, le=12)
    top_k: int = Field(default=20, ge=1, le=100)

class PathContributionItem(ImpactOSBase):
    source_sector_code: str    # j — final demand target
    target_sector_code: str    # i — affected sector
    depth: int                 # k — hop count (0=direct)
    coefficient: float         # (A^k)[i,j] pure
    contribution: float        # (A^k)[i,j] × delta_d[j]

class DepthContributionItem(ImpactOSBase):
    signed: float              # net contribution at this depth
    absolute: float            # sum of |values| at this depth

class ChokePointItem(ImpactOSBase):
    sector_code: str
    forward_linkage: float     # raw row sum of B
    backward_linkage: float    # raw column sum of B
    norm_forward: float        # divided by mean(forward)
    norm_backward: float       # divided by mean(backward)
    chokepoint_score: float    # sqrt(nf × nb)
    is_chokepoint: bool        # both normalized > 1.0

class CreatePathAnalysisRequest(ImpactOSBase):
    run_id: UUID
    config: PathAnalysisConfig = Field(default_factory=PathAnalysisConfig)

class PathAnalysisResponse(ImpactOSBase):
    analysis_id: UUID
    run_id: UUID
    analysis_version: str
    config: PathAnalysisConfig
    config_hash: str
    top_paths: list[PathContributionItem]
    chokepoints: list[ChokePointItem]
    depth_contributions: dict[str, DepthContributionItem]  # str(k) → item
    coverage_ratio: float
    result_checksum: str
    created_at: str

class PathAnalysisListResponse(ImpactOSBase):
    items: list[PathAnalysisResponse]
    total: int
```

Create `src/engine/structural_path.py` with domain errors only (no math yet):

```python
"""Structural Path Analysis — domain errors.

Math implementation added in Task 2.
"""

class SPAError(Exception):
    """Base for all SPA domain errors."""

class SPAConfigError(SPAError):
    """Invalid SPA configuration (max_depth/top_k out of bounds)."""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

class SPADimensionError(SPAError):
    """Matrix/vector dimension mismatch."""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
```

**Verify:** `python -c "from src.models.path import PathAnalysisConfig, CreatePathAnalysisRequest, PathAnalysisResponse; print('OK')"` and `python -c "from src.engine.structural_path import SPAConfigError, SPADimensionError; print('OK')"`

**Commit:** `[sprint20] add pydantic models and domain errors for path analytics`

---

## Task 2: SPA Decomposition Engine (TDD)

Implement the deterministic power series engine. All math, no persistence/API.

**Files:**
- Modify: `src/engine/structural_path.py` (add compute_spa + dataclasses)
- Create: `tests/engine/test_structural_path.py`

**Spec:**

Add frozen dataclasses and `compute_spa()` to `src/engine/structural_path.py`:

```python
from dataclasses import dataclass
import numpy as np
from numpy.linalg import norm as frobenius_norm

@dataclass(frozen=True)
class PathContribution:
    source_sector: int          # j
    source_sector_code: str
    target_sector: int          # i
    target_sector_code: str
    depth: int                  # k (0=direct)
    coefficient: float          # (A^k)[i,j]
    contribution: float         # (A^k)[i,j] × delta_d[j]

@dataclass(frozen=True)
class DepthContrib:
    signed: float
    absolute: float

@dataclass(frozen=True)
class ChokePointScore:
    sector_index: int
    sector_code: str
    forward_linkage: float
    backward_linkage: float
    norm_forward: float
    norm_backward: float
    chokepoint_score: float
    is_chokepoint: bool

@dataclass(frozen=True)
class SPAResult:
    top_paths: list[PathContribution]
    chokepoints: list[ChokePointScore]
    depth_contributions: dict[int, DepthContrib]
    coverage_ratio: float       # Frobenius-norm, [0,1]
    max_depth: int
    top_k: int


def compute_spa(
    A: np.ndarray,
    B: np.ndarray,
    delta_d: np.ndarray,
    sector_codes: list[str],
    *,
    max_depth: int = 6,
    top_k: int = 20,
) -> SPAResult:
    """Deterministic Structural Path Analysis via power series decomposition.

    Math:
        B_hat = Σ(A^k, k=0..max_depth)
        contribution[k][i][j] = (A^k)[i,j] × delta_d[j]
        coverage = 1 - ||B - B_hat||_F / ||B||_F  (clipped to [0,1])

    Chokepoints (Rasmussen convention):
        backward_linkage[j] = Σ_i B[i,j]  (column sum)
        forward_linkage[i] = Σ_j B[i,j]   (row sum)
        chokepoint_score = sqrt(norm_fwd × norm_bwd)
    """
```

Implementation requirements:
1. Validate inputs: A must be (n,n), B must be (n,n), delta_d must be (n,), sector_codes length must be n. Raise `SPADimensionError` on mismatch.
2. Validate config: max_depth ∈ [0,12], top_k ∈ [1,100]. Raise `SPAConfigError` on violation.
3. Power series: compute A^k iteratively (`A_k = A_prev @ A`). Start with A^0 = I (eye(n)).
4. For each depth k, compute contribution matrix `C_k = A_k * delta_d[np.newaxis, :]` (broadcast).
5. Accumulate B_hat = sum of all A^k.
6. Coverage ratio: `max(0.0, min(1.0, 1.0 - frobenius_norm(B - B_hat) / frobenius_norm(B)))`. Handle `frobenius_norm(B) == 0` → coverage = 1.0.
7. Collect all (i,j,k) tuples with contribution, sort by `(|contribution| DESC, k ASC, i ASC, j ASC)`, take top_k.
8. Depth contributions: for each k, signed = sum of all contributions at that depth, absolute = sum of |contributions|.
9. Chokepoints: compute forward/backward linkage from B, normalize by mean, compute score, flag, rank by score desc then index asc, take top_k.
10. Return SPAResult.

**Tests** (`tests/engine/test_structural_path.py`) — ~15 tests:

Use a 2×2 toy model fixture:
```python
# A = [[0.2, 0.3], [0.1, 0.4]]
# B = (I-A)^-1 (computed by hand or numpy)
# delta_d = [100.0, 0.0]  (shock to sector 0 only)
# sector_codes = ["S1", "S2"]
```

And a 3×3 model fixture for chokepoint tests.

Tests to write:
1. `test_2x2_depth_0_direct_only` — max_depth=0 gives identity contributions only
2. `test_2x2_depth_1_first_round` — max_depth=1 captures direct + first indirect
3. `test_2x2_full_depth_coverage_high` — max_depth=10 gives coverage_ratio > 0.99
4. `test_scalar_identity` — sum of signed depth contributions ≈ sum(B @ delta_d)
5. `test_vector_identity` — reconstruct per-sector vector from paths, compare to B @ delta_d componentwise
6. `test_top_k_ranking_deterministic` — tie-break is (k ASC, i ASC, j ASC)
7. `test_top_k_limits_output` — len(top_paths) <= top_k
8. `test_zero_shock` — all contributions zero, top_paths empty
9. `test_depth_contributions_signed_and_absolute` — both fields present and correct
10. `test_chokepoint_forward_backward_linkage` — hand-verified on 3×3 model
11. `test_chokepoint_score_formula` — sqrt(nf × nb) verified
12. `test_chokepoint_flag_both_above_one` — is_chokepoint only when both > 1.0
13. `test_single_sector_degenerate` — n=1, A=[[a]], B=[[1/(1-a)]], handles correctly
14. `test_dimension_mismatch_raises` — wrong shapes raise SPADimensionError
15. `test_config_out_of_bounds_raises` — max_depth=13 or top_k=0 raises SPAConfigError

Key identities to verify:
- `sum(depth_contributions[k].signed for k in range(max_depth+1))` ≈ `np.sum(B @ delta_d)` within 1e-10
- Per-sector reconstruction: for each target sector i, sum contributions where target=i ≈ (B @ delta_d)[i] within 1e-10
- `coverage_ratio` is strictly ∈ [0, 1]
- `len(top_paths) <= top_k`
- PathContribution includes correct sector codes from sector_codes list

**Run:** `python -m pytest tests/engine/test_structural_path.py -v`

**Then full suite:** `python -m pytest -q` — expect 4347 + ~15 = ~4362

**Commit:** `[sprint20] implement deterministic structural path decomposition engine`

---

## Task 3: Migration 015 + ORM PathAnalysisRow

Add the `path_analyses` table. Purely additive DB layer.

**Files:**
- Create: `alembic/versions/015_path_analyses.py`
- Modify: `src/db/tables.py` (add PathAnalysisRow)
- Create: `tests/migration/test_015_path_analyses_postgres.py`

**Spec:**

Migration `015_path_analyses`:
- `revision = "015_path_analyses"`
- `down_revision = "014_assumption_workspace_id"`
- Create table `path_analyses` with columns per design doc Section 4.1
- Use FlexUUID for UUID columns (cross-db compat)
- Use FlexJSON (define locally in migration as `JSONB().with_variant(JSON(), "sqlite")`) for JSON columns
- UNIQUE constraint: `uq_path_analyses_run_config (run_id, config_hash)`
- INDEX: `ix_path_analyses_workspace_id (workspace_id)`
- INDEX: `ix_path_analyses_run_created (run_id, created_at DESC)`
- CHECK: `ck_path_analyses_coverage (coverage_ratio BETWEEN 0 AND 1)` — only on Postgres (SQLite doesn't enforce CHECK)
- FK: `fk_path_analyses_run_id → run_snapshots.run_id`
- FK: `fk_path_analyses_workspace_id → workspaces.workspace_id`

ORM row in `src/db/tables.py` — add `PathAnalysisRow` class:
```python
class PathAnalysisRow(Base):
    """Immutable — persisted SPA + chokepoint analytics for a run."""

    __tablename__ = "path_analyses"

    analysis_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("run_snapshots.run_id"), nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.workspace_id"), nullable=False, index=True,
    )
    analysis_version: Mapped[str] = mapped_column(String(20), nullable=False)
    config_json = mapped_column(FlexJSON, nullable=False)
    config_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    top_paths_json = mapped_column(FlexJSON, nullable=False)
    chokepoints_json = mapped_column(FlexJSON, nullable=False)
    depth_contributions_json = mapped_column(FlexJSON, nullable=False)
    coverage_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    result_checksum: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
```

Note: The UNIQUE constraint `(run_id, config_hash)` and the composite index `(run_id, created_at DESC)` are declared in the migration only (not on ORM), consistent with the pattern for partial unique indexes from Sprint 17.

**Migration tests** (`tests/migration/test_015_path_analyses_postgres.py`) — 4 tests:
1. `test_upgrade_creates_table` — table exists with expected columns
2. `test_unique_constraint_enforced` — duplicate (run_id, config_hash) raises IntegrityError
3. `test_coverage_check_constraint` — coverage_ratio=1.5 raises (Postgres only)
4. `test_downgrade_drops_table` — table removed cleanly

All tests skip if no Postgres available (`@pytest.mark.skipif`).

**Verify:** `python -m alembic upgrade head && python -m alembic check` (with DATABASE_URL set to PG)

**Run:** `python -m pytest tests/migration/test_015_path_analyses_postgres.py -v` (if PG available)

**Commit:** `[sprint20] add migration 015 path_analyses table + ORM row`

---

## Task 4: PathAnalysisRepository (TDD)

Repository layer with CRUD, workspace scoping, idempotency, pagination.

**Files:**
- Create: `src/repositories/path_analytics.py`
- Create: `tests/repositories/test_path_analytics.py`

**Spec:**

Repository follows existing patterns (session-based, `_session.add()` + `await _session.flush()`):

```python
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.tables import PathAnalysisRow
from src.models.base import utc_now


class PathAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *,
        analysis_id: UUID, run_id: UUID, workspace_id: UUID,
        analysis_version: str, config_json: dict, config_hash: str,
        max_depth: int, top_k: int,
        top_paths_json: list, chokepoints_json: list,
        depth_contributions_json: dict, coverage_ratio: float,
        result_checksum: str,
    ) -> PathAnalysisRow:
        row = PathAnalysisRow(
            analysis_id=analysis_id, run_id=run_id,
            workspace_id=workspace_id,
            analysis_version=analysis_version,
            config_json=config_json, config_hash=config_hash,
            max_depth=max_depth, top_k=top_k,
            top_paths_json=top_paths_json,
            chokepoints_json=chokepoints_json,
            depth_contributions_json=depth_contributions_json,
            coverage_ratio=coverage_ratio,
            result_checksum=result_checksum,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, analysis_id: UUID) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.analysis_id == analysis_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_workspace(
        self, analysis_id: UUID, workspace_id: UUID,
    ) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.analysis_id == analysis_id,
                PathAnalysisRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_run_and_config_for_workspace(
        self, run_id: UUID, config_hash: str, workspace_id: UUID,
    ) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.run_id == run_id,
                PathAnalysisRow.config_hash == config_hash,
                PathAnalysisRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_run(
        self, run_id: UUID, workspace_id: UUID, *,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[PathAnalysisRow], int]:
        base = select(PathAnalysisRow).where(
            PathAnalysisRow.run_id == run_id,
            PathAnalysisRow.workspace_id == workspace_id,
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()
        rows_result = await self._session.execute(
            base.order_by(
                PathAnalysisRow.created_at.desc(),
                PathAnalysisRow.analysis_id.desc(),
            ).limit(limit).offset(offset)
        )
        return list(rows_result.scalars().all()), total
```

**Tests** (`tests/repositories/test_path_analytics.py`) — ~10 tests:

Use fixtures that create workspace + run_snapshot rows first (needed for FK).

1. `test_create_and_get_roundtrip` — create → get → verify all fields match
2. `test_get_returns_none_for_missing` — unknown UUID returns None
3. `test_get_for_workspace_hit` — correct workspace returns row
4. `test_get_for_workspace_wrong_workspace` — wrong workspace_id returns None
5. `test_get_by_run_and_config_for_workspace_hit` — exact match returns row
6. `test_get_by_run_and_config_for_workspace_miss` — wrong config_hash returns None
7. `test_list_by_run_multiple_configs` — two analyses for same run, different configs, ordered by created_at DESC
8. `test_list_by_run_pagination` — limit/offset work correctly, total is accurate
9. `test_list_by_run_workspace_isolation` — analysis from workspace A not in workspace B listing
10. `test_idempotency_same_config_hash` — second create with same (run_id, config_hash) either raises IntegrityError or repo handles via get-first pattern

Note: For the concurrent race test (design Section 6.3), test at API layer where we can use the ON CONFLICT pattern. At repo layer, test the get-before-create idempotency pattern.

**Run:** `python -m pytest tests/repositories/test_path_analytics.py -v`

**Commit:** `[sprint20] add path analytics repository with workspace scoping`

---

## Task 5: API Endpoints + Wiring (TDD)

Three endpoints: POST compute, GET by ID, GET list. Mount router. Add DI factory.

**Files:**
- Create: `src/api/path_analytics.py`
- Modify: `src/api/main.py` (mount router)
- Modify: `src/api/dependencies.py` (add DI factory for PathAnalysisRepository)
- Create: `tests/api/test_path_analytics.py`

**Spec:**

DI factory in `src/api/dependencies.py`:
```python
async def get_path_analysis_repo(
    session: AsyncSession = Depends(get_async_session),
) -> PathAnalysisRepository:
    return PathAnalysisRepository(session)
```

Router in `src/api/path_analytics.py`:
```python
router = APIRouter(prefix="/v1/workspaces", tags=["analytics"])
```

**Endpoint 1: POST** `/{workspace_id}/path-analytics`

Flow:
1. Validate config explicitly (even though Pydantic handles ge/le, map to `SPA_INVALID_CONFIG` reason code for bounds, using a pre-Pydantic check or exception handler).
2. Load run via `snap_repo.get(body.run_id)` → check workspace_id → 404 `SPA_RUN_NOT_FOUND`.
3. Compute config_hash → check `pa_repo.get_by_run_and_config_for_workspace` → return 200 with existing row if found (idempotent).
4. Load model data: `_ensure_model_loaded(run.model_version_id, mv_repo, md_repo)` — reuse from `runs.py`. Catch 404 → 422 `SPA_MODEL_DATA_UNAVAILABLE`.
5. Load ResultSets → find `metric_type="direct_effect"` with `series_kind is None` → extract values dict → reconstruct delta_d vector aligned to sector_codes → 422 `SPA_MISSING_DIRECT_EFFECT` if not found.
6. Call `compute_spa(loaded_model.A, loaded_model.B, delta_d, sector_codes, ...)` → catch `SPAConfigError` → 422 `SPA_INVALID_CONFIG`, catch `SPADimensionError` → 422 `SPA_DIMENSION_MISMATCH`.
7. Serialize SPAResult → persist via repository → return 201.

Config hash computation:
```python
import hashlib, json
def _config_hash(config: PathAnalysisConfig) -> str:
    payload = json.dumps(
        {"max_depth": config.max_depth, "top_k": config.top_k},
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
```

Result checksum:
```python
def _result_checksum(result: SPAResult) -> str:
    # Deterministic hash of sorted output
    payload = json.dumps({
        "top_paths": [
            {"s": p.source_sector, "t": p.target_sector, "d": p.depth,
             "c": round(p.contribution, 15)}
            for p in result.top_paths
        ],
        "coverage_ratio": round(result.coverage_ratio, 15),
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
```

Reconstruct delta_d from direct_effect values dict:
```python
def _reconstruct_delta_d(
    values: dict[str, float], sector_codes: list[str],
) -> np.ndarray:
    """Align direct_effect values dict to sector_codes ordering."""
    delta_d = np.zeros(len(sector_codes), dtype=np.float64)
    for idx, code in enumerate(sector_codes):
        delta_d[idx] = values.get(code, 0.0)
    return delta_d
```

**Endpoint 2: GET** `/{workspace_id}/path-analytics/{analysis_id}`

Simple workspace-scoped lookup → 200 or 404 `SPA_ANALYSIS_NOT_FOUND`.

**Endpoint 3: GET** `/{workspace_id}/path-analytics?run_id=...`

Required query param `run_id`. Optional `limit` (default 20, max 100) and `offset` (default 0). Verify run exists in workspace first → 404 `SPA_RUN_NOT_FOUND`. Return `PathAnalysisListResponse`.

Row-to-response helper:
```python
def _row_to_response(row: PathAnalysisRow) -> PathAnalysisResponse:
    # Deserialize JSON fields back to typed Pydantic models
```

Mount in `main.py`:
```python
from src.api.path_analytics import router as path_analytics_router
app.include_router(path_analytics_router)
```

**Tests** (`tests/api/test_path_analytics.py`) — ~18 tests:

Use fixtures that set up: workspace → model_version → model_data → run_snapshot → result_sets (with direct_effect).

Happy paths:
1. `test_post_creates_analysis_201` — full happy path, verify response schema
2. `test_post_idempotent_returns_200` — second POST same config returns 200 with same analysis_id
3. `test_get_by_id_200` — create then GET by ID
4. `test_list_by_run_200` — create two analyses with different configs, list returns both
5. `test_list_by_run_pagination` — limit=1 returns 1 item with total=2

Error precedence (ordered):
6. `test_post_wrong_workspace_run_404` — run belongs to different workspace → 404 `SPA_RUN_NOT_FOUND`
7. `test_post_run_not_found_404` — nonexistent run_id → 404 `SPA_RUN_NOT_FOUND`
8. `test_post_no_direct_effect_422` — run exists but no direct_effect ResultSet → 422 `SPA_MISSING_DIRECT_EFFECT`
9. `test_post_no_results_422` — run exists but zero ResultSets → 422 `SPA_NO_RESULTS` (or `SPA_MISSING_DIRECT_EFFECT`)
10. `test_post_model_data_unavailable_422` — model_version exists but no model_data row → 422 `SPA_MODEL_DATA_UNAVAILABLE`
11. `test_post_invalid_config_max_depth_422` — max_depth=13 → 422 `SPA_INVALID_CONFIG`
12. `test_post_invalid_config_top_k_422` — top_k=0 → 422 `SPA_INVALID_CONFIG`

Workspace isolation:
13. `test_get_by_id_wrong_workspace_404` — analysis exists but wrong workspace → 404
14. `test_list_by_run_wrong_workspace_empty` — run in workspace A, list from workspace B → empty or 404

Auth:
15. `test_post_no_auth_401` — no auth header → 401
16. `test_get_no_auth_401` — no auth header → 401

Response content:
17. `test_response_has_sector_codes` — top_paths items have source/target sector codes
18. `test_response_coverage_ratio_valid` — coverage_ratio ∈ [0, 1]

**Run:** `python -m pytest tests/api/test_path_analytics.py -v`

**Then full suite:** `python -m pytest -q` — expect baseline + engine + migration + repo + api tests

**Commit:** `[sprint20] expose additive workspace-scoped path analytics api contracts`

---

## Task 6: Full Verification + Docs + OpenAPI Refresh

Final verification gate before PR.

**Files:**
- Modify: `docs/evidence/release-readiness-checklist.md` (add Sprint 20 section)
- Regenerate: `openapi.json`

**Spec:**

1. Run full lint: `python -m ruff check src tests` + `python -m ruff format --check src tests`
2. Run full test suite: `python -m pytest -q` — all pass, zero failures
3. Run alembic verification (with PG): `python -m alembic current` → 015_path_analyses (head), `python -m alembic check` → no new operations
4. Regenerate OpenAPI:
```python
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```
5. Add Sprint 20 section to release-readiness-checklist.md with:
   - Migration evidence (015 path_analyses)
   - SPA formula/identity matrix
   - Chokepoint scoring contract
   - Error taxonomy table
   - Test counts (baseline vs sprint 20)
   - Preflight checks
   - Go/No-Go criteria

**Commit:** `[sprint20] full verification: lint clean, openapi refreshed, release checklist updated`

---

## Task 7: Finish (PR)

Use `superpowers:finishing-a-development-branch` skill. Push branch, open PR targeting main.

---

## Summary

| Task | What | ~Tests | Key Files |
|------|------|--------|-----------|
| 1 | Pydantic models + domain errors | 0 | `src/models/path.py`, `src/engine/structural_path.py` |
| 2 | SPA engine (TDD) | 15 | `src/engine/structural_path.py`, `tests/engine/test_structural_path.py` |
| 3 | Migration 015 + ORM | 4 | `alembic/versions/015_path_analyses.py`, `src/db/tables.py` |
| 4 | Repository (TDD) | 10 | `src/repositories/path_analytics.py`, `tests/repositories/test_path_analytics.py` |
| 5 | API endpoints (TDD) | 18 | `src/api/path_analytics.py`, `tests/api/test_path_analytics.py` |
| 6 | Verification + docs | 0 | `openapi.json`, `docs/evidence/release-readiness-checklist.md` |
| 7 | PR | 0 | — |
| **Total** | | **~47** | |
