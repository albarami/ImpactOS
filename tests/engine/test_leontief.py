"""Tests for core Leontief solver (MVP-3 Sections 7.2, 7.3, 7.4).

Covers: Δx = B·Δd, direct/indirect decomposition, multi-year phasing,
deflation, deterministic reproducibility.
"""

import numpy as np
import pytest

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import LoadedModel, ModelStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _register_2x2(store: ModelStore) -> tuple:
    """Register a 2-sector model and return (model_version, loaded)."""
    Z = np.array([[150.0, 500.0],
                   [200.0, 100.0]])
    x = np.array([1000.0, 2000.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"],
        base_year=2023, source="test",
    )
    loaded = store.get(mv.model_version_id)
    return mv, loaded


def _register_3x3(store: ModelStore) -> tuple:
    """Register a 3-sector model."""
    Z = np.array([
        [10.0, 20.0, 5.0],
        [15.0, 5.0,  10.0],
        [5.0,  10.0, 2.0],
    ])
    x = np.array([100.0, 80.0, 50.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2", "S3"],
        base_year=2023, source="test",
    )
    loaded = store.get(mv.model_version_id)
    return mv, loaded


# ===================================================================
# Basic shock propagation: Δx = B · Δd
# ===================================================================


class TestShockPropagation:
    """Δx = B · Δd produces correct total output changes."""

    def test_zero_shock_produces_zero_output(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([0.0, 0.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        np.testing.assert_array_almost_equal(result.delta_x_total, np.zeros(2))

    def test_single_sector_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 0.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # Δx = B · Δd, verify against manual computation
        expected = loaded.B @ delta_d
        np.testing.assert_array_almost_equal(result.delta_x_total, expected)

    def test_multi_sector_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 200.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        expected = loaded.B @ delta_d
        np.testing.assert_array_almost_equal(result.delta_x_total, expected)

    def test_3x3_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_3x3(store)
        solver = LeontiefSolver()

        delta_d = np.array([50.0, 30.0, 20.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        expected = loaded.B @ delta_d
        np.testing.assert_array_almost_equal(result.delta_x_total, expected)

    def test_total_output_ge_shock(self) -> None:
        """Total output change must be >= the shock itself (multiplier >= 1)."""
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 0.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        assert result.delta_x_total[0] >= delta_d[0]

    def test_dimension_mismatch_raises(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        with pytest.raises(ValueError, match="dimension"):
            solver.solve(loaded_model=loaded, delta_d=np.array([100.0, 200.0, 300.0]))


# ===================================================================
# Decomposition: direct vs indirect (Section 7.3)
# ===================================================================


class TestDecomposition:
    """Direct = Δd, Indirect = (B-I)·Δd, Total = Direct + Indirect."""

    def test_direct_equals_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        np.testing.assert_array_almost_equal(result.delta_x_direct, delta_d)

    def test_indirect_equals_B_minus_I_times_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        expected_indirect = (loaded.B - np.eye(2)) @ delta_d
        np.testing.assert_array_almost_equal(result.delta_x_indirect, expected_indirect)

    def test_direct_plus_indirect_equals_total(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        np.testing.assert_array_almost_equal(
            result.delta_x_direct + result.delta_x_indirect,
            result.delta_x_total,
        )

    def test_indirect_is_non_negative(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 0.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        assert np.all(result.delta_x_indirect >= -1e-12)

    def test_3x3_decomposition(self) -> None:
        store = ModelStore()
        _, loaded = _register_3x3(store)
        solver = LeontiefSolver()

        delta_d = np.array([50.0, 30.0, 20.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        np.testing.assert_array_almost_equal(
            result.delta_x_direct + result.delta_x_indirect,
            result.delta_x_total,
        )


# ===================================================================
# Multi-year phasing with deflation (Section 7.4)
# ===================================================================


class TestMultiYearPhasing:
    """Phased scenarios with annual shocks and deflation."""

    def test_single_year_matches_basic_solve(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        basic = solver.solve(loaded_model=loaded, delta_d=delta_d)

        annual_shocks = {2026: delta_d}
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        np.testing.assert_array_almost_equal(
            phased.annual_results[2026].delta_x_total,
            basic.delta_x_total,
        )

    def test_multi_year_produces_annual_results(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        annual_shocks = {
            2026: np.array([100.0, 0.0]),
            2027: np.array([200.0, 50.0]),
            2028: np.array([150.0, 75.0]),
        }
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        assert set(phased.annual_results.keys()) == {2026, 2027, 2028}

    def test_cumulative_is_sum_of_annual(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        annual_shocks = {
            2026: np.array([100.0, 0.0]),
            2027: np.array([200.0, 50.0]),
        }
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        expected_cumulative = (
            phased.annual_results[2026].delta_x_total
            + phased.annual_results[2027].delta_x_total
        )
        np.testing.assert_array_almost_equal(
            phased.cumulative_delta_x, expected_cumulative,
        )

    def test_peak_year_is_max(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        annual_shocks = {
            2026: np.array([100.0, 0.0]),
            2027: np.array([300.0, 0.0]),
            2028: np.array([50.0, 0.0]),
        }
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        # Peak total output should come from 2027 (largest shock)
        totals_by_year = {
            y: float(np.sum(r.delta_x_total))
            for y, r in phased.annual_results.items()
        }
        assert phased.peak_year == max(totals_by_year, key=totals_by_year.get)

    def test_deflation_reduces_real_shock(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        nominal_shock = np.array([100.0, 0.0])
        # 5% annual deflator means 2027 shock (4 years from base 2023)
        # is deflated: real = nominal / (1.05)^4
        annual_shocks = {2027: nominal_shock}
        deflators = {2027: 1.05 ** 4}

        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
            deflators=deflators,
        )
        # Without deflation the total would be larger
        no_deflation = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        assert float(np.sum(phased.cumulative_delta_x)) < float(
            np.sum(no_deflation.cumulative_delta_x)
        )


# ===================================================================
# Deterministic reproducibility
# ===================================================================


class TestReproducibility:
    """Same inputs always produce same outputs."""

    def test_repeated_solve_identical(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        r1 = solver.solve(loaded_model=loaded, delta_d=delta_d)
        r2 = solver.solve(loaded_model=loaded, delta_d=delta_d)
        np.testing.assert_array_equal(r1.delta_x_total, r2.delta_x_total)

    def test_repeated_phased_identical(self) -> None:
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        annual_shocks = {2026: np.array([100.0, 0.0]), 2027: np.array([200.0, 50.0])}
        p1 = solver.solve_phased(loaded_model=loaded, annual_shocks=annual_shocks, base_year=2023)
        p2 = solver.solve_phased(loaded_model=loaded, annual_shocks=annual_shocks, base_year=2023)
        np.testing.assert_array_equal(p1.cumulative_delta_x, p2.cumulative_delta_x)


# ===================================================================
# Type II field extensions (Sprint 15 — Task 1)
# ===================================================================


from src.engine.leontief import PhasedResult, SolveResult


class TestTypeIIFieldDefaults:
    """SolveResult and PhasedResult optional Type II fields default to None."""

    def test_solve_result_type_ii_defaults_none(self) -> None:
        """New Type II fields default to None when not provided."""
        result = SolveResult(
            delta_x_total=np.array([1.0, 2.0]),
            delta_x_direct=np.array([1.0, 0.0]),
            delta_x_indirect=np.array([0.0, 2.0]),
        )
        assert result.delta_x_type_ii_total is None
        assert result.delta_x_induced is None

    def test_solve_result_accepts_type_ii_values(self) -> None:
        """SolveResult can be constructed with Type II values."""
        t2_total = np.array([1.5, 2.5])
        induced = np.array([0.5, 0.5])
        result = SolveResult(
            delta_x_total=np.array([1.0, 2.0]),
            delta_x_direct=np.array([1.0, 0.0]),
            delta_x_indirect=np.array([0.0, 2.0]),
            delta_x_type_ii_total=t2_total,
            delta_x_induced=induced,
        )
        np.testing.assert_array_equal(result.delta_x_type_ii_total, t2_total)
        np.testing.assert_array_equal(result.delta_x_induced, induced)

    def test_existing_solve_returns_none_for_type_ii(self) -> None:
        """Backward compat: existing solve() returns None for Type II fields."""
        store = ModelStore()
        _, loaded = _register_2x2(store)
        solver = LeontiefSolver()

        delta_d = np.array([100.0, 50.0])
        result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        assert result.delta_x_type_ii_total is None
        assert result.delta_x_induced is None

    def test_phased_result_type_ii_defaults_none(self) -> None:
        """PhasedResult Type II cumulative fields default to None."""
        phased = PhasedResult(
            annual_results={},
            cumulative_delta_x=np.zeros(2),
            peak_year=2026,
            peak_delta_x=np.zeros(2),
        )
        assert phased.cumulative_delta_x_type_ii is None
        assert phased.cumulative_delta_x_induced is None


# ===================================================================
# Type II solve (Sprint 15 — Task 2)
# ===================================================================


from tests.integration.golden_scenarios.shared import (
    EXPECTED_B_STAR_SMALL,
    GOLDEN_COMPENSATION,
    GOLDEN_HOUSEHOLD_SHARES,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
)


class TestTypeIISolve:
    """Type II household-closure solve tests."""

    def _register_golden(self, store: ModelStore) -> LoadedModel:
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test-golden",
        )
        return store.get(mv.model_version_id)

    def test_type_ii_total_larger_than_type_i(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        assert np.sum(result.delta_x_type_ii_total) > np.sum(result.delta_x_total)

    def test_induced_equals_difference(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        np.testing.assert_allclose(
            result.delta_x_induced,
            result.delta_x_type_ii_total - result.delta_x_total,
            atol=1e-10,
        )

    def test_type_ii_matches_golden_reference(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded, delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        augmented_d = np.array([100.0, 0.0, 0.0, 0.0])
        expected_full = EXPECTED_B_STAR_SMALL @ augmented_d
        np.testing.assert_allclose(result.delta_x_type_ii_total, expected_full[:3], atol=1e-8)

    def test_type_ii_dimension_mismatch_raises(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="dimension"):
            solver.solve_type_ii(
                loaded_model=loaded, delta_d=delta_d,
                compensation_of_employees=np.array([1.0, 2.0]),
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )

    def test_type_ii_deterministic_reproducibility(self) -> None:
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        results = [
            solver.solve_type_ii(
                loaded_model=loaded, delta_d=delta_d,
                compensation_of_employees=np.array(GOLDEN_COMPENSATION),
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )
            for _ in range(5)
        ]
        for r in results[1:]:
            np.testing.assert_array_equal(r.delta_x_type_ii_total, results[0].delta_x_type_ii_total)


# ===================================================================
# Phased Type II (Sprint 15 — Task 3)
# ===================================================================


class TestPhasedTypeII:
    """solve_phased with optional Type II accumulation."""

    def _register_golden(self, store: ModelStore) -> LoadedModel:
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test-golden",
        )
        return store.get(mv.model_version_id)

    def test_phased_type_ii_accumulates(self) -> None:
        """Cumulative Type II and induced are computed; induced = type_ii - type_i."""
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()

        annual_shocks = {
            2026: np.array([100.0, 0.0, 0.0]),
            2027: np.array([0.0, 200.0, 0.0]),
        }
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        # Type II cumulative must not be None
        assert phased.cumulative_delta_x_type_ii is not None
        assert phased.cumulative_delta_x_induced is not None

        # Induced = type_ii - type_i (cumulative level)
        np.testing.assert_allclose(
            phased.cumulative_delta_x_induced,
            phased.cumulative_delta_x_type_ii - phased.cumulative_delta_x,
            atol=1e-10,
        )

        # Type II cumulative should be larger than Type I cumulative
        assert np.sum(phased.cumulative_delta_x_type_ii) > np.sum(phased.cumulative_delta_x)

        # Each annual result should have Type II fields
        for year, result in phased.annual_results.items():
            assert result.delta_x_type_ii_total is not None
            assert result.delta_x_induced is not None

    def test_phased_without_type_ii_returns_none(self) -> None:
        """When Type II vectors not passed, cumulative Type II fields are None."""
        store = ModelStore()
        loaded = self._register_golden(store)
        solver = LeontiefSolver()

        annual_shocks = {
            2026: np.array([100.0, 0.0, 0.0]),
        }
        phased = solver.solve_phased(
            loaded_model=loaded,
            annual_shocks=annual_shocks,
            base_year=2023,
        )
        assert phased.cumulative_delta_x_type_ii is None
        assert phased.cumulative_delta_x_induced is None

        # Annual results should also have None Type II fields
        for year, result in phased.annual_results.items():
            assert result.delta_x_type_ii_total is None
            assert result.delta_x_induced is None


# ===================================================================
# LoadedModel Type II properties (Sprint 15 — Task 5)
# ===================================================================


class TestLoadedModelTypeIIProperties:
    """LoadedModel exposes Type II prerequisite data as properties."""

    def test_has_type_ii_prerequisites_true(self) -> None:
        """Model registered with comp + shares has has_type_ii_prerequisites=True."""
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        loaded = store.get(mv.model_version_id)
        assert loaded.has_type_ii_prerequisites is True

    def test_has_type_ii_prerequisites_false(self) -> None:
        """Model without artifacts has has_type_ii_prerequisites=False."""
        store = ModelStore()
        _, loaded = _register_2x2(store)
        assert loaded.has_type_ii_prerequisites is False

    def test_compensation_array_returns_numpy(self) -> None:
        """compensation_of_employees_array returns float64 numpy array."""
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        loaded = store.get(mv.model_version_id)
        arr = loaded.compensation_of_employees_array
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float64
        np.testing.assert_array_almost_equal(arr, GOLDEN_COMPENSATION)

    def test_household_shares_array_returns_numpy(self) -> None:
        """household_consumption_shares_array returns float64 numpy array."""
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z), x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL, base_year=2023, source="test",
            artifact_payload={
                "compensation_of_employees": GOLDEN_COMPENSATION,
                "household_consumption_shares": GOLDEN_HOUSEHOLD_SHARES,
            },
        )
        loaded = store.get(mv.model_version_id)
        arr = loaded.household_consumption_shares_array
        assert arr is not None
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.float64
        np.testing.assert_array_almost_equal(arr, GOLDEN_HOUSEHOLD_SHARES)

    def test_compensation_array_none_when_missing(self) -> None:
        """compensation_of_employees_array returns None when not available."""
        store = ModelStore()
        _, loaded = _register_2x2(store)
        assert loaded.compensation_of_employees_array is None

    def test_household_shares_array_none_when_missing(self) -> None:
        """household_consumption_shares_array returns None when not available."""
        store = ModelStore()
        _, loaded = _register_2x2(store)
        assert loaded.household_consumption_shares_array is None
