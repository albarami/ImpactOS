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
