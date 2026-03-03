"""Sprint 17: RunSeries annual storage + API tests."""

from uuid import uuid4

import pytest

from src.models.run import ResultSet


class TestResultSetSeriesFields:
    """ResultSet model accepts optional series fields."""

    def test_legacy_resultset_unchanged(self) -> None:
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


# ---------------------------------------------------------------------------
# Sprint 17 Task 2: Persistence round-trip tests
# ---------------------------------------------------------------------------

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.engine import ResultSetRepository


class TestResultSetSeriesPersistence:
    """Sprint 17: series fields round-trip through repository."""

    @pytest.mark.anyio
    async def test_annual_row_roundtrip(self, db_session: AsyncSession) -> None:
        repo = ResultSetRepository(db_session)
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

    @pytest.mark.anyio
    async def test_legacy_row_has_null_series_fields(self, db_session: AsyncSession) -> None:
        repo = ResultSetRepository(db_session)
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 100.0},
        )
        assert row.year is None
        assert row.series_kind is None
        assert row.baseline_run_id is None

    @pytest.mark.anyio
    async def test_delta_row_stores_baseline(self, db_session: AsyncSession) -> None:
        repo = ResultSetRepository(db_session)
        baseline_id = uuid4()
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 50.0},
            year=2026, series_kind="delta", baseline_run_id=baseline_id,
        )
        assert row.baseline_run_id == baseline_id
        assert row.series_kind == "delta"

    @pytest.mark.anyio
    async def test_get_by_run_series(self, db_session: AsyncSession) -> None:
        """get_by_run_series returns only rows matching series_kind filter."""
        repo = ResultSetRepository(db_session)
        rid = uuid4()
        await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 100.0},
        )
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

    @pytest.mark.anyio
    async def test_peak_row_roundtrip(self, db_session: AsyncSession) -> None:
        repo = ResultSetRepository(db_session)
        rid = uuid4()
        row = await repo.create(
            result_id=uuid4(), run_id=rid,
            metric_type="total_output", values={"F": 200.0},
            year=2028, series_kind="peak",
        )
        assert row.year == 2028
        assert row.series_kind == "peak"


# ---------------------------------------------------------------------------
# Sprint 17 Task 3: Batch runner annual + peak emission tests
# ---------------------------------------------------------------------------

import numpy as np
from uuid_extensions import uuid7

from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput, SingleRunResult
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients


def _run_standard_batch() -> SingleRunResult:
    """Run a 3-year multi-year scenario through the batch runner.

    Mirrors the pattern in test_batch.py: creates a 2-sector ModelStore,
    registers a model, creates a ScenarioInput with 3 years of annual shocks,
    and runs the BatchRunner.  Returns the SingleRunResult for assertions.
    """
    store = ModelStore()
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"],
        base_year=2023, source="test-annual",
    )

    coefficients = SatelliteCoefficients(
        jobs_coeff=np.array([0.01, 0.005]),
        import_ratio=np.array([0.30, 0.20]),
        va_ratio=np.array([0.40, 0.55]),
        version_id=uuid7(),
    )

    scenario = ScenarioInput(
        scenario_spec_id=uuid7(),
        scenario_spec_version=1,
        name="multi-year",
        annual_shocks={
            2024: np.array([100.0, 0.0]),
            2025: np.array([200.0, 50.0]),
            2026: np.array([50.0, 25.0]),
        },
        base_year=2023,
    )

    version_refs = {
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }

    runner = BatchRunner(model_store=store)
    request = BatchRequest(
        scenarios=[scenario],
        model_version_id=mv.model_version_id,
        satellite_coefficients=coefficients,
        version_refs=version_refs,
    )
    result = runner.run(request)
    return result.run_results[0]


