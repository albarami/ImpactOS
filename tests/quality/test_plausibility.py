"""Tests for PlausibilityChecker -- multiplier plausibility validation.

Covers: all-in-range, above-range, below-range, no-benchmark,
cache hit/miss/none, mixed 3x3 matrix, single sector.

TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.quality.models import PlausibilityStatus
from src.quality.plausibility import (
    PlausibilityChecker,
    PlausibilityResult,
    SectorPlausibilityDetail,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture
def checker() -> PlausibilityChecker:
    """Default PlausibilityChecker instance."""
    return PlausibilityChecker()


# ===================================================================
# All sectors in range
# ===================================================================


class TestAllInRange:
    """All sectors within benchmark ranges."""

    def test_100_pct_empty_flagged(self, checker: PlausibilityChecker) -> None:
        """2 sectors both in range -> 100%, no flagged sectors."""
        B = np.diag([1.5, 2.0])
        sectors = ["S1", "S2"]
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.5, 2.5)}

        result = checker.check(B, sectors, benchmarks)

        assert isinstance(result, PlausibilityResult)
        assert result.multipliers_in_range_pct == pytest.approx(100.0)
        assert result.flagged_sectors == []
        assert len(result.sector_details) == 2

    def test_sector_details_content(self, checker: PlausibilityChecker) -> None:
        """Verify detail fields for in-range sector."""
        B = np.diag([1.5])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 2.0)}

        result = checker.check(B, sectors, benchmarks)
        detail = result.sector_details[0]

        assert detail.sector_code == "S1"
        assert detail.output_multiplier == pytest.approx(1.5)
        assert detail.benchmark_low == pytest.approx(1.0)
        assert detail.benchmark_high == pytest.approx(2.0)
        assert detail.status == PlausibilityStatus.IN_RANGE


# ===================================================================
# One above range
# ===================================================================


class TestAboveRange:
    """Sector multiplier exceeds benchmark high."""

    def test_one_above_50_pct(self, checker: PlausibilityChecker) -> None:
        """2 benchmarked sectors, 1 above -> 50% in range."""
        B = np.diag([1.5, 3.5])
        sectors = ["S1", "S2"]
        benchmarks = {"S1": (1.0, 2.0), "S2": (1.0, 3.0)}

        result = checker.check(B, sectors, benchmarks)

        assert result.multipliers_in_range_pct == pytest.approx(50.0)
        assert "S2" in result.flagged_sectors
        assert "S1" not in result.flagged_sectors

    def test_above_range_status(self, checker: PlausibilityChecker) -> None:
        """Above-range sector has ABOVE_RANGE status."""
        B = np.diag([5.0])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 3.0)}

        result = checker.check(B, sectors, benchmarks)
        detail = result.sector_details[0]

        assert detail.status == PlausibilityStatus.ABOVE_RANGE


# ===================================================================
# One below range
# ===================================================================


class TestBelowRange:
    """Sector multiplier below benchmark low."""

    def test_below_range_status(self, checker: PlausibilityChecker) -> None:
        """Below-range sector has BELOW_RANGE status."""
        B = np.diag([0.5])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 3.0)}

        result = checker.check(B, sectors, benchmarks)
        detail = result.sector_details[0]

        assert detail.status == PlausibilityStatus.BELOW_RANGE
        assert "S1" in result.flagged_sectors
        assert result.multipliers_in_range_pct == pytest.approx(0.0)


# ===================================================================
# No benchmark for a sector
# ===================================================================


class TestNoBenchmark:
    """Sector has no benchmark data."""

    def test_no_benchmark_status(self, checker: PlausibilityChecker) -> None:
        """Sector not in benchmarks dict -> NO_BENCHMARK."""
        B = np.diag([1.5, 2.0])
        sectors = ["S1", "S2"]
        benchmarks = {"S1": (1.0, 2.0)}  # S2 has no benchmark

        result = checker.check(B, sectors, benchmarks)

        s2_detail = [d for d in result.sector_details if d.sector_code == "S2"][0]
        assert s2_detail.status == PlausibilityStatus.NO_BENCHMARK
        assert s2_detail.benchmark_low is None
        assert s2_detail.benchmark_high is None

    def test_no_benchmark_excluded_from_pct(
        self, checker: PlausibilityChecker
    ) -> None:
        """NO_BENCHMARK sectors excluded from percentage denominator."""
        B = np.diag([1.5, 2.0])
        sectors = ["S1", "S2"]
        benchmarks = {"S1": (1.0, 2.0)}  # S2 has no benchmark

        result = checker.check(B, sectors, benchmarks)

        # Only S1 is benchmarked and in range -> 100%
        assert result.multipliers_in_range_pct == pytest.approx(100.0)

    def test_no_benchmark_not_flagged(self, checker: PlausibilityChecker) -> None:
        """NO_BENCHMARK sectors are not flagged."""
        B = np.diag([1.5, 2.0])
        sectors = ["S1", "S2"]
        benchmarks = {"S1": (1.0, 2.0)}

        result = checker.check(B, sectors, benchmarks)

        assert "S2" not in result.flagged_sectors


# ===================================================================
# All sectors no benchmark
# ===================================================================


class TestAllNoBenchmark:
    """All sectors lack benchmarks."""

    def test_all_no_benchmark_100_pct(self, checker: PlausibilityChecker) -> None:
        """No benchmarked sectors -> 100% (no issues detectable)."""
        B = np.diag([1.5, 2.0])
        sectors = ["S1", "S2"]
        benchmarks: dict[str, tuple[float, float]] = {}

        result = checker.check(B, sectors, benchmarks)

        assert result.multipliers_in_range_pct == pytest.approx(100.0)
        assert result.flagged_sectors == []


# ===================================================================
# Correct sector_details length and content
# ===================================================================


class TestSectorDetails:
    """Verify sector_details completeness."""

    def test_details_length_matches_sectors(
        self, checker: PlausibilityChecker
    ) -> None:
        """sector_details has one entry per sector."""
        B = np.diag([1.0, 2.0, 3.0])
        sectors = ["A", "B", "C"]
        benchmarks = {"A": (0.5, 1.5), "C": (2.5, 3.5)}

        result = checker.check(B, sectors, benchmarks)

        assert len(result.sector_details) == 3
        codes = [d.sector_code for d in result.sector_details]
        assert codes == ["A", "B", "C"]


# ===================================================================
# Cache behavior
# ===================================================================


class TestCaching:
    """Amendment 13: per-model caching."""

    def test_cache_hit_returns_same_object(
        self, checker: PlausibilityChecker
    ) -> None:
        """Cached result returns the exact same object (identity check)."""
        B = np.diag([1.5])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 2.0)}

        r1 = checker.check(B, sectors, benchmarks, model_version_id="v1")
        r2 = checker.check(B, sectors, benchmarks, model_version_id="v1")

        assert r1 is r2

    def test_cache_miss_different_model(
        self, checker: PlausibilityChecker
    ) -> None:
        """Different model_version_id -> different result objects."""
        B = np.diag([1.5])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 2.0)}

        r1 = checker.check(B, sectors, benchmarks, model_version_id="v1")
        r2 = checker.check(B, sectors, benchmarks, model_version_id="v2")

        assert r1 is not r2

    def test_no_cache_when_none(self, checker: PlausibilityChecker) -> None:
        """model_version_id=None -> no caching, always fresh."""
        B = np.diag([1.5])
        sectors = ["S1"]
        benchmarks = {"S1": (1.0, 2.0)}

        r1 = checker.check(B, sectors, benchmarks, model_version_id=None)
        r2 = checker.check(B, sectors, benchmarks, model_version_id=None)

        assert r1 is not r2


# ===================================================================
# 3x3 matrix with mixed results
# ===================================================================


class TestMixedMatrix:
    """3x3 matrix with in-range, above, and below sectors."""

    def test_3x3_mixed(self, checker: PlausibilityChecker) -> None:
        """S1 in range, S2 above, S3 below -> 1/3 in range ~33.33%."""
        B = np.diag([2.0, 5.0, 0.5])
        sectors = ["S1", "S2", "S3"]
        benchmarks = {
            "S1": (1.0, 3.0),  # 2.0 in [1.0, 3.0] -> IN_RANGE
            "S2": (1.0, 3.0),  # 5.0 > 3.0 -> ABOVE_RANGE
            "S3": (1.0, 3.0),  # 0.5 < 1.0 -> BELOW_RANGE
        }

        result = checker.check(B, sectors, benchmarks)

        assert result.multipliers_in_range_pct == pytest.approx(100.0 / 3.0)
        assert sorted(result.flagged_sectors) == ["S2", "S3"]
        assert len(result.sector_details) == 3

        details_by_code = {d.sector_code: d for d in result.sector_details}
        assert details_by_code["S1"].status == PlausibilityStatus.IN_RANGE
        assert details_by_code["S2"].status == PlausibilityStatus.ABOVE_RANGE
        assert details_by_code["S3"].status == PlausibilityStatus.BELOW_RANGE


# ===================================================================
# Single sector
# ===================================================================


class TestSingleSector:
    """Edge case: only one sector."""

    def test_single_sector_in_range(self, checker: PlausibilityChecker) -> None:
        """Single sector in range -> 100%."""
        B = np.array([[2.0]])
        sectors = ["ONLY"]
        benchmarks = {"ONLY": (1.0, 3.0)}

        result = checker.check(B, sectors, benchmarks)

        assert result.multipliers_in_range_pct == pytest.approx(100.0)
        assert result.flagged_sectors == []
        assert len(result.sector_details) == 1
        assert result.sector_details[0].sector_code == "ONLY"
        assert result.sector_details[0].output_multiplier == pytest.approx(2.0)

    def test_single_sector_flagged(self, checker: PlausibilityChecker) -> None:
        """Single sector above range -> 0%, flagged."""
        B = np.array([[5.0]])
        sectors = ["ONLY"]
        benchmarks = {"ONLY": (1.0, 3.0)}

        result = checker.check(B, sectors, benchmarks)

        assert result.multipliers_in_range_pct == pytest.approx(0.0)
        assert result.flagged_sectors == ["ONLY"]
