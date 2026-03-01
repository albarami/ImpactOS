"""Data loader + computation smoke test.

Loads the 20-sector Saudi IO model via load_real_saudi_io() and runs it
through the core computation stack with plausibility validation. Tests
explicitly report whether curated KAPSARC data or synthetic fallback was
used — Amendment 5 (real-data coverage) is deferred until curated GASTAT
data is committed to the repo.

Note: As of Phase 2 gate, only synthetic data is available. These tests
validate the loader→engine pipeline, NOT that real curated data was used.
"""

import warnings
import numpy as np
import pytest
from uuid_extensions import uuid7

from .golden_scenarios.shared import ISIC_20_SECTIONS


@pytest.mark.integration
class TestDataLoaderSmoke:
    """Smoke test: load_real_saudi_io() → Leontief → Satellite pipeline."""

    # ---------------------------------------------------------------
    # Test 9c-1: Leontief + Satellite on real model
    # ---------------------------------------------------------------

    def test_leontief_satellite_on_loaded_model(self):
        """Load 20-sector model, run Leontief + Satellite, check plausibility.

        Runs a 100M SAR shock in Construction (F) through the full
        computation stack: load -> register -> Leontief solve ->
        satellite impacts. Validates that all outputs are finite,
        non-negative, and economically sensible.

        Explicitly reports whether curated or synthetic data was loaded.
        """
        from src.data.io_loader import load_satellites_from_json
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore
        from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model = load_real_saudi_io()

        # Detect whether curated or synthetic data was loaded
        used_synthetic = any(
            "synthetic" in str(w.message).lower() for w in caught
        )
        is_synthetic_source = "synthetic" in model.source.lower()
        if used_synthetic or is_synthetic_source:
            pytest.warns_msg = (
                "SYNTHETIC FALLBACK: No curated KAPSARC/GASTAT data available. "
                "This test validates the loader→engine pipeline only, "
                "not real-data coverage (Amendment 5 deferred)."
            )
            warnings.warn(pytest.warns_msg, UserWarning, stacklevel=1)
        assert len(model.sector_codes) == 20

        # Register and load
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="real-data-smoke",
        )
        loaded = store.get(mv.model_version_id)

        # Run Leontief with 100M SAR shock in Construction (F)
        f_idx = model.sector_codes.index("F")
        delta_d = np.zeros(20)
        delta_d[f_idx] = 100.0  # 100M SAR shock

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # Leontief output checks
        assert solve_result.delta_x_total is not None
        assert all(np.isfinite(solve_result.delta_x_total))
        assert np.all(solve_result.delta_x_total >= 0)

        # Output multiplier should be >= 1.0 (Leontief theory)
        total_output = float(solve_result.delta_x_total.sum())
        assert total_output >= 100.0, (
            f"Total output {total_output:.2f} < input shock 100.0"
        )

        # Direct effect should equal the shock
        assert abs(solve_result.delta_x_direct[f_idx] - 100.0) < 1e-6

        # Indirect effects should be non-negative
        assert np.all(solve_result.delta_x_indirect >= -1e-10)

        # Run satellite impacts
        sat_data = load_satellites_from_json(
            "data/curated/saudi_satellites_synthetic_v1.json",
        )
        sat_coefficients = SatelliteCoefficients(
            jobs_coeff=sat_data.jobs_coeff,
            import_ratio=sat_data.import_ratio,
            va_ratio=sat_data.va_ratio,
            version_id=uuid7(),
        )

        sat_calc = SatelliteAccounts()
        sat_result = sat_calc.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coefficients,
        )

        # Satellite output checks
        assert all(np.isfinite(sat_result.delta_jobs))
        assert all(np.isfinite(sat_result.delta_imports))
        assert all(np.isfinite(sat_result.delta_va))

        # Jobs should be positive (at least some employment impact)
        total_jobs = float(sat_result.delta_jobs.sum())
        assert total_jobs > 0, f"Total jobs {total_jobs} should be positive"

        # Value added should be positive
        total_va = float(sat_result.delta_va.sum())
        assert total_va > 0, f"Total VA {total_va} should be positive"

        # Domestic output = total output - imports
        expected_domestic = solve_result.delta_x_total - sat_result.delta_imports
        np.testing.assert_allclose(
            sat_result.delta_domestic_output,
            expected_domestic,
            rtol=1e-10,
        )

    # ---------------------------------------------------------------
    # Test 9c-2: Real model has 20 sectors
    # ---------------------------------------------------------------

    def test_loaded_model_has_20_sectors(self):
        """The loaded model must have exactly 20 ISIC Rev.4 section codes.

        Verifies that sector codes match the standard A-T set and that
        Z matrix and x vector dimensions are consistent.
        Works on both curated and synthetic models.
        """
        from src.data.real_io_loader import load_real_saudi_io

        model = load_real_saudi_io()

        # Exact 20 sectors
        assert len(model.sector_codes) == 20, (
            f"Expected 20 sectors, got {len(model.sector_codes)}"
        )
        assert sorted(model.sector_codes) == sorted(ISIC_20_SECTIONS), (
            f"Sector codes {sorted(model.sector_codes)} != "
            f"expected {sorted(ISIC_20_SECTIONS)}"
        )

        # Z matrix must be 20x20
        assert model.Z.shape == (20, 20), (
            f"Z shape {model.Z.shape} != expected (20, 20)"
        )

        # x vector must have 20 elements
        assert model.x.shape == (20,), (
            f"x shape {model.x.shape} != expected (20,)"
        )

        # All x values should be positive (no zero-output sectors)
        assert np.all(model.x > 0), (
            "Some sectors have zero or negative output"
        )

        # Z should be non-negative
        assert np.all(model.Z >= 0), "Z has negative entries"

    # ---------------------------------------------------------------
    # Test 9c-3: All multipliers finite and positive
    # ---------------------------------------------------------------

    def test_all_multipliers_finite_and_positive(self):
        """Every sector's Type I output multiplier is finite and >= 1.0.

        Runs a unit shock in each of the 20 sectors and verifies:
        1. All output changes are finite
        2. Output multiplier >= 1.0 (Leontief theory: direct + indirect >= direct)
        3. No NaN or Inf values in any result vector
        """
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="multiplier-check",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        for i, sector in enumerate(model.sector_codes):
            delta_d = np.zeros(20)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded, delta_d=delta_d)

            # All values must be finite
            assert all(np.isfinite(result.delta_x_total)), (
                f"Sector {sector}: delta_x_total contains non-finite values"
            )
            assert all(np.isfinite(result.delta_x_direct)), (
                f"Sector {sector}: delta_x_direct contains non-finite values"
            )
            assert all(np.isfinite(result.delta_x_indirect)), (
                f"Sector {sector}: delta_x_indirect contains non-finite values"
            )

            # Output multiplier >= 1.0
            multiplier = float(result.delta_x_total.sum())
            assert multiplier >= 1.0, (
                f"Sector {sector}: output multiplier {multiplier:.4f} < 1.0 "
                "(should be >= 1.0 by Leontief theory)"
            )

            # All sector output changes should be non-negative
            assert np.all(result.delta_x_total >= -1e-10), (
                f"Sector {sector}: negative output changes detected"
            )
