"""Tests for BenchmarkValidator (D-3).

Tests multiplier validation against benchmark data.
No live API calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data.benchmark_validator import (
    BenchmarkValidator,
    SectorComparison,
    ValidationReport,
)


class TestBenchmarkValidator:
    """Benchmark validation of computed vs published multipliers."""

    def _make_validator(self) -> BenchmarkValidator:
        return BenchmarkValidator()

    def test_perfect_match(self) -> None:
        """Identical values -> all within tolerance, PASS."""
        v = self._make_validator()
        computed = {"A": 1.5, "B": 1.3, "C": 1.8}
        benchmark = {"A": 1.5, "B": 1.3, "C": 1.8}
        report = v.validate_multipliers(computed, benchmark)
        assert report.overall_pass
        assert report.sectors_outside_tolerance == 0
        assert report.rmse == pytest.approx(0.0)

    def test_within_tolerance(self) -> None:
        """Small differences within 5% tolerance -> PASS."""
        v = self._make_validator()
        computed = {"A": 1.52, "B": 1.28}
        benchmark = {"A": 1.50, "B": 1.30}
        report = v.validate_multipliers(computed, benchmark, tolerance=0.05)
        assert report.overall_pass

    def test_outside_tolerance(self) -> None:
        """Large difference -> FAIL."""
        v = self._make_validator()
        computed = {"A": 1.50, "B": 1.80}
        benchmark = {"A": 1.50, "B": 1.30}
        report = v.validate_multipliers(computed, benchmark, tolerance=0.05)
        assert not report.overall_pass
        assert report.sectors_outside_tolerance >= 1

    def test_report_type(self) -> None:
        """Returns ValidationReport."""
        v = self._make_validator()
        report = v.validate_multipliers({"A": 1.0}, {"A": 1.0})
        assert isinstance(report, ValidationReport)

    def test_sector_comparison_type(self) -> None:
        """Each comparison is SectorComparison."""
        v = self._make_validator()
        report = v.validate_multipliers({"A": 1.0}, {"A": 1.0})
        assert isinstance(report.sector_comparisons[0], SectorComparison)

    def test_pct_diff_calculated(self) -> None:
        """Percentage difference calculated correctly."""
        v = self._make_validator()
        report = v.validate_multipliers({"A": 1.10}, {"A": 1.00})
        comp = report.sector_comparisons[0]
        assert comp.pct_diff == pytest.approx(0.10)

    def test_rmse_calculation(self) -> None:
        """RMSE computed correctly."""
        v = self._make_validator()
        computed = {"A": 1.1, "B": 1.3}
        benchmark = {"A": 1.0, "B": 1.2}
        report = v.validate_multipliers(computed, benchmark)
        # RMSE of [0.1, 0.1] = 0.1
        assert report.rmse == pytest.approx(0.1)

    def test_mae_calculation(self) -> None:
        """MAE computed correctly."""
        v = self._make_validator()
        computed = {"A": 1.1, "B": 1.4}
        benchmark = {"A": 1.0, "B": 1.2}
        report = v.validate_multipliers(computed, benchmark)
        # MAE of [0.1, 0.2] = 0.15
        assert report.mae == pytest.approx(0.15)

    def test_missing_sectors_warned(self) -> None:
        """Sectors in one but not other produce warnings."""
        v = self._make_validator()
        computed = {"A": 1.5, "B": 1.3, "X": 2.0}
        benchmark = {"A": 1.5, "B": 1.3, "Y": 1.8}
        report = v.validate_multipliers(computed, benchmark)
        assert len(report.warnings) >= 2
        assert report.total_sectors == 2  # Only A, B are common

    def test_tolerance_parameter(self) -> None:
        """Custom tolerance used."""
        v = self._make_validator()
        computed = {"A": 1.10}
        benchmark = {"A": 1.00}
        # 10% diff, 15% tolerance -> pass
        report = v.validate_multipliers(computed, benchmark, tolerance=0.15)
        assert report.overall_pass
        assert report.tolerance_used == pytest.approx(0.15)

    def test_load_benchmark_from_file(self, tmp_path: Path) -> None:
        """Load benchmark from curated JSON."""
        data = {
            "sectors": [
                {"sector_code": "A", "output_multiplier": 1.45},
                {"sector_code": "B", "output_multiplier": 1.28},
            ],
        }
        path = tmp_path / "bench.json"
        path.write_text(json.dumps(data))

        v = self._make_validator()
        result = v.load_benchmark_from_file(path)
        assert result == {"A": 1.45, "B": 1.28}

    def test_format_report(self) -> None:
        """Format report produces readable text."""
        v = self._make_validator()
        report = v.validate_multipliers(
            {"A": 1.5, "B": 1.3},
            {"A": 1.5, "B": 1.4},
        )
        text = v.format_report(report)
        assert "Multiplier Benchmark Validation" in text
        assert "RMSE" in text

    def test_empty_inputs(self) -> None:
        """Empty inputs -> empty report, not PASS."""
        v = self._make_validator()
        report = v.validate_multipliers({}, {})
        assert report.total_sectors == 0
        assert not report.overall_pass
