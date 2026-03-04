# Sprint 19: Client Portal Collaboration Flows — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver portal-ready assumption sign-off, scenario comparison, and evidence browsing APIs with workspace-scoped isolation, deterministic behavior, and fail-closed validation.

**Architecture:** Extend existing `governance.py` and `scenarios.py` routers with additive endpoints and query params. One additive migration (014) for `assumptions.workspace_id`. New repo methods for workspace-scoped lookups. Pure deterministic math for comparison deltas.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, pytest

**Design doc:** `docs/plans/2026-03-04-sprint19-client-portal-collaboration-design.md`

---

## Task 1: Migration 014 — `assumptions.workspace_id`

**Files:**
- Create: `alembic/versions/014_assumption_workspace_id.py`
- Modify: `src/db/tables.py:292-308` (AssumptionRow)
- Test: `tests/migration/test_014_assumption_workspace_postgres.py`

**Context:** AssumptionRow currently has no workspace_id. We add a nullable FK column with index so all sign-off APIs can enforce workspace scoping. Legacy NULL rows are hidden from workspace APIs.

**Step 1: Create migration file**

Create `alembic/versions/014_assumption_workspace_id.py`:

```python
"""Add workspace_id to assumptions for workspace scoping.

Revision ID: 014_assumption_workspace_id
Revises: 013_sg_provenance
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "014_assumption_workspace_id"
down_revision = "013_sg_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assumptions",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_assumptions_workspace_id",
        "assumptions",
        "workspaces",
        ["workspace_id"],
        ["workspace_id"],
    )
    op.create_index(
        "ix_assumptions_workspace_id",
        "assumptions",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_assumptions_workspace_id", table_name="assumptions")
    op.drop_constraint("fk_assumptions_workspace_id", "assumptions", type_="foreignkey")
    op.drop_column("assumptions", "workspace_id")
```

**Step 2: Update ORM model**

Add `workspace_id` to `AssumptionRow` in `src/db/tables.py` after line 303 (after `evidence_refs`):

```python
    workspace_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
```

**Step 3: Write migration tests**

Create `tests/migration/test_014_assumption_workspace_postgres.py` with 4 tests (skip when PG unavailable):
- `test_upgrade_adds_column` — upgrade head, verify column exists
- `test_downgrade_removes_column` — downgrade -1, verify column gone
- `test_re_upgrade` — upgrade head again, verify clean
- `test_alembic_check_no_drift` — `alembic check` reports no drift

**Step 4: Run tests**

```bash
python -m pytest tests/migration/test_014_assumption_workspace_postgres.py -v
```

Expected: 4 passed or 4 skipped (if PG unavailable).

**Step 5: Commit**

```bash
git add alembic/versions/014_assumption_workspace_id.py src/db/tables.py tests/migration/test_014_assumption_workspace_postgres.py
git commit -m "[sprint19] add migration 014 assumption workspace_id + ORM update"
```

---

## Task 2: Assumption Repository — Workspace-Scoped Methods

**Files:**
- Modify: `src/repositories/governance.py:19-91` (AssumptionRepository)
- Test: `tests/repositories/test_assumption_workspace.py`

**Context:** Add `get_for_workspace()` and `list_by_workspace()` repo methods. These are the foundation for all sign-off API endpoints. Legacy rows with NULL workspace_id are excluded from workspace-scoped queries.

**Step 1: Write failing tests**

Create `tests/repositories/test_assumption_workspace.py`:

Tests to write:
- `test_list_by_workspace_returns_only_workspace_rows` — create assumptions in ws_a and ws_b, list ws_a only sees ws_a rows
- `test_list_by_workspace_excludes_null_workspace` — create assumption without workspace_id, verify it's not listed
- `test_list_by_workspace_filters_by_status` — create DRAFT and APPROVED, filter by status
- `test_list_by_workspace_orders_by_created_at_desc` — verify ordering
- `test_list_by_workspace_paginates` — create 5 rows, request limit=2 offset=0, then offset=2
- `test_list_by_workspace_returns_total_count` — verify total across pages
- `test_get_for_workspace_returns_matching` — get by id and workspace, found
- `test_get_for_workspace_returns_none_wrong_workspace` — get by id but wrong workspace → None
- `test_get_for_workspace_returns_none_null_workspace` — legacy row with NULL workspace → None

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/repositories/test_assumption_workspace.py -v
```

Expected: FAIL (methods don't exist yet).

**Step 3: Implement repo methods**

Add to `AssumptionRepository` in `src/repositories/governance.py`:

```python
async def get_for_workspace(
    self, assumption_id: UUID, workspace_id: UUID,
) -> AssumptionRow | None:
    """Get assumption only if it belongs to the given workspace.

    Returns None for wrong workspace or legacy NULL workspace_id rows.
    """
    result = await self._session.execute(
        select(AssumptionRow).where(
            AssumptionRow.assumption_id == assumption_id,
            AssumptionRow.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()

async def list_by_workspace(
    self, workspace_id: UUID, *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AssumptionRow], int]:
    """List assumptions scoped to workspace with optional status filter.

    Returns (page_rows, total_count). Excludes NULL workspace_id rows.
    Orders by created_at DESC, assumption_id DESC.
    """
    base = select(AssumptionRow).where(
        AssumptionRow.workspace_id == workspace_id,
    )
    if status is not None:
        base = base.where(AssumptionRow.status == status)

    count_result = await self._session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar_one()

    rows_result = await self._session.execute(
        base.order_by(
            AssumptionRow.created_at.desc(),
            AssumptionRow.assumption_id.desc(),
        ).limit(limit).offset(offset)
    )
    return list(rows_result.scalars().all()), total
```

Add `from sqlalchemy import func` to imports if not present.

**Step 4: Run tests**

```bash
python -m pytest tests/repositories/test_assumption_workspace.py -v
```

Expected: All pass.

**Step 5: Commit**

```bash
git add src/repositories/governance.py tests/repositories/test_assumption_workspace.py
git commit -m "[sprint19] add workspace-scoped assumption repo methods"
```

---

## Task 3: Assumption Sign-Off API Endpoints

**Files:**
- Modify: `src/api/governance.py` (add list, detail, reject endpoints; modify create, approve)
- Test: `tests/api/test_assumption_signoff.py`

**Context:** Add `GET /assumptions` (list), `GET /assumptions/{id}` (detail), `POST /assumptions/{id}/reject`. Modify `POST /assumptions` (set workspace_id), `POST /assumptions/{id}/approve` (add role gate + workspace scope). All use reason codes from design doc.

**Step 1: Write failing tests**

Create `tests/api/test_assumption_signoff.py`:

Tests to write (TDD, all fail initially):
- **List tests:**
  - `test_list_assumptions_empty_workspace` — 200, empty items
  - `test_list_assumptions_returns_workspace_scoped` — create in ws_a, list ws_a, verify found
  - `test_list_assumptions_filters_by_status` — create DRAFT + APPROVED, filter by DRAFT only
  - `test_list_assumptions_paginates` — limit=2, offset=0, verify has_more=True
  - `test_list_assumptions_invalid_pagination_422` — limit=200 → 422 ASSUMPTION_INVALID_PAGINATION
  - `test_list_assumptions_hides_null_workspace` — legacy row not visible

- **Detail tests:**
  - `test_get_assumption_detail` — 200 with all fields
  - `test_get_assumption_detail_404_wrong_workspace` — wrong ws → 404
  - `test_get_assumption_detail_404_null_workspace` — legacy row → 404

- **Create tests:**
  - `test_create_assumption_sets_workspace_id` — POST create, verify workspace_id persisted

- **Approve tests:**
  - `test_approve_requires_manager_role` — analyst → 403
  - `test_approve_workspace_scoped_404` — approve from wrong ws → 404
  - `test_approve_missing_range_422` — no range → 422 ASSUMPTION_RANGE_REQUIRED
  - `test_approve_non_draft_409` — approve APPROVED → 409 ASSUMPTION_NOT_DRAFT
  - `test_approve_happy_path` — manager approves DRAFT → 200, status=APPROVED

- **Reject tests:**
  - `test_reject_requires_manager_role` — analyst → 403
  - `test_reject_workspace_scoped_404` — wrong ws → 404
  - `test_reject_non_draft_409` — reject APPROVED → 409 ASSUMPTION_NOT_DRAFT
  - `test_reject_happy_path` — manager rejects DRAFT → 200, status=REJECTED

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/api/test_assumption_signoff.py -v
```

**Step 3: Implement endpoints**

In `src/api/governance.py`:

**Add new schemas:**

```python
class AssumptionListItem(BaseModel):
    assumption_id: str
    type: str
    value: float
    units: str
    justification: str
    status: str
    range_min: float | None = None
    range_max: float | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str
    updated_at: str

class AssumptionListResponse(BaseModel):
    items: list[AssumptionListItem]
    total: int
    limit: int
    offset: int
    has_more: bool

class AssumptionDetailResponse(BaseModel):
    assumption_id: str
    type: str
    value: float
    units: str
    justification: str
    status: str
    range_min: float | None = None
    range_max: float | None = None
    evidence_refs: list[str]
    approved_by: str | None = None
    approved_at: str | None = None
    created_at: str
    updated_at: str

class RejectAssumptionRequest(BaseModel):
    actor: str
    reason: str | None = None

class RejectAssumptionResponse(BaseModel):
    assumption_id: str
    status: str
```

**Add new endpoints** (list and detail before approve/reject in code order):

```python
@router.get("/{workspace_id}/governance/assumptions", response_model=AssumptionListResponse)
async def list_assumptions(
    workspace_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    offset: int = Query(default=0),
) -> AssumptionListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail={
            "reason_code": "ASSUMPTION_INVALID_PAGINATION",
            "message": f"limit must be 1-100, got {limit}.",
        })
    if offset < 0:
        raise HTTPException(status_code=422, detail={
            "reason_code": "ASSUMPTION_INVALID_PAGINATION",
            "message": f"offset must be >= 0, got {offset}.",
        })
    rows, total = await assumption_repo.list_by_workspace(
        workspace_id, status=status, limit=limit, offset=offset,
    )
    items = [_row_to_assumption_item(r) for r in rows]
    return AssumptionListResponse(
        items=items, total=total, limit=limit, offset=offset,
        has_more=total > offset + limit,
    )
```

```python
@router.get(
    "/{workspace_id}/governance/assumptions/{assumption_id}",
    response_model=AssumptionDetailResponse,
)
async def get_assumption_detail(
    workspace_id: UUID,
    assumption_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
) -> AssumptionDetailResponse:
    row = await assumption_repo.get_for_workspace(assumption_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail={
            "reason_code": "ASSUMPTION_NOT_FOUND",
            "message": f"Assumption {assumption_id} not found.",
        })
    return _row_to_assumption_detail(row)
```

```python
@router.post(
    "/{workspace_id}/governance/assumptions/{assumption_id}/reject",
    response_model=RejectAssumptionResponse,
)
async def reject_assumption(
    workspace_id: UUID,
    assumption_id: UUID,
    body: RejectAssumptionRequest,
    member: WorkspaceMember = Depends(require_role("manager", "admin")),
    assumption_repo: AssumptionRepository = Depends(get_assumption_repo),
) -> RejectAssumptionResponse:
    row = await assumption_repo.get_for_workspace(assumption_id, workspace_id)
    if row is None:
        raise HTTPException(status_code=404, detail={
            "reason_code": "ASSUMPTION_NOT_FOUND",
            "message": f"Assumption {assumption_id} not found.",
        })
    if row.status != "DRAFT":
        raise HTTPException(status_code=409, detail={
            "reason_code": "ASSUMPTION_NOT_DRAFT",
            "message": f"Cannot reject: status is {row.status}, expected DRAFT.",
        })
    updated = await assumption_repo.reject(assumption_id)
    return RejectAssumptionResponse(
        assumption_id=str(updated.assumption_id),
        status=updated.status,
    )
```

**Modify existing `create_assumption`:** Add `workspace_id=workspace_id` to the `assumption_repo.create()` call.

**Modify existing `approve_assumption`:**
- Change `Depends(require_workspace_member)` → `Depends(require_role("manager", "admin"))`
- Change `assumption_repo.get(assumption_id)` → `assumption_repo.get_for_workspace(assumption_id, workspace_id)`
- Change range validation from 400 → 422 with `ASSUMPTION_RANGE_REQUIRED` reason code
- Change non-DRAFT check to use `ASSUMPTION_NOT_DRAFT` reason code

**Add helper functions:**

```python
def _row_to_assumption_item(row: AssumptionRow) -> AssumptionListItem:
    return AssumptionListItem(
        assumption_id=str(row.assumption_id),
        type=row.type,
        value=row.value,
        units=row.units,
        justification=row.justification,
        status=row.status,
        range_min=row.range_json.get("min") if row.range_json else None,
        range_max=row.range_json.get("max") if row.range_json else None,
        approved_by=str(row.approved_by) if row.approved_by else None,
        approved_at=row.approved_at.isoformat() if row.approved_at else None,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )

def _row_to_assumption_detail(row: AssumptionRow) -> AssumptionDetailResponse:
    return AssumptionDetailResponse(
        assumption_id=str(row.assumption_id),
        type=row.type,
        value=row.value,
        units=row.units,
        justification=row.justification,
        status=row.status,
        range_min=row.range_json.get("min") if row.range_json else None,
        range_max=row.range_json.get("max") if row.range_json else None,
        evidence_refs=[str(e) for e in (row.evidence_refs or [])],
        approved_by=str(row.approved_by) if row.approved_by else None,
        approved_at=row.approved_at.isoformat() if row.approved_at else None,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )
```

**Modify `create_assumption` repo call** to include `workspace_id`:

```python
await assumption_repo.create(
    assumption_id=assumption.assumption_id,
    type=assumption.type.value,
    value=assumption.value,
    units=assumption.units,
    justification=assumption.justification,
    evidence_refs=[str(er) for er in assumption.evidence_refs],
    status=assumption.status.value,
    workspace_id=workspace_id,  # NEW
)
```

Also update `AssumptionRepository.create()` to accept `workspace_id: UUID | None = None` and pass it to `AssumptionRow(...)`.

**Step 4: Run tests**

```bash
python -m pytest tests/api/test_assumption_signoff.py -v
```

Expected: All pass.

**Step 5: Run existing governance tests for regression**

```bash
python -m pytest tests/api/test_decisions.py tests/integration/test_governance_chain.py -v
```

Expected: All still pass.

**Step 6: Commit**

```bash
git add src/api/governance.py src/repositories/governance.py tests/api/test_assumption_signoff.py
git commit -m "[sprint19] implement authz-safe assumption sign-off collaboration flow"
```

---

## Task 4: Scenario Comparison API — `POST /scenarios/compare-runs`

**Files:**
- Modify: `src/api/scenarios.py` (add compare-runs endpoint)
- Test: `tests/api/test_scenario_comparison.py`

**Context:** Deterministic comparison of two runs' ResultSet data. Route declared before `{scenario_id}` routes to prevent shadowing. Uses `_extract_aggregate()` helper for consistent value extraction.

**Step 1: Write failing tests**

Create `tests/api/test_scenario_comparison.py`:

Tests to write:
- **Happy path:**
  - `test_compare_runs_happy_path` — two runs with same model, same metrics, verify deltas correct
  - `test_compare_runs_pct_change_correct` — verify delta / value_a * 100
  - `test_compare_runs_pct_change_none_when_zero` — value_a=0 → pct_change=None

- **Validation:**
  - `test_compare_run_not_found_404` — nonexistent run_id → 404 COMPARE_RUN_NOT_FOUND
  - `test_compare_run_wrong_workspace_404` — run exists but different ws → 404
  - `test_compare_no_results_422` — run with no ResultSet rows → 422 COMPARE_NO_RESULTS
  - `test_compare_model_mismatch_422` — different model_version_id → 422 COMPARE_MODEL_MISMATCH
  - `test_compare_metric_set_mismatch_422` — run_a has {total_output, employment}, run_b has {total_output} → 422

- **Annual:**
  - `test_compare_annual_happy_path` — include_annual=True, verify year-by-year deltas
  - `test_compare_annual_unavailable_422` — include_annual=True but no annual rows → 422
  - `test_compare_annual_year_mismatch_422` — different year sets → 422

- **Peak:**
  - `test_compare_peak_happy_path` — include_peak=True, verify peak comparison
  - `test_compare_peak_unavailable_422` — include_peak=True but no peak rows → 422

- **Aggregate extraction:**
  - `test_extract_aggregate_uses_total_key` — {"_total": 100, "A": 60, "B": 40} → 100
  - `test_extract_aggregate_sums_without_total` — {"A": 60, "B": 40} → 100

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/api/test_scenario_comparison.py -v
```

**Step 3: Implement endpoint**

In `src/api/scenarios.py`:

**Add schemas** (near the top, after existing schemas):

```python
class CompareRunsRequest(BaseModel):
    run_id_a: UUID
    run_id_b: UUID
    include_annual: bool = False
    include_peak: bool = False

class MetricComparison(BaseModel):
    metric_type: str
    value_a: float
    value_b: float
    delta: float
    pct_change: float | None = None

class AnnualComparison(BaseModel):
    year: int
    metrics: list[MetricComparison]

class PeakComparison(BaseModel):
    peak_year_a: int | None = None
    peak_year_b: int | None = None
    metrics: list[MetricComparison]

class CompareRunsResponse(BaseModel):
    run_id_a: str
    run_id_b: str
    model_version_a: str
    model_version_b: str
    sector_count_a: int
    sector_count_b: int
    metrics: list[MetricComparison]
    annual: list[AnnualComparison] | None = None
    peak: PeakComparison | None = None
```

**Add helper:**

```python
def _extract_aggregate(values: dict[str, float]) -> float:
    """Deterministic aggregate: use _total if present, else sum numeric values."""
    if "_total" in values:
        return float(values["_total"])
    return sum(float(v) for v in values.values() if isinstance(v, (int, float)))


def _build_metric_comparison(
    metric_type: str,
    values_a: dict[str, float],
    values_b: dict[str, float],
) -> MetricComparison:
    va = _extract_aggregate(values_a)
    vb = _extract_aggregate(values_b)
    delta = vb - va
    pct = (delta / va * 100) if va != 0.0 else None
    return MetricComparison(
        metric_type=metric_type,
        value_a=va, value_b=vb,
        delta=delta, pct_change=pct,
    )
```

**Add endpoint BEFORE the `list_scenarios` route** (critical — prevents `{scenario_id}` shadowing):

```python
@router.post(
    "/{workspace_id}/scenarios/compare-runs",
    response_model=CompareRunsResponse,
)
async def compare_runs(
    workspace_id: UUID,
    body: CompareRunsRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
    rs_repo: ResultSetRepository = Depends(get_result_set_repo),
) -> CompareRunsResponse:
    """Compare two runs' deterministic outputs within the same workspace."""
    # 1. Load and validate runs
    snap_a = await snap_repo.get(body.run_id_a)
    if snap_a is None or snap_a.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail={
            "reason_code": "COMPARE_RUN_NOT_FOUND",
            "message": f"Run {body.run_id_a} not found in workspace.",
        })
    snap_b = await snap_repo.get(body.run_id_b)
    if snap_b is None or snap_b.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail={
            "reason_code": "COMPARE_RUN_NOT_FOUND",
            "message": f"Run {body.run_id_b} not found in workspace.",
        })

    # 2. Load cumulative results
    results_a = await rs_repo.get_by_run_series(body.run_id_a, series_kind=None)
    results_b = await rs_repo.get_by_run_series(body.run_id_b, series_kind=None)
    if not results_a:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_NO_RESULTS",
            "message": f"Run {body.run_id_a} has no result sets.",
        })
    if not results_b:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_NO_RESULTS",
            "message": f"Run {body.run_id_b} has no result sets.",
        })

    # 3. Model mismatch check
    if snap_a.model_version_id != snap_b.model_version_id:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_MODEL_MISMATCH",
            "message": "Runs use different model versions.",
        })

    # 4. Metric set validation
    metrics_a = {r.metric_type for r in results_a}
    metrics_b = {r.metric_type for r in results_b}
    if metrics_a != metrics_b:
        raise HTTPException(status_code=422, detail={
            "reason_code": "COMPARE_METRIC_SET_MISMATCH",
            "message": f"Metric sets differ: a={sorted(metrics_a)}, b={sorted(metrics_b)}.",
        })

    # 5. Build cumulative comparisons
    map_a = {r.metric_type: r.values for r in results_a}
    map_b = {r.metric_type: r.values for r in results_b}
    metrics = [
        _build_metric_comparison(mt, map_a[mt], map_b[mt])
        for mt in sorted(metrics_a)
    ]

    # 6. Annual comparison (optional)
    annual = None
    if body.include_annual:
        annual_a = await rs_repo.get_by_run_series(body.run_id_a, series_kind="annual")
        annual_b = await rs_repo.get_by_run_series(body.run_id_b, series_kind="annual")
        if not annual_a or not annual_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_ANNUAL_UNAVAILABLE",
                "message": "Annual series data not available for one or both runs.",
            })
        years_a = {r.year for r in annual_a}
        years_b = {r.year for r in annual_b}
        if years_a != years_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_ANNUAL_YEAR_MISMATCH",
                "message": f"Year sets differ: a={sorted(years_a)}, b={sorted(years_b)}.",
            })
        annual = _build_annual_comparisons(annual_a, annual_b, sorted(years_a))

    # 7. Peak comparison (optional)
    peak = None
    if body.include_peak:
        peak_a = await rs_repo.get_by_run_series(body.run_id_a, series_kind="peak")
        peak_b = await rs_repo.get_by_run_series(body.run_id_b, series_kind="peak")
        if not peak_a or not peak_b:
            raise HTTPException(status_code=422, detail={
                "reason_code": "COMPARE_PEAK_UNAVAILABLE",
                "message": "Peak data not available for one or both runs.",
            })
        peak = _build_peak_comparison(peak_a, peak_b)

    return CompareRunsResponse(
        run_id_a=str(body.run_id_a),
        run_id_b=str(body.run_id_b),
        model_version_a=str(snap_a.model_version_id),
        model_version_b=str(snap_b.model_version_id),
        sector_count_a=snap_a.sector_count,
        sector_count_b=snap_b.sector_count,
        metrics=metrics,
        annual=annual,
        peak=peak,
    )
