"""Type II mathematical accuracy tests — Sprint 15.

Verifies the mathematical correctness of the household-closed Leontief solver
by comparing solver results against hand-computed golden references.
"""

import numpy as np
import pytest

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from tests.integration.golden_scenarios.shared import (
    EXPECTED_B_STAR_SMALL,
    GOLDEN_COMPENSATION,
    GOLDEN_HOUSEHOLD_SHARES,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
)


class TestTypeIIMathematicalAccuracy:
    """Verify Type II solver against hand-computed golden references."""

    @pytest.fixture()
    def loaded_model(self):
        store = ModelStore()
        mv = store.register(
            Z=np.array(GOLDEN_Z),
            x=np.array(GOLDEN_X),
            sector_codes=SECTOR_CODES_SMALL,
            base_year=2023,
            source="golden-test",
        )
        return store.get(mv.model_version_id)

    @pytest.fixture()
    def solver(self):
        return LeontiefSolver()

    def test_augmented_leontief_inverse_matches_golden(self, loaded_model, solver) -> None:
        """B* = (I - A*)^{-1} matches pre-computed reference."""
        delta_d = np.array([100.0, 0.0, 0.0])
        result = solver.solve_type_ii(
            loaded_model=loaded_model,
            delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        # Expected: B* @ [100, 0, 0, 0], trimmed to first 3 elements
        augmented_d = np.array([100.0, 0.0, 0.0, 0.0])
        expected = EXPECTED_B_STAR_SMALL @ augmented_d
        np.testing.assert_allclose(result.delta_x_type_ii_total, expected[:3], atol=1e-8)

    def test_parity_identity_induced_equals_difference(self, loaded_model, solver) -> None:
        """Induced = Type II total - Type I total (core parity identity)."""
        for shock in [
            np.array([100.0, 0.0, 0.0]),
            np.array([0.0, 200.0, 0.0]),
            np.array([50.0, 50.0, 50.0]),
            np.array([1e6, 0.0, 0.0]),
        ]:
            result = solver.solve_type_ii(
                loaded_model=loaded_model,
                delta_d=shock,
                compensation_of_employees=np.array(GOLDEN_COMPENSATION),
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )
            np.testing.assert_allclose(
                result.delta_x_induced,
                result.delta_x_type_ii_total - result.delta_x_total,
                atol=1e-10,
                err_msg=f"Parity failed for shock={shock}",
            )

    def test_type_ii_strictly_larger_than_type_i(self, loaded_model, solver) -> None:
        """Type II total output >= Type I total output element-wise."""
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve_type_ii(
            loaded_model=loaded_model,
            delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        assert np.all(result.delta_x_type_ii_total >= result.delta_x_total - 1e-10)
        # Sum should be strictly larger for non-trivial shocks
        assert np.sum(result.delta_x_type_ii_total) > np.sum(result.delta_x_total)

    def test_deterministic_across_multiple_runs(self, loaded_model, solver) -> None:
        """Same inputs must produce byte-identical outputs."""
        delta_d = np.array([100.0, 50.0, 25.0])
        results = [
            solver.solve_type_ii(
                loaded_model=loaded_model,
                delta_d=delta_d,
                compensation_of_employees=np.array(GOLDEN_COMPENSATION),
                household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
            )
            for _ in range(10)
        ]
        for r in results[1:]:
            np.testing.assert_array_equal(r.delta_x_type_ii_total, results[0].delta_x_type_ii_total)
            np.testing.assert_array_equal(r.delta_x_induced, results[0].delta_x_induced)

    def test_zero_shock_produces_zero_output(self, loaded_model, solver) -> None:
        """Zero demand shock produces zero Type II output."""
        delta_d = np.zeros(3)
        result = solver.solve_type_ii(
            loaded_model=loaded_model,
            delta_d=delta_d,
            compensation_of_employees=np.array(GOLDEN_COMPENSATION),
            household_consumption_shares=np.array(GOLDEN_HOUSEHOLD_SHARES),
        )
        np.testing.assert_allclose(result.delta_x_type_ii_total, np.zeros(3), atol=1e-15)
        np.testing.assert_allclose(result.delta_x_induced, np.zeros(3), atol=1e-15)

    def test_linearity_of_type_ii_solver(self, loaded_model, solver) -> None:
        """Type II must be linear: f(a*d1 + b*d2) = a*f(d1) + b*f(d2)."""
        d1 = np.array([100.0, 0.0, 0.0])
        d2 = np.array([0.0, 200.0, 0.0])
        a, b = 2.0, 3.0
        comp = np.array(GOLDEN_COMPENSATION)
        shares = np.array(GOLDEN_HOUSEHOLD_SHARES)

        r1 = solver.solve_type_ii(
            loaded_model=loaded_model, delta_d=d1,
            compensation_of_employees=comp,
            household_consumption_shares=shares,
        )
        r2 = solver.solve_type_ii(
            loaded_model=loaded_model, delta_d=d2,
            compensation_of_employees=comp,
            household_consumption_shares=shares,
        )
        r_combined = solver.solve_type_ii(
            loaded_model=loaded_model, delta_d=a * d1 + b * d2,
            compensation_of_employees=comp,
            household_consumption_shares=shares,
        )

        expected = a * r1.delta_x_type_ii_total + b * r2.delta_x_type_ii_total
        np.testing.assert_allclose(r_combined.delta_x_type_ii_total, expected, atol=1e-8)

    def test_phased_type_ii_cumulative_matches_manual_sum(self, loaded_model, solver) -> None:
        """Phased solve cumulative Type II matches manual sum of per-year results."""
        shocks = {
            2024: np.array([100.0, 0.0, 0.0]),
            2025: np.array([50.0, 25.0, 0.0]),
        }
        comp = np.array(GOLDEN_COMPENSATION)
        shares = np.array(GOLDEN_HOUSEHOLD_SHARES)

        phased = solver.solve_phased(
            loaded_model=loaded_model,
            annual_shocks=shocks,
            base_year=2023,
            compensation_of_employees=comp,
            household_consumption_shares=shares,
        )

        # Manual sum of per-year Type II totals
        manual_cumulative = np.zeros(3)
        for year in sorted(shocks.keys()):
            r = solver.solve_type_ii(
                loaded_model=loaded_model,
                delta_d=shocks[year],
                compensation_of_employees=comp,
                household_consumption_shares=shares,
            )
            manual_cumulative += r.delta_x_type_ii_total

        np.testing.assert_allclose(
            phased.cumulative_delta_x_type_ii, manual_cumulative, atol=1e-10
        )
