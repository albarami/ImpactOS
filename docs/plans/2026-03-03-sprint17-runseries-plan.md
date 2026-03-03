# Sprint 17: RunSeries Annual Storage + API — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist annual phased outputs as first-class ResultSet rows with `year`/`series_kind`/`baseline_run_id` columns, emit annual+peak+delta series from batch runner, and expose them additively via flat API with `include_series=true`.

**Architecture:** Extend `ResultSetRow` with 3 nullable columns + CHECK constraints + partial unique indexes. Batch runner emits annual/peak rows alongside existing cumulative rows. API returns flat `ResultSetResponse` with optional series fields when `include_series=true`. Delta series computed by subtracting baseline annual rows from scenario annual rows.

**Tech Stack:** SQLAlchemy + Alembic (schema), Pydantic v2 (models), FastAPI (API), NumPy (deterministic math), pytest (TDD).

**Baseline:** 4114 tests on main at `4374376`.

---

### Task 1: Extend Pydantic ResultSet model with series fields

**Files:**
- Modify: `src/models/run.py:49-67`
- Test: `tests/engine/test_runseries.py` (create)

**Step 1: Write the failing test**

Create `tests/engine/test_runseries.py`:

```python
"""Sprint 17: RunSeries annual storage + API tests."""

from uuid import uuid4

import pytest

from src.models.run import ResultSet


class TestResultSetSeriesFields:
    """ResultSet model accepts optional series fields."""

    def test_legacy_resultset_unchanged(self) -> None:
        """Existing ResultSet creation works with no series fields."""
        rs = ResultSet(
            run_id=uuid4(),
            metric_type="total_output",
            values={"F": 100.0},
        )
        assert rs.year is None
        assert rs.series_kind is None
        assert rs.baseline_run_id is None

    def test_annual_resultset(self) -> None:
        rs = ResultSet(
            run_id=uuid4(),
            metric_type="total_output",
            values={"F": 100.0},
            year=2026,
            series_kind="annual",
        )
        assert rs.year == 2026
        assert rs.series_kind == "annual"
        assert rs.baseline_run_id is None

    def test_peak_resultset(self) -> None:
        rs = ResultSet(
            run_id=uuid4(),
            metric_type="total_output",
            values={"F": 100.0},
            year=2028,
            series_kind="peak",
        )
        assert rs.year == 2028
        assert rs.series_kind == "peak"

    def test_delta_resultset(self) -> None:
        baseline_id = uuid4()
        rs = ResultSet(
            run_id=uuid4(),
            metric_type="total_output",
            values={"F": 50.0},
            year=2026,
            series_kind="delta",
            baseline_run_id=baseline_id,
        )
        assert rs.series_kind == "delta"
        assert rs.baseline_run_id == baseline_id

    def test_series_kind_validated(self) -> None:
        with pytest.raises(ValueError, match="series_kind"):
            ResultSet(
                run_id=uuid4(),
                metric_type="total_output",
                values={"F": 1.0},
                series_kind="invalid",
            )

    def test_annual_requires_year(self) -> None:
        with pytest.raises(ValueError, match="year"):
            ResultSet(
                run_id=uuid4(),
                metric_type="total_output",
                values={"F": 1.0},
                series_kind="annual",
                year=None,
            )

    def test_delta_requires_baseline(self) -> None:
        with pytest.raises(ValueError, match="baseline_run_id"):
            ResultSet(
                run_id=uuid4(),
                metric_type="total_output",
                values={"F": 1.0},
                series_kind="delta",
                year=2026,
                baseline_run_id=None,
            )
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/engine/test_runseries.py -q`
Expected: FAIL (ResultSet has no `year`, `series_kind`, `baseline_run_id` fields)

**Step 3: Implement model changes**

In `src/models/run.py`, add to `ResultSet` class (after line 66):

