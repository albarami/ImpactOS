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