class TestBatchRunnerAnnualEmission:
    """Batch runner emits annual + peak ResultSet rows."""

    def test_annual_rows_emitted(self) -> None:
        """Annual series rows present for total_output, direct, indirect."""
        result = _run_standard_batch()
        annual_rows = [r for r in result.result_sets if r.series_kind == "annual"]
        years = {r.year for r in annual_rows}
        metrics = {r.metric_type for r in annual_rows}
        assert len(years) >= 2  # multi-year scenario
        assert {"total_output", "direct_effect", "indirect_effect"} <= metrics

    def test_annual_total_output_sums_to_cumulative(self) -> None:
        """Sum of annual total_output values == cumulative total_output values per sector."""
        result = _run_standard_batch()
        cumulative = next(
            r for r in result.result_sets
            if r.metric_type == "total_output" and r.series_kind is None
        )
        annual = [
            r for r in result.result_sets
            if r.metric_type == "total_output" and r.series_kind == "annual"
        ]
        for sector in cumulative.values:
            annual_sum = sum(r.values[sector] for r in annual)
            assert abs(annual_sum - cumulative.values[sector]) < 1e-10

    def test_peak_row_emitted(self) -> None:
        """Peak row present with series_kind='peak'."""
        result = _run_standard_batch()
        peak_rows = [r for r in result.result_sets if r.series_kind == "peak"]
        assert len(peak_rows) == 1
        assert peak_rows[0].metric_type == "total_output"
        assert peak_rows[0].year is not None

    def test_peak_values_match_annual(self) -> None:
        """Peak values match the annual row for peak year."""
        result = _run_standard_batch()
        peak = next(r for r in result.result_sets if r.series_kind == "peak")
        annual = next(
            r for r in result.result_sets
            if r.metric_type == "total_output"
            and r.series_kind == "annual"
            and r.year == peak.year
        )
        for sector, val in peak.values.items():
            assert abs(val - annual.values[sector]) < 1e-10

    def test_legacy_cumulative_unchanged(self) -> None:
        """Legacy cumulative rows (series_kind=None) still emitted."""
        result = _run_standard_batch()
        legacy = [r for r in result.result_sets if r.series_kind is None]
        legacy_metrics = {r.metric_type for r in legacy}
        assert "total_output" in legacy_metrics
        assert "employment" in legacy_metrics


# ---------------------------------------------------------------------------
# Sprint 17 Task 4: RunSeries delta computation tests
# ---------------------------------------------------------------------------


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

    def test_delta_partial_year_overlap(self) -> None:
        """When only some years overlap, only overlapping years appear in result."""
        from src.engine.runseries_delta import compute_delta_series
        scenario = {
            2026: {"total_output": {"F": 100.0}},
            2027: {"total_output": {"F": 200.0}},
        }
        baseline = {
            2027: {"total_output": {"F": 150.0}},
            2028: {"total_output": {"F": 300.0}},
        }
        delta = compute_delta_series(scenario, baseline)
        assert list(delta.keys()) == [2027]
        assert delta[2027]["total_output"]["F"] == pytest.approx(50.0)

    def test_delta_empty_overlap_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            compute_delta_series,
        )
        with pytest.raises(RunSeriesValidationError) as exc_info:
            compute_delta_series(
                {2026: {"total_output": {"F": 1.0}}},
                {2030: {"total_output": {"F": 1.0}}},
            )
        assert exc_info.value.reason_code == "RS_YEAR_MISMATCH"

    def test_delta_metric_mismatch_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            compute_delta_series,
        )
        with pytest.raises(RunSeriesValidationError) as exc_info:
            compute_delta_series(
                {2026: {"total_output": {"F": 1.0}}},
                {2026: {"employment": {"F": 1.0}}},
            )
        assert exc_info.value.reason_code == "RS_BASELINE_METRIC_MISMATCH"

    def test_baseline_no_series_raises(self) -> None:
        from src.engine.runseries_delta import (
            RunSeriesValidationError,
            validate_baseline_has_series,
        )
        with pytest.raises(RunSeriesValidationError) as exc_info:
            validate_baseline_has_series([])
        assert exc_info.value.reason_code == "RS_BASELINE_NO_SERIES"

    def test_baseline_with_series_passes(self) -> None:
        from src.engine.runseries_delta import validate_baseline_has_series
        # Should not raise
        validate_baseline_has_series(["some_row"])

    def test_delta_multi_metric(self) -> None:
        """Delta works across multiple metric types in same year."""
        from src.engine.runseries_delta import compute_delta_series
        scenario = {2026: {
            "total_output": {"F": 100.0},
            "direct_effect": {"F": 60.0},
        }}
        baseline = {2026: {
            "total_output": {"F": 80.0},
            "direct_effect": {"F": 50.0},
        }}
        delta = compute_delta_series(scenario, baseline)
        assert delta[2026]["total_output"]["F"] == pytest.approx(20.0)
        assert delta[2026]["direct_effect"]["F"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Sprint 17 Task 5: Batch runner delta series emission tests
# ---------------------------------------------------------------------------


def _run_batch_with_baseline(
    baseline_result: SingleRunResult,
    shock_multiplier: float = 1.0,
) -> SingleRunResult:
    """Run a scenario with baseline_run_id, extracting baseline annual data.

    Uses the same 2-sector model as _run_standard_batch() but passes
    baseline_run_id and baseline_annual_data extracted from baseline_result.
    """
    # Extract baseline annual data from baseline_result into the dict shape
    baseline_annual_data: dict[int, dict[str, dict[str, float]]] = {}
    for rs in baseline_result.result_sets:
        if rs.series_kind == "annual" and rs.year is not None:
            baseline_annual_data.setdefault(rs.year, {})[rs.metric_type] = dict(rs.values)

    store = ModelStore()
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"],
        base_year=2023, source="test-delta",
    )

    coefficients = SatelliteCoefficients(
        jobs_coeff=np.array([0.01, 0.005]),
        import_ratio=np.array([0.30, 0.20]),
        va_ratio=np.array([0.40, 0.55]),
        version_id=uuid7(),
    )

    scenario = ScenarioInput(
        scenario_spec_id=uuid7(),
        scenario_spec_version=1,
        name="delta-scenario",
        annual_shocks={
            2024: np.array([100.0 * shock_multiplier, 0.0]),
            2025: np.array([200.0 * shock_multiplier, 50.0 * shock_multiplier]),
            2026: np.array([50.0 * shock_multiplier, 25.0 * shock_multiplier]),
        },
        base_year=2023,
        baseline_run_id=baseline_result.snapshot.run_id,
        baseline_annual_data=baseline_annual_data,
    )

    version_refs = {
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }

    runner = BatchRunner(model_store=store)
    request = BatchRequest(
        scenarios=[scenario],
        model_version_id=mv.model_version_id,
        satellite_coefficients=coefficients,
        version_refs=version_refs,
    )
    result = runner.run(request)
    return result.run_results[0]