```python
class ResultSet(ImpactOSBase, frozen=True):
    """Immutable deterministic engine output per Section 5.3."""

    result_id: UUIDv7 = Field(default_factory=new_uuid7)
    run_id: UUID
    metric_type: str = Field(..., min_length=1)
    values: dict[str, float] = Field(
        ...,
        description="Metric values keyed by sector code or aggregate label.",
    )
    sector_breakdowns: dict[str, dict[str, float]] = Field(
        default_factory=dict,
    )
    # Sprint 17: RunSeries fields
    year: int | None = Field(default=None, description="Year for annual/peak/delta rows.")
    series_kind: str | None = Field(
        default=None,
        description="'annual', 'peak', or 'delta'. NULL for legacy cumulative.",
    )
    baseline_run_id: UUID | None = Field(
        default=None,
        description="Baseline run_id for delta series rows.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_series_fields(self) -> "ResultSet":
        kind = self.series_kind
        if kind is not None and kind not in ("annual", "peak", "delta"):
            raise ValueError(f"series_kind must be 'annual', 'peak', or 'delta', got '{kind}'")
        if kind is not None and self.year is None:
            raise ValueError(f"year is required when series_kind='{kind}'")
        if kind == "delta" and self.baseline_run_id is None:
            raise ValueError("baseline_run_id is required when series_kind='delta'")
        if kind != "delta" and self.baseline_run_id is not None:
            raise ValueError("baseline_run_id must be None unless series_kind='delta'")
        if kind is None and self.year is not None:
            raise ValueError("year must be None when series_kind is None (legacy row)")
        return self
```

Add `from pydantic import model_validator` to imports at top of file.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/engine/test_runseries.py -q`
Expected: 7 passed

**Step 5: Commit**

```bash
git add src/models/run.py tests/engine/test_runseries.py
git commit -m "[sprint17] extend ResultSet model with series fields (year, series_kind, baseline_run_id)"
```

---

### Task 2: Extend DB schema (ResultSetRow + Alembic migration)

**Files:**
- Modify: `src/db/tables.py:133-144`
- Create: `alembic/versions/012_runseries_columns.py`
- Test: `tests/repositories/test_engine.py` (append)

**Step 1: Write the failing test**

Append to `tests/repositories/test_engine.py`:

```python
class TestResultSetSeriesPersistence:
    """Sprint 17: series fields round-trip through repository."""

    async def test_annual_row_roundtrip(self, session: AsyncSession) -> None:
        repo = ResultSetRepository(session)
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 100.0},
            year=2026, series_kind="annual",
        )
        assert row.year == 2026
        assert row.series_kind == "annual"
        assert row.baseline_run_id is None

        rows = await repo.get_by_run(rid)
        assert len(rows) == 1
        assert rows[0].year == 2026

    async def test_legacy_row_has_null_series_fields(self, session: AsyncSession) -> None:
        repo = ResultSetRepository(session)
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 100.0},
        )
        assert row.year is None
        assert row.series_kind is None
        assert row.baseline_run_id is None

    async def test_delta_row_stores_baseline(self, session: AsyncSession) -> None:
        repo = ResultSetRepository(session)
        baseline_id = uuid4()
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 50.0},
            year=2026, series_kind="delta", baseline_run_id=baseline_id,
        )
        assert row.baseline_run_id == baseline_id
        assert row.series_kind == "delta"

    async def test_get_by_run_series(self, session: AsyncSession) -> None:
        """get_by_run_series returns only rows matching series_kind filter."""
        repo = ResultSetRepository(session)
        rid = uuid4()
        # Legacy row
        await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 100.0},
        )
        # Annual rows
        for y in (2026, 2027):
            await repo.create(
                result_id=uuid4(), run_id=rid,
                metric_type="total_output", values={"F": float(y)},
                year=y, series_kind="annual",
            )
        annual_rows = await repo.get_by_run_series(rid, series_kind="annual")
        assert len(annual_rows) == 2
        assert all(r.series_kind == "annual" for r in annual_rows)

        legacy_rows = await repo.get_by_run_series(rid, series_kind=None)
        assert len(legacy_rows) == 1
        assert legacy_rows[0].year is None
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/repositories/test_engine.py::TestResultSetSeriesPersistence -q`
Expected: FAIL (columns don't exist, `get_by_run_series` doesn't exist)

**Step 3: Implement schema + repository changes**

In `src/db/tables.py`, modify `ResultSetRow` (lines 133-144):

```python
class ResultSetRow(Base):
    """Immutable engine output — metric values and sector breakdowns."""

    __tablename__ = "result_sets"

    result_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    values = mapped_column(FlexJSON, nullable=False)
    sector_breakdowns = mapped_column(FlexJSON, nullable=False)
    # Sprint 17: RunSeries columns
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    baseline_run_id: Mapped[UUID | None] = mapped_column(nullable=True)
    workspace_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

