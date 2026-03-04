"""Performance benchmarks — reference measurements (Amendment 6).

Marked @pytest.mark.slow and @pytest.mark.performance.
Skipped by default in CI. Run with: pytest -m performance

These are REFERENCE benchmarks, not hard gates.
"""

import time

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.quality.service import QualityAssessmentService
from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.integration
class TestPerformanceBenchmarks:
    """Performance reference benchmarks (informational, not gate criteria)."""

    def test_single_scenario_under_2s(self):
        """Single scenario completes in < 2 seconds (3-sector)."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="perf",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )

        start = time.perf_counter()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)
        sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"Single scenario took {elapsed:.2f}s (>2s)"

    def test_batch_10_scenarios_under_10s(self):
        """10 scenarios complete in < 10 seconds."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="perf-batch",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()

        start = time.perf_counter()
        for i in range(10):
            delta_d = np.array([100.0 + i * 10, 50.0 + i * 5, 25.0 + i * 2])
            solver.solve(loaded_model=loaded, delta_d=delta_d)
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"10 scenarios took {elapsed:.2f}s (>10s)"

    def test_quality_assessment_under_1s(self):
        """Quality assessment completes in < 1 second."""
        qas = QualityAssessmentService()

        start = time.perf_counter()
        qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            mapping_residual_pct=0.03, mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.8, assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 8, "ESTIMATED": 2, "ASSUMED": 0},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0, plausibility_flagged_count=1,
            source_ages=[], run_id=uuid7(),
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Quality assessment took {elapsed:.2f}s (>1s)"