class TestBatchRunnerDeltaSeries:
    """Batch runner emits delta ResultSet rows when baseline provided."""

    def test_delta_rows_emitted(self) -> None:
        """When baseline_run_id provided, delta rows appear."""
        baseline_result = _run_standard_batch()
        scenario_result = _run_batch_with_baseline(baseline_result)
        delta_rows = [r for r in scenario_result.result_sets if r.series_kind == "delta"]
        assert len(delta_rows) > 0
        assert all(r.baseline_run_id is not None for r in delta_rows)

    def test_delta_values_correct(self) -> None:
        """Delta values = scenario annual - baseline annual per sector."""
        baseline_result = _run_standard_batch()
        scenario_result = _run_batch_with_baseline(baseline_result, shock_multiplier=2.0)
        for delta_row in (r for r in scenario_result.result_sets if r.series_kind == "delta"):
            year = delta_row.year
            metric = delta_row.metric_type
            scenario_annual = next(
                r for r in scenario_result.result_sets
                if r.metric_type == metric and r.series_kind == "annual" and r.year == year
            )
            baseline_annual = next(
                r for r in baseline_result.result_sets
                if r.metric_type == metric and r.series_kind == "annual" and r.year == year
            )
            for sector, dval in delta_row.values.items():
                expected = scenario_annual.values[sector] - baseline_annual.values[sector]
                assert abs(dval - expected) < 1e-10

    def test_no_delta_without_baseline(self) -> None:
        """Without baseline_run_id, no delta rows emitted."""
        result = _run_standard_batch()
        delta_rows = [r for r in result.result_sets if r.series_kind == "delta"]
        assert len(delta_rows) == 0

    def test_delta_row_count(self) -> None:
        """3 years overlap x 3 metrics = 9 delta rows."""
        baseline_result = _run_standard_batch()
        scenario_result = _run_batch_with_baseline(baseline_result)
        delta_rows = [r for r in scenario_result.result_sets if r.series_kind == "delta"]
        # 3 years * 3 metrics (total_output, direct_effect, indirect_effect)
        assert len(delta_rows) == 9