In `src/repositories/engine.py`, update `ResultSetRepository.create()` (line 130) to accept optional series fields and add `get_by_run_series()`:

```python
class ResultSetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, result_id: UUID, run_id: UUID,
                     metric_type: str, values: dict,
                     sector_breakdowns: dict | None = None,
                     workspace_id: UUID | None = None,
                     year: int | None = None,
                     series_kind: str | None = None,
                     baseline_run_id: UUID | None = None) -> ResultSetRow:
        row = ResultSetRow(
            result_id=result_id, run_id=run_id,
            metric_type=metric_type, values=values,
            sector_breakdowns=sector_breakdowns or {},
            year=year, series_kind=series_kind,
            baseline_run_id=baseline_run_id,
            workspace_id=workspace_id,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_run(self, run_id: UUID) -> list[ResultSetRow]:
        result = await self._session.execute(
            select(ResultSetRow).where(ResultSetRow.run_id == run_id)
        )
        return list(result.scalars().all())

    async def get_by_run_series(
        self, run_id: UUID, *, series_kind: str | None,
    ) -> list[ResultSetRow]:
        """Get ResultSets for a run filtered by series_kind."""
        stmt = select(ResultSetRow).where(ResultSetRow.run_id == run_id)
        if series_kind is None:
            stmt = stmt.where(ResultSetRow.series_kind.is_(None))
        else:
            stmt = stmt.where(ResultSetRow.series_kind == series_kind)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

Create Alembic migration `alembic/versions/012_runseries_columns.py`:

```python
"""Add RunSeries columns to result_sets.

Revision ID: 012_runseries_columns
Revises: fa33e2cd9dda
"""
from alembic import op
import sqlalchemy as sa

revision = "012_runseries_columns"
down_revision = "fa33e2cd9dda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("result_sets", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("result_sets", sa.Column("series_kind", sa.String(20), nullable=True))
    op.add_column("result_sets", sa.Column("baseline_run_id", sa.dialects.postgresql.UUID(), nullable=True))

    # CHECK constraints
    op.execute("""
        ALTER TABLE result_sets ADD CONSTRAINT chk_series_kind
        CHECK (series_kind IN ('annual', 'peak', 'delta') OR series_kind IS NULL)
    """)
    op.execute("""
        ALTER TABLE result_sets ADD CONSTRAINT chk_year_required
        CHECK (
            (series_kind IS NULL AND year IS NULL)
            OR (series_kind IS NOT NULL AND year IS NOT NULL)
        )
    """)
    op.execute("""
        ALTER TABLE result_sets ADD CONSTRAINT chk_baseline_delta
        CHECK (
            (series_kind = 'delta' AND baseline_run_id IS NOT NULL)
            OR (series_kind != 'delta' AND baseline_run_id IS NULL)
            OR (series_kind IS NULL AND baseline_run_id IS NULL)
        )
    """)

    # Partial unique indexes
    op.create_index("uq_resultset_legacy", "result_sets",
                    ["run_id", "metric_type"],
                    unique=True, postgresql_where=sa.text("series_kind IS NULL"))
    op.create_index("uq_resultset_annual", "result_sets",
                    ["run_id", "metric_type", "year"],
                    unique=True, postgresql_where=sa.text("series_kind = 'annual'"))
    op.create_index("uq_resultset_peak", "result_sets",
                    ["run_id", "metric_type"],
                    unique=True, postgresql_where=sa.text("series_kind = 'peak'"))
    op.create_index("uq_resultset_delta", "result_sets",
                    ["run_id", "metric_type", "year", "baseline_run_id"],
                    unique=True, postgresql_where=sa.text("series_kind = 'delta'"))


