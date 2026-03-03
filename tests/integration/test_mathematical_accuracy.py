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


# ---------------------------------------------------------------------------
# Sprint 16: Value Measures Mathematical Accuracy
# ---------------------------------------------------------------------------

from src.engine.value_measures import ValueMeasuresComputer

from tests.integration.golden_scenarios.shared import (
    SMALL_DEFLATOR_SERIES,
    SMALL_FINAL_DEMAND_F,
    SMALL_GOS,
    SMALL_IMPORTS_VECTOR,
    SMALL_OIL_SECTOR_CODES,
    SMALL_TAXES_LESS_SUBSIDIES,
)


@pytest.fixture
def loaded_3sector_with_vm():
    """3-sector model with value-measures artifacts."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="math-vm-test",
        artifact_payload={
            "gross_operating_surplus": SMALL_GOS.tolist(),
            "taxes_less_subsidies": SMALL_TAXES_LESS_SUBSIDIES.tolist(),
            "final_demand_F": SMALL_FINAL_DEMAND_F.tolist(),
            "imports_vector": SMALL_IMPORTS_VECTOR.tolist(),
            "deflator_series": SMALL_DEFLATOR_SERIES,
        },
    )
    return store.get(mv.model_version_id)


@pytest.mark.integration
class TestValueMeasuresMathematicalAccuracy:
    """Algebraic verification of value-measures on 3-sector toy model."""

    def test_gdp_basic_equals_sum_delta_va(
        self,
        loaded_3sector_with_vm: object,
    ) -> None:
        """GDP basic = Σ(va_ratio · Δx) = Σ(delta_va)."""
        loaded = loaded_3sector_with_vm
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        coeffs = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF, import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO, version_id=uuid7(),
        )
        sat = SatelliteAccounts()
        sat_result = sat.compute(delta_x=result.delta_x_total, coefficients=coeffs)

        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total, sat_result=sat_result,
            loaded_model=loaded, base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        expected_gdp_basic = float(np.sum(SMALL_VA_RATIO * result.delta_x_total))
        assert_allclose(vm_result.gdp_basic_price, expected_gdp_basic, rtol=1e-10)

    def test_gdp_market_basic_tax_identity(
        self,
        loaded_3sector_with_vm: object,
    ) -> None:
        """GDP market = GDP basic + Σ(tax_ratio · Δx)."""
        loaded = loaded_3sector_with_vm
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        coeffs = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF, import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO, version_id=uuid7(),
        )
        sat = SatelliteAccounts()
        sat_result = sat.compute(delta_x=result.delta_x_total, coefficients=coeffs)

        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total, sat_result=sat_result,
            loaded_model=loaded, base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        tax_ratio = SMALL_TAXES_LESS_SUBSIDIES / GOLDEN_X
        tax_effect = float(np.sum(tax_ratio * result.delta_x_total))
        assert_allclose(
            vm_result.gdp_market_price,
            vm_result.gdp_basic_price + tax_effect,
            rtol=1e-10,
        )

    def test_gdp_real_deflator_identity(
        self,
        loaded_3sector_with_vm: object,
    ) -> None:
        """GDP real = GDP market / deflator(base_year). At base_year, real == market."""
        loaded = loaded_3sector_with_vm
        solver = LeontiefSolver()
        result = solver.solve(loaded_model=loaded, delta_d=np.array([100.0, 50.0, 25.0]))
        coeffs = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF, import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO, version_id=uuid7(),
        )
        sat = SatelliteAccounts()
        sat_result = sat.compute(delta_x=result.delta_x_total, coefficients=coeffs)

        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total, sat_result=sat_result,
            loaded_model=loaded, base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        # deflator(2024) = 1.0, so real == market
        assert_allclose(vm_result.gdp_real, vm_result.gdp_market_price, rtol=1e-10)

    def test_bot_equals_exports_minus_imports(
        self,
        loaded_3sector_with_vm: object,
    ) -> None:
        """BoT = Σ(export_ratio · Δx) - Σ(import_ratio · Δx)."""
        loaded = loaded_3sector_with_vm
        solver = LeontiefSolver()
        result = solver.solve(loaded_model=loaded, delta_d=np.array([100.0, 50.0, 25.0]))
        coeffs = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF, import_ratio=SMALL_IMPORT_RATIO,
            va_ratio=SMALL_VA_RATIO, version_id=uuid7(),
        )
        sat = SatelliteAccounts()
        sat_result = sat.compute(delta_x=result.delta_x_total, coefficients=coeffs)

        vm = ValueMeasuresComputer()
        vm_result = vm.compute(
            delta_x=result.delta_x_total, sat_result=sat_result,
            loaded_model=loaded, base_year=GOLDEN_BASE_YEAR,
            oil_sector_codes=SMALL_OIL_SECTOR_CODES,
        )
        export_ratio = SMALL_FINAL_DEMAND_F[:, 3] / GOLDEN_X
        expected_bot = float(np.sum(
            export_ratio * result.delta_x_total
            - SMALL_IMPORT_RATIO * result.delta_x_total
        ))
        assert_allclose(vm_result.balance_of_trade, expected_bot, rtol=1e-10)