```

**Add annual/peak builders:**

```python
def _build_annual_comparisons(
    annual_a: list, annual_b: list, years: list[int],
) -> list[AnnualComparison]:
    """Build per-year metric comparisons from annual ResultSet rows."""
    # Group by (year, metric_type)
    def _group(rows):
        out = {}
        for r in rows:
            out.setdefault(r.year, {})[r.metric_type] = r.values
        return out
    ga, gb = _group(annual_a), _group(annual_b)
    result = []
    for y in years:
        year_a, year_b = ga.get(y, {}), gb.get(y, {})
        shared = sorted(set(year_a) & set(year_b))
        result.append(AnnualComparison(
            year=y,
            metrics=[_build_metric_comparison(mt, year_a[mt], year_b[mt]) for mt in shared],
        ))
    return result


def _build_peak_comparison(peak_a: list, peak_b: list) -> PeakComparison:
    """Build peak-year metric comparison."""
    map_a = {r.metric_type: r.values for r in peak_a}
    map_b = {r.metric_type: r.values for r in peak_b}
    shared = sorted(set(map_a) & set(map_b))
    return PeakComparison(
        peak_year_a=peak_a[0].year if peak_a else None,
        peak_year_b=peak_b[0].year if peak_b else None,
        metrics=[_build_metric_comparison(mt, map_a[mt], map_b[mt]) for mt in shared],
    )