def downgrade() -> None:
    op.drop_index("uq_resultset_delta", "result_sets")
    op.drop_index("uq_resultset_peak", "result_sets")
    op.drop_index("uq_resultset_annual", "result_sets")
    op.drop_index("uq_resultset_legacy", "result_sets")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_baseline_delta")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_year_required")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_series_kind")
    op.drop_column("result_sets", "baseline_run_id")
    op.drop_column("result_sets", "series_kind")
    op.drop_column("result_sets", "year")
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/repositories/test_engine.py::TestResultSetSeriesPersistence -q`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/db/tables.py src/repositories/engine.py alembic/versions/012_runseries_columns.py
git commit -m "[sprint17] add series columns to ResultSetRow with partial unique indexes"
```

---

### Task 3: Emit annual + peak rows from batch runner

**Files:**
- Modify: `src/engine/batch.py:102-353`
- Test: `tests/engine/test_runseries.py` (append)

**Step 1: Write the failing tests**

Append to `tests/engine/test_runseries.py`:

```python
class TestBatchRunnerAnnualEmission:
    """Batch runner emits annual + peak ResultSet rows."""

    def test_annual_rows_emitted(self) -> None:
        """Annual series rows present for total_output, direct, indirect."""
        # Use standard 3-sector, 3-year golden scenario
        result = _run_standard_batch()
        annual_rows = [r for r in result.result_sets if r.series_kind == "annual"]
        years = {r.year for r in annual_rows}
        assert years == {2026, 2027, 2028}
        metrics = {r.metric_type for r in annual_rows}
        assert {"total_output", "direct_effect", "indirect_effect"} <= metrics

    def test_annual_total_output_sums_to_cumulative(self) -> None:
        """Sum of annual total_output values == cumulative total_output values."""
        result = _run_standard_batch()
        cumulative = _find_rs(result, "total_output", series_kind=None)
        annual = _find_all_rs(result, "total_output", series_kind="annual")
        for sector in cumulative.values:
            annual_sum = sum(r.values[sector] for r in annual)
            assert abs(annual_sum - cumulative.values[sector]) < 1e-10

    def test_peak_row_emitted(self) -> None:
        """Peak row present with correct year."""
        result = _run_standard_batch()
        peak_rows = [r for r in result.result_sets if r.series_kind == "peak"]
        assert len(peak_rows) == 1
        assert peak_rows[0].metric_type == "total_output"
        assert peak_rows[0].year is not None

    def test_peak_values_match_annual(self) -> None:
        """Peak values match the annual row for peak year."""
        result = _run_standard_batch()
        peak = _find_rs(result, "total_output", series_kind="peak")
        annual = _find_rs(result, "total_output", series_kind="annual", year=peak.year)
        for sector, val in peak.values.items():
            assert abs(val - annual.values[sector]) < 1e-10

    def test_legacy_cumulative_unchanged(self) -> None:
        """Legacy cumulative rows (series_kind=None) still emitted."""
        result = _run_standard_batch()
        legacy = [r for r in result.result_sets if r.series_kind is None]
        legacy_metrics = {r.metric_type for r in legacy}
        assert "total_output" in legacy_metrics
        assert "employment" in legacy_metrics

    def test_annual_row_count(self) -> None:
        """3 years × 3 metrics = 9 annual rows + 1 peak = 10 series rows."""
        result = _run_standard_batch()
        annual = [r for r in result.result_sets if r.series_kind == "annual"]
        peak = [r for r in result.result_sets if r.series_kind == "peak"]
        assert len(annual) == 9  # 3 years * 3 metrics
        assert len(peak) == 1
```

