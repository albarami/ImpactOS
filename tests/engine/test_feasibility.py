"""Tests for ClippingSolver — MVP-10 deterministic constraint engine.

Tests the composition-preserving clipping solver:
- No constraints = identity
- Sector capacity caps
- Aggregate constraints (labor, import, budget)
- Combined constraints
- Binding/slack identification
- Shadow price computation
- Gap sign convention enforcement
- Edge cases (zero input, all capped, dimension mismatch)
- applies_to="all" handling
- Enabler recommendation generation
- Confidence summary computation
"""

from uuid import uuid4

import numpy as np
import pytest

from src.engine.feasibility import (
    ClippingSolver,
    ConstraintSpec,
    compute_confidence_summary,
    constraints_to_specs,
    generate_enabler_recommendations,
)
from src.engine.satellites import SatelliteCoefficients
from src.models.common import ConstraintConfidence
from src.models.feasibility import (
    BindingConstraint,
    Constraint,
    ConstraintType,
)


@pytest.fixture
def solver():
    return ClippingSolver()


@pytest.fixture
def sector_codes():
    return ["SEC01", "SEC02", "SEC03"]


@pytest.fixture
def unconstrained_3():
    """Unconstrained delta_x for 3 sectors."""
    return np.array([100.0, 80.0, 60.0])


@pytest.fixture
def sat_coeffs():
    """Satellite coefficients for 3 sectors."""
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.1, 0.15, 0.2]),
        import_ratio=np.array([0.3, 0.2, 0.1]),
        va_ratio=np.array([0.5, 0.6, 0.7]),
        version_id=uuid4(),
    )


class TestClippingSolverIdentity:
    def test_no_constraints_returns_unconstrained(self, solver, unconstrained_3, sector_codes):
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=[],
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(result.feasible_delta_x, unconstrained_3)

    def test_no_constraints_gap_is_zero(self, solver, unconstrained_3, sector_codes):
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=[],
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(result.gap_per_sector, np.zeros(3))


