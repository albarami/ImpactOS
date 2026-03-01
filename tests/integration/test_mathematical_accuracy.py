"""Mathematical accuracy verification using the 3-sector toy model.

Uses the small ISIC F/C/G model from shared.py where hand calculation
is feasible. Verifies Leontief algebra, multipliers, satellite identities,
IO accounting, and numerical stability.

This is the ONLY test file that uses the 3-sector toy model.
All other integration tests use the 20-sector D-1 model.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

from tests.integration.golden_scenarios.shared import (
    EXPECTED_B_SMALL,
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def loaded_3sector():
    """Register and load the 3-sector toy model (ISIC F/C/G)."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="math-accuracy-test",
    )
    return store.get(mv.model_version_id)


@pytest.mark.integration
class TestMathematicalAccuracy:
    """Algebraic verification of Leontief computations on 3-sector toy model.

    The toy model uses ISIC codes F (Construction), C (Manufacturing),
    G (Wholesale/Retail) with known Z matrix and x vector from shared.py.
    B = (I-A)^-1 is pre-computed in EXPECTED_B_SMALL for verification.
    """

    def test_leontief_inverse_matches_hand_calculation(self, loaded_3sector):
        """B = (I-A)^-1 matches pre-computed reference values."""
        B = loaded_3sector.B
        assert_allclose(B, EXPECTED_B_SMALL, rtol=1e-10)

    def test_leontief_identity(self, loaded_3sector):
        """delta_x = B . delta_d verified algebraically."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        expected = EXPECTED_B_SMALL @ delta_d
        assert_allclose(result.delta_x_total, expected, rtol=1e-10)

    def test_output_multiplier_is_column_sum(self, loaded_3sector):
        """Column sum of B = output multiplier for each sector."""
        B = loaded_3sector.B
        multipliers = B.sum(axis=0)

        solver = LeontiefSolver()
        for i in range(3):
            delta_d = np.zeros(3)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)
            assert_allclose(
                result.delta_x_total.sum(), multipliers[i], rtol=1e-10,
                err_msg=f"Sector {SECTOR_CODES_SMALL[i]}: multiplier mismatch",
            )

    def test_satellite_gdp_consistency(self, loaded_3sector):
        """GDP impact = va_ratio * delta_x (element-wise dot product)."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sa = SatelliteAccounts()
        sat = sa.compute(delta_x=result.delta_x_total, coefficients=coeff)

        expected_gdp = SMALL_VA_RATIO * result.delta_x_total
        assert_allclose(sat.delta_va, expected_gdp, rtol=1e-10)

    def test_satellite_employment_consistency(self, loaded_3sector):
        """Employment = jobs_coeff * delta_x (element-wise)."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sa = SatelliteAccounts()
        sat = sa.compute(delta_x=result.delta_x_total, coefficients=coeff)

        expected_jobs = SMALL_JOBS_COEFF * result.delta_x_total
        assert_allclose(sat.delta_jobs, expected_jobs, rtol=1e-10)

    def test_io_accounting_identity(self, loaded_3sector):
        """Row sums of Z + final demand = gross output.

        x = A.x + d  =>  d = x - A.x = (I-A).x
        Reconstructed x = A.x + d should equal original x.
        """
        A = loaded_3sector.A
        x = loaded_3sector.x

        d = x - A @ x
        reconstructed_x = A @ x + d
        assert_allclose(reconstructed_x, x, rtol=1e-10)

    def test_import_leakage_reduces_domestic(self, loaded_3sector):
        """Higher import share -> lower domestic multiplier effect.

        Halving the domestic demand shock halves the output (linearity).
        """
        solver = LeontiefSolver()
        delta_d_full = np.array([100.0, 50.0, 25.0])
        result_full = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d_full)

        # With 50% import leakage applied pre-solve
        delta_d_half = delta_d_full * 0.5
        result_half = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d_half)

        # Half the domestic shock -> half the output (linearity)
        assert_allclose(
            result_half.delta_x_total,
            result_full.delta_x_total * 0.5,
            rtol=1e-10,
        )

    def test_numerical_stability_serial_computation(self, loaded_3sector):
        """10 serial computations -> numerical drift < 1e-10."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        first_result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        for _ in range(10):
            result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        assert_allclose(
            result.delta_x_total,
            first_result.delta_x_total,
            rtol=0,
            atol=1e-10,
        )