Also add helper functions at the top of the test file:

```python
def _run_standard_batch() -> SingleRunResult:
    """Run standard 3-sector 3-year golden scenario."""
    # Setup model store + run batch (standard pattern from test_batch.py)
    ...

def _find_rs(result, metric_type, series_kind=None, year=None):
    """Find single ResultSet by metric/kind/year."""
    ...

def _find_all_rs(result, metric_type, series_kind=None):
    """Find all ResultSets by metric/kind."""
    ...
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/engine/test_runseries.py::TestBatchRunnerAnnualEmission -q`
Expected: FAIL (no annual/peak rows emitted)

**Step 3: Implement batch emission**

In `src/engine/batch.py`, add after the existing cumulative emission block (after line 187, before value measures):

```python
        # Sprint 17: Emit annual series rows
        _ANNUAL_METRICS = ("total_output", "direct_effect", "indirect_effect")
        for year in sorted(phased.annual_results):
            year_result = phased.annual_results[year]
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="total_output",
                values=self._vec_to_dict(year_result.delta_x_total, sector_codes),
                year=year,
                series_kind="annual",
            ))
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="direct_effect",
                values=self._vec_to_dict(year_result.delta_x_direct, sector_codes),
                year=year,
                series_kind="annual",
            ))
            result_sets.append(ResultSet(
                run_id=run_id,
                metric_type="indirect_effect",
                values=self._vec_to_dict(year_result.delta_x_indirect, sector_codes),
                year=year,
                series_kind="annual",
            ))

        # Peak-year row
        result_sets.append(ResultSet(
            run_id=run_id,
            metric_type="total_output",
            values=self._vec_to_dict(phased.peak_delta_x, sector_codes),
            year=phased.peak_year,
            series_kind="peak",
        ))
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/engine/test_runseries.py -q`
Expected: all passed

**Step 5: Commit**

```bash
git add src/engine/batch.py tests/engine/test_runseries.py
git commit -m "[sprint17] emit annual and peak series rows from batch runner"
```

---

### Task 4: Implement delta series computation + validation

**Files:**
- Create: `src/engine/runseries_delta.py`
- Test: `tests/engine/test_runseries.py` (append)

**Step 1: Write the failing tests**

Append to `tests/engine/test_runseries.py`:

```python
class TestRunSeriesValidationError:
    """RunSeriesValidationError has required fields."""

    def test_error_fields(self) -> None:
        from src.engine.runseries_delta import RunSeriesValidationError
        err = RunSeriesValidationError(
            reason_code="RS_BASELINE_NO_SERIES",
            message="Baseline has no annual series",
        )
        assert err.reason_code == "RS_BASELINE_NO_SERIES"
        assert "no annual series" in str(err).lower()

    def test_no_secret_leak(self) -> None:
        from src.engine.runseries_delta import RunSeriesValidationError
        err = RunSeriesValidationError(
            reason_code="RS_YEAR_MISMATCH",
            message="Years do not overlap",
        )
        assert "password" not in str(err).lower()


class TestDeltaSeriesComputation:
    """Deterministic delta = scenario - baseline per year per sector."""

    def test_delta_values(self) -> None:
        """Delta = scenario - baseline for each (year, metric, sector)."""
        from src.engine.runseries_delta import compute_delta_series
        scenario_annual = {
            2026: {"total_output": {"F": 150.0, "C": 250.0}},
            2027: {"total_output": {"F": 200.0, "C": 300.0}},
        }
        baseline_annual = {
            2026: {"total_output": {"F": 100.0, "C": 200.0}},
            2027: {"total_output": {"F": 120.0, "C": 220.0}},
        }
        delta = compute_delta_series(scenario_annual, baseline_annual)
        assert delta[2026]["total_output"]["F"] == pytest.approx(50.0)
        assert delta[2027]["total_output"]["C"] == pytest.approx(80.0)

    def test_delta_empty_overlap_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            compute_delta_series,
        )
        with pytest.raises(RunSeriesValidationError, match="RS_YEAR_MISMATCH"):
            compute_delta_series(
                {2026: {"total_output": {"F": 1.0}}},
                {2030: {"total_output": {"F": 1.0}}},
            )

    def test_delta_metric_mismatch_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            compute_delta_series,
        )
        with pytest.raises(RunSeriesValidationError, match="RS_BASELINE_METRIC_MISMATCH"):
            compute_delta_series(
                {2026: {"total_output": {"F": 1.0}}},
                {2026: {"employment": {"F": 1.0}}},
            )

    def test_delta_no_baseline_series_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            validate_baseline_has_series,
        )
        with pytest.raises(RunSeriesValidationError, match="RS_BASELINE_NO_SERIES"):
            validate_baseline_has_series([])  # no annual rows
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/engine/test_runseries.py::TestRunSeriesValidationError tests/engine/test_runseries.py::TestDeltaSeriesComputation -q`
Expected: FAIL (module doesn't exist)

**Step 3: Implement delta computation**

Create `src/engine/runseries_delta.py`:

```python
"""RunSeries delta computation — Sprint 17.

Deterministic scenario-vs-baseline delta per year per metric per sector.
No LLM calls, no side effects.
"""

from src.models.run import ResultSet


class RunSeriesValidationError(Exception):
    """Structured validation error for RunSeries operations."""

    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def validate_baseline_has_series(baseline_annual_rows: list[ResultSet]) -> None:
    """Validate that baseline run has annual series rows."""
    if not baseline_annual_rows:
        raise RunSeriesValidationError(
            reason_code="RS_BASELINE_NO_SERIES",
            message="Baseline run has no annual series rows. "
                    "Re-run baseline with Sprint 17+ engine to generate series.",
        )


AnnualData = dict[int, dict[str, dict[str, float]]]
# shape: {year: {metric_type: {sector: value}}}


def compute_delta_series(
    scenario_annual: AnnualData,
    baseline_annual: AnnualData,
) -> AnnualData:
    """Compute scenario - baseline delta for overlapping years and metrics.

    Returns:
        Delta data in same shape as input: {year: {metric: {sector: delta}}}.

    Raises:
        RunSeriesValidationError: If years or metrics don't overlap.
    """
    overlap_years = sorted(set(scenario_annual) & set(baseline_annual))
    if not overlap_years:
        raise RunSeriesValidationError(
            reason_code="RS_YEAR_MISMATCH",
            message=f"No overlapping years between scenario {sorted(scenario_annual)} "
                    f"and baseline {sorted(baseline_annual)}.",
        )

    delta: AnnualData = {}
    for year in overlap_years:
        s_metrics = scenario_annual[year]
        b_metrics = baseline_annual[year]
        overlap_metrics = set(s_metrics) & set(b_metrics)
        if not overlap_metrics:
            raise RunSeriesValidationError(
                reason_code="RS_BASELINE_METRIC_MISMATCH",
                message=f"No overlapping metrics for year {year}: "
                        f"scenario={sorted(s_metrics)}, baseline={sorted(b_metrics)}.",
            )
        delta[year] = {}
        for metric in sorted(overlap_metrics):
            delta[year][metric] = {}
            for sector in s_metrics[metric]:
                s_val = s_metrics[metric].get(sector, 0.0)
                b_val = b_metrics[metric].get(sector, 0.0)
                delta[year][metric][sector] = s_val - b_val
    return delta
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/engine/test_runseries.py -q`
Expected: all passed

**Step 5: Commit**

```bash
git add src/engine/runseries_delta.py tests/engine/test_runseries.py
git commit -m "[sprint17] add deterministic delta series computation with validation"
```

---

### Task 5: Wire delta series into batch runner

**Files:**
- Modify: `src/engine/batch.py` (add baseline_run_id to ScenarioInput, emit delta rows)
- Test: `tests/engine/test_runseries.py` (append delta batch tests)

**Step 1: Write the failing tests**

Append to `tests/engine/test_runseries.py`:

```python
class TestBatchRunnerDeltaSeries:
    """Batch runner emits delta ResultSet rows when baseline provided."""

    def test_delta_rows_emitted(self) -> None:
        """When baseline_run_id provided, delta rows appear."""
        # Run baseline first, then scenario with baseline_run_id
        baseline_result = _run_standard_batch()
        scenario_result = _run_standard_batch_with_baseline(baseline_result)
        delta_rows = [r for r in scenario_result.result_sets if r.series_kind == "delta"]
        assert len(delta_rows) > 0
        assert all(r.baseline_run_id is not None for r in delta_rows)

    def test_delta_values_correct(self) -> None:
        """Delta values = scenario annual - baseline annual."""
        baseline_result = _run_standard_batch()
        scenario_result = _run_standard_batch_with_baseline(
            baseline_result, shock_multiplier=2.0,
        )
        # For each delta row, verify it equals scenario_annual - baseline_annual
        for delta_row in (r for r in scenario_result.result_sets if r.series_kind == "delta"):
            year = delta_row.year
            metric = delta_row.metric_type
            scenario_annual = _find_rs(scenario_result, metric, series_kind="annual", year=year)
            baseline_annual = _find_rs(baseline_result, metric, series_kind="annual", year=year)
            for sector, dval in delta_row.values.items():
                expected = scenario_annual.values[sector] - baseline_annual.values[sector]
                assert abs(dval - expected) < 1e-10
```

**Step 2: Run, verify fail**
**Step 3: Implement in batch.py**

Add `baseline_run_id: UUID | None = None` and `baseline_annual_data: dict | None = None` to `ScenarioInput`. In `_execute_single`, after annual/peak emission, add delta emission logic.

**Step 4: Run, verify pass**
**Step 5: Commit**

```bash
git commit -m "[sprint17] wire delta series emission into batch runner"
```

---

### Task 6: API additive exposure — ResultSetResponse + include_series

**Files:**
- Modify: `src/api/runs.py` (ResultSetResponse, RunRequest, query params, persist/load series fields)
- Test: `tests/engine/test_api_runs.py` (append)

**Step 1: Write the failing tests**

Append to `tests/engine/test_api_runs.py`:

```python
class TestRunSeriesAPI:
    """Sprint 17: RunSeries API exposure."""

    async def test_run_response_has_series_fields(self, client, ...) -> None:
        """ResultSetResponse includes year/series_kind when include_series=true."""
        # POST run, then GET with ?include_series=true
        resp = await client.get(f".../{run_id}?include_series=true")
        data = resp.json()
        annual_rs = [r for r in data["result_sets"] if r.get("series_kind") == "annual"]
        assert len(annual_rs) > 0
        assert all(r["year"] is not None for r in annual_rs)

    async def test_default_response_excludes_series(self, client, ...) -> None:
        """Default (include_series not set) returns only legacy rows."""
        resp = await client.get(f".../{run_id}")
        data = resp.json()
        assert all(r.get("series_kind") is None for r in data["result_sets"])

    async def test_baseline_mismatch_returns_422(self, client, ...) -> None:
        """Invalid baseline_run_id returns 422."""
        resp = await client.post("...runs", json={
            ..., "baseline_run_id": str(uuid4()),
        })
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["reason_code"] == "RS_BASELINE_NOT_FOUND"

    async def test_delta_series_in_response(self, client, ...) -> None:
        """Delta series rows appear in response when baseline provided."""
        ...
```

**Step 2: Run, verify fail**
**Step 3: Implement API changes**

In `src/api/runs.py`:
- Add `year`, `series_kind`, `baseline_run_id` to `ResultSetResponse`
- Add `baseline_run_id` to `RunRequest` and `ScenarioPayload`
- Add `include_series: bool = False` query param to GET endpoints
- Filter result_sets in response: default returns only `series_kind IS NULL`; `include_series=true` returns all
- Update `_persist_run_result` to pass series fields
- Update `_load_run_response` to accept `include_series` flag
- Add `RunSeriesValidationError` catch in create_run/create_batch_run

**Step 4: Run, verify pass**
**Step 5: Commit**

```bash
git commit -m "[sprint17] expose additive RunSeries via API with include_series param"
```

---

### Task 7: Evidence docs + mathematical parity tests

**Files:**
- Modify: `docs/evidence/release-readiness-checklist.md` (append Sprint 17 section)
- Create: `tests/evidence/test_sprint17_evidence.py`
- Modify: `tests/integration/test_mathematical_accuracy.py` (append parity tests)

**Step 1: Write evidence tests**

Create `tests/evidence/test_sprint17_evidence.py`:

```python
"""Sprint 17 evidence: release-readiness-checklist references RunSeries."""
from pathlib import Path

def test_sprint17_section_exists() -> None:
    text = Path("docs/evidence/release-readiness-checklist.md").read_text()
    assert "Sprint 17" in text

def test_runseries_storage_shape_documented() -> None:
    text = Path("docs/evidence/release-readiness-checklist.md").read_text()
    assert "series_kind" in text
    assert "annual" in text and "peak" in text and "delta" in text

def test_reason_codes_documented() -> None:
    text = Path("docs/evidence/release-readiness-checklist.md").read_text()
    for code in ("RS_BASELINE_NOT_FOUND", "RS_BASELINE_NO_SERIES",
                  "RS_YEAR_MISMATCH", "RS_BASELINE_METRIC_MISMATCH"):
        assert code in text

def test_go_no_go_criteria() -> None:
    text = Path("docs/evidence/release-readiness-checklist.md").read_text()
    assert "go/no-go" in text.lower() or "Go / No-Go" in text
```

Append math parity tests to `tests/integration/test_mathematical_accuracy.py`:

```python
class TestRunSeriesMathematicalAccuracy:
    """Sprint 17: annual series arithmetic identities."""

    def test_cumulative_equals_annual_sum(self) -> None:
        """Legacy cumulative total_output == sum of annual total_output."""
        ...

    def test_peak_equals_max_annual(self) -> None:
        """Peak total_output values == values from max-impact annual year."""
        ...

    def test_delta_equals_scenario_minus_baseline(self) -> None:
        """Each delta row == corresponding scenario annual - baseline annual."""
        ...
```

**Step 2: Run, verify fail**
**Step 3: Write evidence doc + implement parity tests**
**Step 4: Run, verify pass**
**Step 5: Commit**

```bash
git commit -m "[sprint17] add mvp17 parity evidence and math accuracy tests"
```

---

### Task 8: Full verification + OpenAPI refresh

**Step 1: Run targeted Sprint 17 tests**

```bash
python -m pytest tests/engine/test_runseries.py tests/engine/test_api_runs.py tests/repositories/test_engine.py tests/evidence/test_sprint17_evidence.py tests/integration/test_mathematical_accuracy.py -q
```

**Step 2: Run full test suite**

```bash
python -m pytest tests -q
```
Expected: 4114 + N new tests, 0 failures.

**Step 3: Ruff lint**

```bash
python -m ruff check src tests
```

**Step 4: OpenAPI regenerate + validate**

```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```

**Step 5: Commit**

```bash
git add openapi.json
git commit -m "[sprint17] fix lint and regenerate openapi with runseries fields"
```

---

### Task 9: Push + open PR

```bash
git push -u origin phase2e-sprint17-runseries-annual-storage-api
gh pr create --title "Sprint 17: RunSeries Annual Storage + API (MVP-17)" --body "..."
```

PR body must include:
- RunSeries storage model summary
- Validation matrix (input → validation → fail mode → reason code)
- Output matrix (series type → meaning → retrieval path)
- Verification outputs summary
- Superpowers usage log (all 14)