class TestCapacityCaps:
    def test_single_capacity_cap_clips_sector(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(
                constraint_id=uuid4(),
                constraint_type="CAPACITY_CAP",
                sector_index=0,
                bound_value=50.0,
                confidence="HARD",
            ),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.feasible_delta_x[0] == 50.0
        assert result.feasible_delta_x[1] == 80.0  # Unchanged
        assert result.feasible_delta_x[2] == 60.0  # Unchanged

    def test_multiple_capacity_caps(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 2, 30.0, "ESTIMATED"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.feasible_delta_x[0] == 50.0
        assert result.feasible_delta_x[1] == 80.0
        assert result.feasible_delta_x[2] == 30.0

    def test_capacity_cap_non_binding(self, solver, unconstrained_3, sector_codes):
        """Cap above unconstrained should have no effect."""
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 200.0, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.feasible_delta_x[0] == 100.0  # Unchanged

    def test_capacity_cap_exact_match(self, solver, unconstrained_3, sector_codes):
        """Cap exactly equal to unconstrained — binding but no change."""
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 100.0, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.feasible_delta_x[0] == 100.0


class TestAggregateConstraints:
    def test_labor_constraint_scales_proportionally(
        self, solver, unconstrained_3, sector_codes, sat_coeffs,
    ):
        """Total jobs = 0.1*100 + 0.15*80 + 0.2*60 = 10 + 12 + 12 = 34."""
        labor_cap = 17.0  # Half of 34
        constraints = [
            ConstraintSpec(uuid4(), "LABOR_AVAILABILITY", None, labor_cap, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=sat_coeffs,
            sector_codes=sector_codes,
        )
        # Should scale by 17/34 = 0.5
        np.testing.assert_allclose(result.feasible_delta_x, unconstrained_3 * 0.5, rtol=1e-10)

    def test_import_constraint_scales_proportionally(
        self, solver, unconstrained_3, sector_codes, sat_coeffs,
    ):
        """Total imports = 0.3*100 + 0.2*80 + 0.1*60 = 30 + 16 + 6 = 52."""
        import_cap = 26.0  # Half of 52
        constraints = [
            ConstraintSpec(uuid4(), "IMPORT_BOTTLENECK", None, import_cap, "ESTIMATED"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=sat_coeffs,
            sector_codes=sector_codes,
        )
        np.testing.assert_allclose(result.feasible_delta_x, unconstrained_3 * 0.5, rtol=1e-10)

    def test_budget_ceiling_scales_proportionally(self, solver, unconstrained_3, sector_codes):
        """Total output = 100 + 80 + 60 = 240."""
        budget_cap = 120.0  # Half of 240
        constraints = [
            ConstraintSpec(uuid4(), "BUDGET_CEILING", None, budget_cap, "ASSUMED"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_allclose(result.feasible_delta_x, unconstrained_3 * 0.5, rtol=1e-10)

    def test_aggregate_non_binding(self, solver, unconstrained_3, sector_codes):
        """Budget cap above total output — no effect."""
        budget_cap = 500.0
        constraints = [
            ConstraintSpec(uuid4(), "BUDGET_CEILING", None, budget_cap, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(result.feasible_delta_x, unconstrained_3)


class TestCombinedConstraints:
    def test_capacity_then_labor(self, solver, sector_codes, sat_coeffs):
        """Capacity cap first, then labor aggregate on the capped result."""
        ux = np.array([100.0, 80.0, 60.0])
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
            # After cap: [50, 80, 60]. Jobs = 0.1*50 + 0.15*80 + 0.2*60 = 5+12+12 = 29
            ConstraintSpec(uuid4(), "LABOR_AVAILABILITY", None, 14.5, "ESTIMATED"),
            # 14.5/29 = 0.5, scale: [25, 40, 30]
        ]
        result = solver.solve(
            unconstrained_delta_x=ux,
            constraints=constraints,
            satellite_coefficients=sat_coeffs,
            sector_codes=sector_codes,
        )
        np.testing.assert_allclose(result.feasible_delta_x, [25.0, 40.0, 30.0], rtol=1e-10)


class TestBindingAndShadowPrices:
    def test_binding_mask_correct(self, solver, unconstrained_3, sector_codes):
        cid = uuid4()
        constraints = [
            ConstraintSpec(cid, "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.binding_mask[0] is True or result.binding_mask[0] == True  # noqa: E712

    def test_shadow_prices_positive_for_binding(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        # Binding constraint should have positive shadow price
        assert result.shadow_prices[0] > 0

    def test_shadow_prices_zero_for_slack(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 200.0, "HARD"),  # Not binding
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.shadow_prices[0] == 0.0


class TestFeasibilityInvariants:
    def test_feasible_leq_unconstrained(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 2, 30.0, "ESTIMATED"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert np.all(result.feasible_delta_x <= unconstrained_3 + 1e-10)

    def test_feasible_non_negative(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 0.0, "HARD"),  # Cap to zero
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert np.all(result.feasible_delta_x >= 0)

    def test_gap_sign_convention(self, solver, unconstrained_3, sector_codes):
        """gap = unconstrained - feasible, always >= 0."""
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        expected_gap = unconstrained_3 - result.feasible_delta_x
        np.testing.assert_array_equal(result.gap_per_sector, expected_gap)
        assert np.all(result.gap_per_sector >= 0)

    def test_deterministic_reproducibility(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        r1 = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        r2 = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(r1.feasible_delta_x, r2.feasible_delta_x)


class TestEdgeCases:
    def test_zero_unconstrained_input(self, solver, sector_codes):
        ux = np.zeros(3)
        result = solver.solve(
            unconstrained_delta_x=ux,
            constraints=[],
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(result.feasible_delta_x, np.zeros(3))

    def test_all_sectors_capped_to_zero(self, solver, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", i, 0.0, "HARD")
            for i in range(3)
        ]
        result = solver.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        np.testing.assert_array_equal(result.feasible_delta_x, np.zeros(3))

    def test_dimension_mismatch_raises(self, solver):
        ux = np.array([100.0, 80.0])  # 2 sectors
        with pytest.raises(ValueError, match="dimension"):
            solver.solve(
                unconstrained_delta_x=ux,
                constraints=[],
                satellite_coefficients=None,
                sector_codes=["SEC01", "SEC02", "SEC03"],  # 3 sectors
            )


class TestConstraintsToSpecs:
    def test_sector_code_maps_to_index(self):
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            applies_to="SEC02",
            value=100.0,
            unit="SAR",
            confidence=ConstraintConfidence.HARD,
        )
        specs = constraints_to_specs([c], ["SEC01", "SEC02", "SEC03"])
        assert len(specs) == 1
        assert specs[0].sector_index == 1

    def test_all_maps_to_none_index(self):
        c = Constraint(
            constraint_type=ConstraintType.BUDGET_CEILING,
            applies_to="all",
            value=1_000_000.0,
            unit="SAR",
            confidence=ConstraintConfidence.ASSUMED,
        )
        specs = constraints_to_specs([c], ["SEC01", "SEC02"])
        assert specs[0].sector_index is None

    def test_unknown_sector_raises(self):
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            applies_to="UNKNOWN_SECTOR",
            value=100.0,
            unit="SAR",
            confidence=ConstraintConfidence.HARD,
        )
        with pytest.raises(ValueError, match="UNKNOWN_SECTOR"):
            constraints_to_specs([c], ["SEC01", "SEC02"])

    def test_applies_to_all_with_multiple_sectors(self):
        """Constraint with applies_to='all' + 3 sectors → aggregate constraint."""
        c = Constraint(
            constraint_type=ConstraintType.BUDGET_CEILING,
            applies_to="all",
            value=200.0,
            unit="SAR",
            confidence=ConstraintConfidence.HARD,
        )
        specs = constraints_to_specs([c], ["SEC01", "SEC02", "SEC03"])
        assert specs[0].sector_index is None
        assert specs[0].bound_value == 200.0


class TestEnablerRecommendations:
    def test_generates_recommendations_for_binding(self):
        binding = [
            BindingConstraint(
                constraint_id=uuid4(),
                constraint_type=ConstraintType.CAPACITY_CAP,
                sector_code="SEC01",
                shadow_price=50.0,
                gap_to_feasible=100.0,
            ),
        ]
        constraints = [
            Constraint(
                constraint_id=binding[0].constraint_id,
                constraint_type=ConstraintType.CAPACITY_CAP,
                applies_to="SEC01",
                value=50.0,
                unit="SAR",
                confidence=ConstraintConfidence.HARD,
            ),
        ]
        recs = generate_enabler_recommendations(binding, constraints)
        assert len(recs) == 1
        assert recs[0].priority_rank == 1

    def test_ranked_by_shadow_price(self):
        id1, id2 = uuid4(), uuid4()
        binding = [
            BindingConstraint(
                constraint_id=id1,
                constraint_type=ConstraintType.CAPACITY_CAP,
                sector_code="SEC01",
                shadow_price=10.0,
                gap_to_feasible=50.0,
            ),
            BindingConstraint(
                constraint_id=id2,
                constraint_type=ConstraintType.LABOR_AVAILABILITY,
                sector_code="all",
                shadow_price=100.0,
                gap_to_feasible=500.0,
            ),
        ]
        constraints = [
            Constraint(
                constraint_id=id1,
                constraint_type=ConstraintType.CAPACITY_CAP,
                applies_to="SEC01", value=50.0,
                unit="SAR", confidence=ConstraintConfidence.HARD,
            ),
            Constraint(
                constraint_id=id2,
                constraint_type=ConstraintType.LABOR_AVAILABILITY,
                applies_to="all", value=1000.0,
                unit="jobs", confidence=ConstraintConfidence.ESTIMATED,
            ),
        ]
        recs = generate_enabler_recommendations(binding, constraints)
        assert len(recs) == 2
        # Highest shadow price (100) should be rank 1
        assert recs[0].estimated_unlock_value == 500.0  # gap_to_feasible of highest shadow_price
        assert recs[0].priority_rank == 1
        assert recs[1].priority_rank == 2

    def test_empty_binding_returns_empty(self):
        recs = generate_enabler_recommendations([], [])
        assert recs == []


class TestConfidenceSummary:
    def test_compute_all_hard(self):
        constraints = [
            Constraint(constraint_type=ConstraintType.CAPACITY_CAP, applies_to="SEC01",
                        value=100.0, unit="SAR", confidence=ConstraintConfidence.HARD),
            Constraint(constraint_type=ConstraintType.BUDGET_CEILING, applies_to="all",
                        value=500.0, unit="SAR", confidence=ConstraintConfidence.HARD),
        ]
        summary = compute_confidence_summary(constraints)
        assert summary.hard_pct == 1.0
        assert summary.estimated_pct == 0.0
        assert summary.assumed_pct == 0.0
        assert summary.total_constraints == 2

    def test_compute_mixed(self):
        constraints = [
            Constraint(constraint_type=ConstraintType.CAPACITY_CAP, applies_to="S1",
                        value=100.0, unit="SAR", confidence=ConstraintConfidence.HARD),
            Constraint(constraint_type=ConstraintType.LABOR_AVAILABILITY, applies_to="all",
                        value=1000.0, unit="jobs", confidence=ConstraintConfidence.ESTIMATED),
            Constraint(constraint_type=ConstraintType.BUDGET_CEILING, applies_to="all",
                        value=500.0, unit="SAR", confidence=ConstraintConfidence.ASSUMED),
        ]
        summary = compute_confidence_summary(constraints)
        assert abs(summary.hard_pct - 1 / 3) < 0.01
        assert abs(summary.estimated_pct - 1 / 3) < 0.01
        assert abs(summary.assumed_pct - 1 / 3) < 0.01
        assert summary.total_constraints == 3

    def test_compute_empty(self):
        summary = compute_confidence_summary([])
        assert summary.hard_pct == 0.0
        assert summary.total_constraints == 0