```

**Add imports** to `src/api/scenarios.py`:

```python
from src.repositories.engine import ResultSetRepository, RunSnapshotRepository
from src.api.dependencies import get_result_set_repo, get_run_snapshot_repo
```

**Step 4: Run tests**

```bash
python -m pytest tests/api/test_scenario_comparison.py -v
```

Expected: All pass.

**Step 5: Run existing scenario tests for regression**

```bash
python -m pytest tests/api/test_scenarios_read.py -v
```

Expected: All still pass (no existing routes broken).

**Step 6: Commit**

```bash
git add src/api/scenarios.py tests/api/test_scenario_comparison.py
git commit -m "[sprint19] add deterministic scenario comparison dashboard api outputs"
```

---

## Task 5: Evidence Browsing — Pagination + Filters

**Files:**
- Modify: `src/api/governance.py:594-632` (extend list_evidence)
- Modify: `src/repositories/governance.py:193-337` (add browse method)
- Test: `tests/api/test_evidence_browse.py`

**Context:** Extend existing `GET /evidence` with additive pagination and filter params. Backward-compatible: when `limit` is None, behavior identical to current. New `browse()` repo method handles dynamic query building.

**Step 1: Write failing tests**

Create `tests/api/test_evidence_browse.py`:

Tests to write:
- **Backward compatibility:**
  - `test_evidence_list_no_params_returns_all` — no limit → all rows, total=len(items), no pagination fields
  - `test_evidence_list_with_run_id_existing_behavior` — existing run_id filter still works

- **Pagination:**
  - `test_evidence_paginated_limit_offset` — limit=2, offset=0, verify items + total_matching + has_more
  - `test_evidence_paginated_second_page` — limit=2, offset=2, verify continuation
  - `test_evidence_invalid_limit_422` — limit=200 → 422 EVIDENCE_INVALID_PAGINATION
  - `test_evidence_negative_offset_422` — offset=-1 → 422 EVIDENCE_INVALID_PAGINATION
  - `test_evidence_offset_without_limit_422` — offset=5 without limit → 422

- **Claim filter:**
  - `test_evidence_claim_id_filter` — create claim with evidence_refs, filter by claim_id → only those snippets
  - `test_evidence_claim_id_empty_refs_returns_empty` — claim exists but evidence_refs=[] → empty items, total_matching=0
  - `test_evidence_claim_id_not_found_404` — nonexistent claim → 404

- **Source filter:**
  - `test_evidence_source_id_filter` — filter by source_id → only snippets from that source
  - `test_evidence_source_id_not_found_404` — nonexistent source → 404

- **Text search:**
  - `test_evidence_text_query_filters` — text_query="budget" → only matching snippets
  - `test_evidence_text_query_too_short_422` — text_query="a" → 422 EVIDENCE_TEXT_QUERY_TOO_SHORT
  - `test_evidence_text_query_trimmed` — text_query="  ab  " → trimmed to "ab", valid

- **Combined filters:**
  - `test_evidence_combined_filters_and` — run_id + claim_id + limit → AND combination

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/api/test_evidence_browse.py -v
```

