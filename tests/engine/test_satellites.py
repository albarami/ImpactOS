"""Tests for satellite accounts (MVP-3 Section 7.5).

Covers: employment impacts (jobs_coeff · Δx), import leakage (import_ratio · Δx),
value-added (va_ratio · Δx), coefficient versioning.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.model_store import ModelStore
from src.engine.leontief import LeontiefSolver
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients, SatelliteResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _register_2x2(store: ModelStore) -> tuple:
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"],
        base_year=2023, source="test",
    )
    loaded = store.get(mv.model_version_id)
    return mv, loaded


def _make_coefficients_2() -> SatelliteCoefficients:
    """2-sector satellite coefficients."""
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.01, 0.005]),      # jobs per unit output
        import_ratio=np.array([0.30, 0.20]),      # import fraction
        va_ratio=np.array([0.40, 0.55]),          # value-added fraction
        version_id=uuid7(),
    )


# ===================================================================
# Employment impacts
# ===================================================================


class TestEmploymentImpacts:
    """Δjobs = diag(jobs_coeff) · Δx."""

    def test_employment_computation(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()
        sat = SatelliteAccounts()

        delta_d = np.array([100.0, 0.0])
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        coeffs = _make_coefficients_2()

        result = sat.compute(delta_x=solve_result.delta_x_total, coefficients=coeffs)
        expected_jobs = coeffs.jobs_coeff * solve_result.delta_x_total
        np.testing.assert_array_almost_equal(result.delta_jobs, expected_jobs)

    def test_zero_shock_zero_jobs(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        result = sat.compute(delta_x=np.zeros(2), coefficients=coeffs)
        np.testing.assert_array_almost_equal(result.delta_jobs, np.zeros(2))

    def test_employment_non_negative(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()
        sat = SatelliteAccounts()

        delta_d = np.array([100.0, 50.0])
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        coeffs = _make_coefficients_2()
        result = sat.compute(delta_x=solve_result.delta_x_total, coefficients=coeffs)
        assert np.all(result.delta_jobs >= 0)


# ===================================================================
# Import leakage
# ===================================================================


class TestImportLeakage:
    """Δimports = diag(import_ratio) · Δx."""

    def test_import_computation(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        delta_x = np.array([200.0, 300.0])

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        expected_imports = coeffs.import_ratio * delta_x
        np.testing.assert_array_almost_equal(result.delta_imports, expected_imports)

    def test_domestic_output(self) -> None:
        """Δdomestic = Δx - Δimports."""
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        delta_x = np.array([200.0, 300.0])

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        expected_domestic = delta_x - result.delta_imports
        np.testing.assert_array_almost_equal(result.delta_domestic_output, expected_domestic)

    def test_imports_le_total_output(self) -> None:
        """Imports should not exceed total output per sector."""
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        delta_x = np.array([200.0, 300.0])

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        assert np.all(result.delta_imports <= delta_x + 1e-12)


# ===================================================================
# Value-added
# ===================================================================


class TestValueAdded:
    """ΔVA = diag(va_ratio) · Δx."""

    def test_va_computation(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        delta_x = np.array([200.0, 300.0])

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        expected_va = coeffs.va_ratio * delta_x
        np.testing.assert_array_almost_equal(result.delta_va, expected_va)

    def test_va_non_negative(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        delta_x = np.array([200.0, 300.0])

        result = sat.compute(delta_x=delta_x, coefficients=coeffs)
        assert np.all(result.delta_va >= 0)


# ===================================================================
# Coefficient versioning
# ===================================================================


class TestCoefficientVersioning:
    """Satellite coefficients carry a version_id for traceability."""

    def test_version_id_stored(self) -> None:
        coeffs = _make_coefficients_2()
        assert coeffs.version_id is not None

    def test_result_carries_version_id(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        result = sat.compute(delta_x=np.array([100.0, 100.0]), coefficients=coeffs)
        assert result.coefficients_version_id == coeffs.version_id


# ===================================================================
# Dimension validation
# ===================================================================


class TestDimensionValidation:
    """Satellite accounts validates dimension consistency."""

    def test_mismatched_dimensions_raises(self) -> None:
        sat = SatelliteAccounts()
        coeffs = _make_coefficients_2()
        with pytest.raises(ValueError, match="dimension"):
            sat.compute(delta_x=np.array([100.0, 200.0, 300.0]), coefficients=coeffs)
