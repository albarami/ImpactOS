"""Multiplier Plausibility Checker (MVP-13, Task 7).

Validates Leontief output multipliers against sector-level benchmark
ranges and flags out-of-range sectors.  Supports per-model caching
(Amendment 13).

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.quality.models import PlausibilityStatus


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectorPlausibilityDetail:
    """Per-sector plausibility check result."""

    sector_code: str
    output_multiplier: float
    benchmark_low: float | None
    benchmark_high: float | None
    status: PlausibilityStatus


@dataclass(frozen=True)
class PlausibilityResult:
    """Aggregate plausibility result across all sectors."""

    multipliers_in_range_pct: float  # 0.0 - 100.0
    flagged_sectors: list[str]
    sector_details: list[SectorPlausibilityDetail]


# ---------------------------------------------------------------------------
# PlausibilityChecker
# ---------------------------------------------------------------------------


class PlausibilityChecker:
    """Validate Leontief multipliers against benchmark ranges.

    Extracts output multipliers from the diagonal of the provided
    B-matrix and checks each against optional sector benchmarks.

    Amendment 13: results are cached per *model_version_id* so
    repeated calls with the same model version return the identical
    (cached) :class:`PlausibilityResult` object.
    """

    def __init__(self) -> None:
        self._cache: dict[str, PlausibilityResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        B_matrix: np.ndarray,
        sector_codes: list[str],
        benchmarks: dict[str, tuple[float, float]],
        model_version_id: str | None = None,
    ) -> PlausibilityResult:
        """Check multiplier plausibility for every sector.

        Parameters
        ----------
        B_matrix:
            Square matrix whose diagonal elements ``B[i, i]`` are the
            output multipliers for each sector *i*.
        sector_codes:
            Ordered list of sector identifiers matching the matrix rows.
        benchmarks:
            Mapping of ``sector_code -> (low, high)`` benchmark bounds.
            Sectors absent from this dict receive
            :pyattr:`PlausibilityStatus.NO_BENCHMARK`.
        model_version_id:
            Optional cache key.  When provided, a cached result for the
            same key is returned immediately (identity-preserving).

        Returns
        -------
        PlausibilityResult
        """
        # 1. Cache lookup
        if model_version_id is not None and model_version_id in self._cache:
            return self._cache[model_version_id]

        # 2. Extract diagonal multipliers
        multipliers = np.diag(B_matrix)

        # 3. Evaluate each sector
        details: list[SectorPlausibilityDetail] = []
        flagged: list[str] = []
        in_range_count = 0
        benchmarked_count = 0

        for i, code in enumerate(sector_codes):
            mult = float(multipliers[i])

            if code not in benchmarks:
                details.append(
                    SectorPlausibilityDetail(
                        sector_code=code,
                        output_multiplier=mult,
                        benchmark_low=None,
                        benchmark_high=None,
                        status=PlausibilityStatus.NO_BENCHMARK,
                    )
                )
                continue

            low, high = benchmarks[code]
            benchmarked_count += 1

            if mult < low:
                status = PlausibilityStatus.BELOW_RANGE
                flagged.append(code)
            elif mult > high:
                status = PlausibilityStatus.ABOVE_RANGE
                flagged.append(code)
            else:
                status = PlausibilityStatus.IN_RANGE
                in_range_count += 1

            details.append(
                SectorPlausibilityDetail(
                    sector_code=code,
                    output_multiplier=mult,
                    benchmark_low=low,
                    benchmark_high=high,
                    status=status,
                )
            )

        # 4. Compute percentage
        if benchmarked_count == 0:
            pct = 100.0
        else:
            pct = in_range_count / benchmarked_count * 100.0

        result = PlausibilityResult(
            multipliers_in_range_pct=pct,
            flagged_sectors=flagged,
            sector_details=details,
        )

        # 5. Cache if model_version_id provided
        if model_version_id is not None:
            self._cache[model_version_id] = result

        return result