**Step 3: Implement browse repo method**

Add to `EvidenceSnippetRepository` in `src/repositories/governance.py`:

```python
async def browse(
    self, workspace_id: UUID, *,
    run_id: UUID | None = None,
    snippet_ids: list[UUID] | None = None,
    source_id: UUID | None = None,
    text_query: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> tuple[list[EvidenceSnippetRow], int | None]:
    """Paginated, filtered evidence browsing with workspace scoping.

    Returns (rows, total_count). total_count is None when unpaginated.
    snippet_ids is pre-resolved from claim's evidence_refs by the API layer.
    """
    base = (
        select(EvidenceSnippetRow)
        .join(DocumentRow, EvidenceSnippetRow.source_id == DocumentRow.doc_id)
        .where(DocumentRow.workspace_id == workspace_id)
    )

    if snippet_ids is not None:
        if not snippet_ids:
            return [], 0
        base = base.where(EvidenceSnippetRow.snippet_id.in_(snippet_ids))

    if source_id is not None:
        base = base.where(EvidenceSnippetRow.source_id == source_id)

    if text_query is not None:
        base = base.where(
            EvidenceSnippetRow.extracted_text.ilike(f"%{text_query}%")
        )

    if run_id is not None:
        # Resolve run → source checksums → documents → snippets
        snap_result = await self._session.execute(
            select(RunSnapshotRow).where(
                RunSnapshotRow.run_id == run_id,
                RunSnapshotRow.workspace_id == workspace_id,
            )
        )
        snapshot = snap_result.scalar_one_or_none()
        if snapshot is None:
            return [], 0
        checksums = snapshot.source_checksums or []
        if not checksums:
            return [], 0
        doc_result = await self._session.execute(
            select(DocumentRow.doc_id).where(
                DocumentRow.workspace_id == workspace_id,
                DocumentRow.hash_sha256.in_(checksums),
            )
        )
        doc_ids = list(doc_result.scalars().all())
        if not doc_ids:
            return [], 0
        base = base.where(EvidenceSnippetRow.source_id.in_(doc_ids))

    base = base.order_by(
        EvidenceSnippetRow.created_at.asc(),
        EvidenceSnippetRow.snippet_id.asc(),
    )

    total_count = None
    if limit is not None:
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total_count = count_result.scalar_one()
        base = base.limit(limit).offset(offset or 0)

    result = await self._session.execute(base)
    return list(result.scalars().all()), total_count
```

