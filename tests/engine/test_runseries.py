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
