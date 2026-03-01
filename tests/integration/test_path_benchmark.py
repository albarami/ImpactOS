"""Integration Path 9: Benchmark Validator Integration.

Tests that the 20-sector Saudi IO model (curated or synthetic) produces
Leontief multipliers that pass benchmark plausibility validation:
  load_real_saudi_io() -> LeontiefSolver.solve -> BenchmarkValidator.validate_multipliers

Checks multiplier ranges, outlier flags, and comparison against known
Saudi economic benchmarks. Currently runs on synthetic fallback data —
real-data coverage deferred until curated GASTAT data is committed.
"""

import numpy as np
import pytest

from .golden_scenarios.shared import ISIC_20_SECTIONS


@pytest.mark.integration
class TestBenchmarkValidatorIntegration:
    """Benchmark validation of Leontief multipliers on loaded 20-sector model."""

    # ---------------------------------------------------------------
    # Test 9b-1: Multipliers in plausible range
    # ---------------------------------------------------------------

    def test_benchmark_multipliers_in_plausible_range(self):
        """Multipliers from 20-sector model are within plausible ranges.

        Loads the real (or synthetic) IO model, registers it, runs
        Leontief with a unit shock in each sector, computes output
        multipliers (column sums of B), and validates that they fall
        within economically plausible bounds [1.0, 5.0].
        """
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        assert len(model.sector_codes) == 20

        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="benchmark-test",
        )
        loaded = store.get(mv.model_version_id)

        # Compute output multiplier for each sector (column sums of B)
        solver = LeontiefSolver()
        computed_multipliers: dict[str, float] = {}

        for i, sector in enumerate(model.sector_codes):
            delta_d = np.zeros(20)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded, delta_d=delta_d)
            multiplier = float(result.delta_x_total.sum())
            computed_multipliers[sector] = multiplier

        # All multipliers should be in [1.0, 5.0] for a reasonable IO model
        for sector, mult in computed_multipliers.items():
            assert 1.0 <= mult <= 5.0, (
                f"Sector {sector}: multiplier {mult:.4f} outside "
                f"plausible range [1.0, 5.0]"
            )

    # ---------------------------------------------------------------
    # Test 9b-2: Benchmark validates real model
    # ---------------------------------------------------------------

    def test_benchmark_validates_real_model(self):
        """BenchmarkValidator passes when computed == benchmark (self-test).

        Validates that the BenchmarkValidator works correctly by
        comparing a model's multipliers against themselves (should
        produce 0% difference and overall pass).
        """
        from src.data.benchmark_validator import BenchmarkValidator
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="benchmark-self-test",
        )
        loaded = store.get(mv.model_version_id)

        # Compute multipliers
        solver = LeontiefSolver()
        computed: dict[str, float] = {}
        for i, sector in enumerate(model.sector_codes):
            delta_d = np.zeros(20)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded, delta_d=delta_d)
            computed[sector] = float(result.delta_x_total.sum())

        # Self-compare: computed == benchmark should always pass
        validator = BenchmarkValidator()
        report = validator.validate_multipliers(
            computed=computed,
            benchmark=computed,  # same values as benchmark
            tolerance=0.05,
        )

        assert report.overall_pass, (
            f"Self-benchmark failed! Max % diff: {report.max_pct_diff:.4%}. "
            f"Sectors outside tolerance: {report.sectors_outside_tolerance}"
        )
        assert report.rmse < 1e-10, f"Self-benchmark RMSE={report.rmse} (should be ~0)"
        assert report.mae < 1e-10, f"Self-benchmark MAE={report.mae} (should be ~0)"

    # ---------------------------------------------------------------
    # Test 9b-3: Benchmark flags outliers on extreme model
    # ---------------------------------------------------------------

    def test_benchmark_flags_outliers_on_extreme_model(self):
        """BenchmarkValidator correctly detects outliers when multipliers diverge.

        Creates two multiplier dicts: one from the real model, and one
        with deliberately inflated values. The validator should flag
        the extreme sectors as outside tolerance.
        """
        from src.data.benchmark_validator import BenchmarkValidator
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="benchmark-extreme-test",
        )
        loaded = store.get(mv.model_version_id)

        # Compute real multipliers
        solver = LeontiefSolver()
        real_multipliers: dict[str, float] = {}
        for i, sector in enumerate(model.sector_codes):
            delta_d = np.zeros(20)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded, delta_d=delta_d)
            real_multipliers[sector] = float(result.delta_x_total.sum())

        # Create extreme multipliers: multiply some by 2x
        extreme_multipliers = dict(real_multipliers)
        # Pick first 3 sectors and double their multipliers
        tampered_sectors = model.sector_codes[:3]
        for sector in tampered_sectors:
            extreme_multipliers[sector] = real_multipliers[sector] * 2.0

        validator = BenchmarkValidator()
        report = validator.validate_multipliers(
            computed=extreme_multipliers,
            benchmark=real_multipliers,
            tolerance=0.05,
        )

        # Should NOT pass overall (tampered sectors diverge by ~100%)
        assert not report.overall_pass, (
            "Validator should fail when multipliers diverge by 100%"
        )
        assert report.sectors_outside_tolerance >= len(tampered_sectors), (
            f"Expected >= {len(tampered_sectors)} outliers, "
            f"got {report.sectors_outside_tolerance}"
        )

        # The tampered sectors should appear in failing comparisons
        failing_sectors = {
            c.sector_code
            for c in report.sector_comparisons
            if not c.within_tolerance
        }
        for sector in tampered_sectors:
            assert sector in failing_sectors, (
                f"Tampered sector {sector} not flagged as outlier"
            )