**Step 4: Modify list_evidence endpoint**

Replace the existing `list_evidence` in `src/api/governance.py` (lines 594-632) with the extended version:

Add new query params, add validation, use `browse()` repo method. When `limit` is None: return all rows with backward-compatible response (new fields are None). When `limit` is set: populate pagination fields.

Update `EvidenceListResponse` to add optional fields:

```python
class EvidenceListResponse(BaseModel):
    items: list[EvidenceListItem]
    total: int
    total_matching: int | None = None
    limit: int | None = None
    offset: int | None = None
    has_more: bool | None = None
```

**Step 5: Run tests**

```bash
python -m pytest tests/api/test_evidence_browse.py -v
```

Expected: All pass.

**Step 6: Run existing evidence tests for regression**

```bash
python -m pytest tests/integration/test_governance_chain.py -v
```

Expected: All still pass.

**Step 7: Commit**

```bash
git add src/api/governance.py src/repositories/governance.py tests/api/test_evidence_browse.py
git commit -m "[sprint19] add workspace-scoped evidence browsing contracts for portal"
```

---

## Task 6: Full Verification + Docs + OpenAPI Refresh

**Files:**
- Modify: `openapi.json` (regenerate)
- Modify: `docs/evidence/release-readiness-checklist.md` (add Sprint 19 section)

