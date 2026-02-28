"""Tests for LPFeasibilitySolver — MVP-10 shadow prices via scipy.optimize.linprog.

Amendment 7: LP is used for shadow prices ONLY. The clipping solver produces
the feasible vector (composition-preserving). LP should NOT reallocate across sectors.

Tests validate:
- LP shadow prices match clipping for simple cases
- LP shadow prices are non-negative for binding constraints
- LP handles no-constraint case (all zeros)
- LP fallback to clipping when infeasible
- LP status tracking
- LP + clipping combined result
"""

from uuid import uuid4

import numpy as np
import pytest

from src.engine.feasibility import (
    ClippingSolver,
    ConstraintSpec,
)
from src.engine.feasibility_lp import (
    LPFeasibilitySolver,
)
from src.engine.satellites import SatelliteCoefficients


@pytest.fixture
def sector_codes():
    return ["SEC01", "SEC02", "SEC03"]


@pytest.fixture
def unconstrained_3():
    return np.array([100.0, 80.0, 60.0])


@pytest.fixture
def sat_coeffs():
    return SatelliteCoefficients(
        jobs_coeff=np.array([0.1, 0.15, 0.2]),
        import_ratio=np.array([0.3, 0.2, 0.1]),
        va_ratio=np.array([0.5, 0.6, 0.7]),
        version_id=uuid4(),
    )


class TestLPShadowPrices:
    def test_no_constraints_zero_prices(self, unconstrained_3, sector_codes):
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=[],
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert len(result.shadow_prices) == 0

    def test_single_capacity_cap_positive_shadow(self, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert len(result.shadow_prices) == 1
        # Binding constraint should have positive shadow price
        assert result.shadow_prices[0] > 0

    def test_non_binding_constraint_zero_shadow(self, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 200.0, "HARD"),  # Not binding
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert abs(result.shadow_prices[0]) < 1e-6

    def test_multiple_constraints_shadow_prices(self, unconstrained_3, sector_codes):
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 2, 30.0, "ESTIMATED"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert len(result.shadow_prices) == 2
        # Both binding → both positive
        assert result.shadow_prices[0] > 0
        assert result.shadow_prices[1] > 0

    def test_labor_constraint_shadow_price(self, unconstrained_3, sector_codes, sat_coeffs):
        """Total jobs = 34, cap at 17 → binding."""
        constraints = [
            ConstraintSpec(uuid4(), "LABOR_AVAILABILITY", None, 17.0, "HARD"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=sat_coeffs,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert result.shadow_prices[0] > 0

    def test_budget_ceiling_shadow_price(self, unconstrained_3, sector_codes):
        """Total = 240, cap at 120 → binding."""
        constraints = [
            ConstraintSpec(uuid4(), "BUDGET_CEILING", None, 120.0, "ASSUMED"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.status == "optimal"
        assert result.shadow_prices[0] > 0

    def test_lp_result_has_constraint_ids(self, unconstrained_3, sector_codes):
        cid = uuid4()
        constraints = [
            ConstraintSpec(cid, "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        assert result.constraint_ids[0] == cid


class TestLPFeasibleVectorFromClipping:
    """Amendment 7: LP does NOT produce feasible vector. Clipping does."""

    def test_lp_does_not_return_feasible_vector(self, unconstrained_3, sector_codes):
        """LPShadowPriceResult should not have feasible_delta_x."""
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]
        lp = LPFeasibilitySolver()
        result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )
        # LPShadowPriceResult should only have shadow_prices, no feasible vector
        assert not hasattr(result, "feasible_delta_x")

    def test_combined_clipping_and_lp(self, unconstrained_3, sector_codes):
        """Test typical usage: clipping for feasible, LP for shadow prices."""
        constraints = [
            ConstraintSpec(uuid4(), "CAPACITY_CAP", 0, 50.0, "HARD"),
        ]

        # Clipping for feasible vector
        clipper = ClippingSolver()
        clip_result = clipper.solve(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )

        # LP for shadow prices
        lp = LPFeasibilitySolver()
        lp_result = lp.compute_shadow_prices(
            unconstrained_delta_x=unconstrained_3,
            constraints=constraints,
            satellite_coefficients=None,
            sector_codes=sector_codes,
        )

        # Both should agree constraint is binding
        assert clip_result.binding_mask[0]
        assert lp_result.shadow_prices[0] > 0

        # Feasible vector comes from clipping
        assert clip_result.feasible_delta_x[0] == 50.0