**Step 1: Run full test suite**

```bash
python -m pytest --tb=short -q
```

Expected: All tests pass (baseline 4,220 + new Sprint 19 tests). Zero failures.

**Step 2: Run linter**

```bash
python -m ruff check src/ tests/ --fix
```

Expected: No errors remaining.

**Step 3: Regenerate OpenAPI**

```bash
python -c "from src.api.main import app; import json; open('openapi.json', 'w').write(json.dumps(app.openapi(), indent=2) + '\n')"
```

Verify new endpoints appear:

```bash
grep -c "compare-runs\|assumptions/{assumption_id}/reject\|assumptions/{assumption_id}\"\|governance/assumptions\"" openapi.json
```

**Step 4: Add Sprint 19 section to release readiness checklist**

Append Sprint 19 section to `docs/evidence/release-readiness-checklist.md`:
- Assumption sign-off auth matrix
- Scenario comparison validation matrix
- Evidence browsing filter matrix
- Sprint 19 test counts
- Migration 014 evidence

**Step 5: Run alembic check (if PG available)**

```bash
python -c "import os; os.environ['DATABASE_URL']='postgresql+asyncpg://postgres:Salim1977@localhost:5432/impactos'; from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.upgrade(cfg, 'head'); command.downgrade(cfg, '-1'); command.upgrade(cfg, 'head'); command.check(cfg)"
```

**Step 6: Commit**

```bash
git add openapi.json docs/evidence/release-readiness-checklist.md
git commit -m "[sprint19] add mvp19 portal evidence and refresh openapi"
```

---

## Task 7: Push + PR

**Step 1: Push branch**

```bash
git push -u origin phase3-sprint19-client-portal-collaboration
```

**Step 2: Create PR**

Use `superpowers:finishing-a-development-branch` skill.

---

## Execution Notes

- **TDD throughout:** Every task writes tests first, verifies they fail, then implements.
- **Frequent commits:** Each task produces exactly one commit with prescribed message.
- **No regressions:** Task 6 runs the full 4,220+ test baseline.
- **Route safety:** compare-runs endpoint declared BEFORE {scenario_id} routes.
- **Backward compatibility:** Evidence pagination is opt-in (limit=None default).
- **Reason codes are stable:** Defined in design doc, tests verify exact codes.
- **Python 3.12:** Use `python -m pytest` NOT bare `pytest`.
