"""Tests for FeasibilitySolver — core constraint clipping logic."""

from uuid import uuid4

import numpy as np
import pytest

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.constraints.solver import FeasibilitySolver
from src.engine.satellites import SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7


def _make_coefficients(n: int = 2) -> SatelliteCoefficients:
    return SatelliteCoefficients(
        jobs_coeff=np.ones(n) * 0.5,
        import_ratio=np.ones(n) * 0.2,
        va_ratio=np.ones(n) * 0.6,
        version_id=uuid4(),
    )


def _make_constraint_set(
    constraints: list[Constraint],
) -> ConstraintSet:
    return ConstraintSet(
        workspace_id=uuid4(),
        model_version_id=new_uuid7(),
        name="test",
        constraints=constraints,
    )


class TestNoConstraints:
    """Identity test: no constraints → feasible == unconstrained."""

    def test_empty_set_identity(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])
        base = np.array([100.0, 200.0])
        cs = _make_constraint_set([])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        np.testing.assert_array_equal(
            result.feasible_delta_x, result.unconstrained_delta_x,
        )
        assert len(result.binding_constraints) == 0
        assert result.total_output_gap == 0.0

    def test_all_constraints_non_binding(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 20.0])
        base = np.array([100.0, 200.0])
        # Cap at 500 — way above unconstrained
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="High cap",
            upper_bound=500.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        np.testing.assert_array_equal(
            result.feasible_delta_x, unconstrained,
        )
        assert len(result.binding_constraints) == 0
        assert result.total_output_gap == 0.0
        assert len(result.non_binding_constraints) == 1


class TestCapacityCap:
    """CAPACITY_CAP constraint tests."""

    def test_single_cap_binds(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 100.0])  # F wants +100
        base = np.array([100.0, 200.0])            # F has 200 base
        # Cap F at 250 absolute → max delta = 50
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap at 250",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # F should be clipped: 250 - 200 = 50
        assert result.feasible_delta_x[1] == pytest.approx(50.0)
        # A unchanged
        assert result.feasible_delta_x[0] == pytest.approx(10.0)
        assert len(result.binding_constraints) == 1
        assert result.binding_constraints[0].sector_code == "F"
        assert result.binding_constraints[0].gap == pytest.approx(50.0)

    def test_delta_only_scope(self) -> None:
        """Amendment 1: DELTA_ONLY caps delta_x directly."""
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 100.0])
        base = np.array([100.0, 200.0])
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Delta cap at 30",
            upper_bound=30.0,
            bound_scope=ConstraintBoundScope.DELTA_ONLY,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        assert result.feasible_delta_x[1] == pytest.approx(30.0)


class TestRampConstraint:
    """RAMP constraint tests (Amendment 7)."""

    def test_ramp_binds(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([5.0, 80.0])  # F wants +80
        base = np.array([100.0, 200.0])          # F base = 200
        # Max 15% growth → max total = 230, max delta = 30
        ramp = Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F max 15% growth",
            max_growth_rate=0.15,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = _make_constraint_set([ramp])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # max delta = 200 * 0.15 = 30
        assert result.feasible_delta_x[1] == pytest.approx(30.0)
        assert result.feasible_delta_x[0] == pytest.approx(5.0)


class TestMultipleConstraints:
    """Multiple constraints on same sector."""

    def test_tightest_wins(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([5.0, 100.0])
        base = np.array([100.0, 200.0])
        # Cap at 260 → delta 60. Ramp 15% → delta 30. Ramp is tighter.
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Cap at 260",
            upper_bound=260.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        ramp = Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="15% ramp",
            max_growth_rate=0.15,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = _make_constraint_set([cap, ramp])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # Ramp is tighter: 200 * 0.15 = 30
        assert result.feasible_delta_x[1] == pytest.approx(30.0)
        assert len(result.binding_constraints) == 2

    def test_different_sectors_independent(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])
        base = np.array([100.0, 200.0])
        cap_a = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["A"]),
            description="A cap",
            upper_bound=120.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cap_f = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap_a, cap_f])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # A: cap 120, delta = 120 - 100 = 20 (clipped from 50)
        assert result.feasible_delta_x[0] == pytest.approx(20.0)
        # F: cap 250, delta = 250 - 200 = 50 (clipped from 100)
        assert result.feasible_delta_x[1] == pytest.approx(50.0)


class TestNegativeDeltaX:
    """Contraction scenarios: constraints don't clip below zero."""

    def test_contraction_allowed(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([-20.0, 50.0])
        base = np.array([100.0, 200.0])
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["A"]),
            description="A cap",
            upper_bound=120.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # A is contracting — don't clip
        assert result.feasible_delta_x[0] == pytest.approx(-20.0)


class TestLaborConstraint:
    """LABOR constraint: caps in jobs space, back-calculated to output."""

    def test_labor_cap_binds(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 100.0])
        base = np.array([100.0, 200.0])
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.5, 1.0]),  # F: 1 job per unit output
            import_ratio=np.array([0.2, 0.3]),
            va_ratio=np.array([0.6, 0.4]),
            version_id=uuid4(),
        )
        # Labor cap: max 240 jobs for F absolute
        # F base output = 200, jobs_coeff = 1.0 → base jobs = 200
        # Max output = 240 / 1.0 = 240 → max delta = 40
        labor = Constraint(
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F labor cap",
            upper_bound=240.0,
            unit=ConstraintUnit.JOBS,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        cs = _make_constraint_set([labor])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # max output = 240 / 1.0 = 240, max delta = 240 - 200 = 40
        assert result.feasible_delta_x[1] == pytest.approx(40.0)


class TestSaudizationDiagnostic:
    """Amendment 5: SAUDIZATION = diagnostic only, no clipping."""

    def test_saudization_does_not_clip(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 100.0])
        base = np.array([100.0, 200.0])
        saud = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="25% Saudi share",
            lower_bound=0.25,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        cs = _make_constraint_set([saud])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # Output NOT clipped
        np.testing.assert_array_equal(
            result.feasible_delta_x, unconstrained,
        )
        # But compliance diagnostic present
        assert len(result.compliance_diagnostics) == 1
        assert result.compliance_diagnostics[0].sector_code == "F"
        assert result.compliance_diagnostics[0].target_value == 0.25


class TestEconomyWide:
    """Amendment 4: Economy-wide constraints with proportional allocation."""

    def test_proportional_ramp(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])  # Both want to grow
        base = np.array([100.0, 200.0])
        # Economy-wide 10% ramp → A max delta=10, F max delta=20
        ramp = Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="all", allocation_rule="proportional"),
            description="10% economy-wide ramp",
            max_growth_rate=0.10,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = _make_constraint_set([ramp])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # A: max delta = 100 * 0.10 = 10
        assert result.feasible_delta_x[0] == pytest.approx(10.0)
        # F: max delta = 200 * 0.10 = 20
        assert result.feasible_delta_x[1] == pytest.approx(20.0)


class TestSummaryStats:
    """Summary statistics in FeasibilityResult."""

    def test_total_output_gap(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])
        base = np.array([100.0, 200.0])
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap at 250",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # Gap on F: 100 - 50 = 50. A has no gap.
        assert result.total_output_gap == pytest.approx(50.0)
        assert result.total_output_gap_pct == pytest.approx(50.0 / 150.0)

    def test_jobs_gap(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([0.0, 100.0])
        base = np.array([100.0, 200.0])
        coefficients = SatelliteCoefficients(
            jobs_coeff=np.array([0.0, 1.0]),  # F: 1 job per unit
            import_ratio=np.array([0.0, 0.0]),
            va_ratio=np.array([0.0, 0.0]),
            version_id=uuid4(),
        )
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap at 250",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = _make_constraint_set([cap])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # F delta clipped from 100 to 50 → jobs gap = 50 * 1.0 = 50
        assert result.total_jobs_gap == pytest.approx(50.0)


class TestConfidenceSummary:
    """Amendment 9: ConstraintConfidenceSummary."""

    def test_confidence_counts(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])
        base = np.array([100.0, 200.0])
        cs = _make_constraint_set([
            Constraint(
                constraint_type=ConstraintType.CAPACITY_CAP,
                scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                description="Hard cap",
                upper_bound=250.0,
                unit=ConstraintUnit.SAR_MILLIONS,
                confidence=ConstraintConfidence.HARD,
            ),
            Constraint(
                constraint_type=ConstraintType.RAMP,
                scope=ConstraintScope(scope_type="sector", scope_values=["A"]),
                description="Assumed ramp",
                max_growth_rate=0.10,
                unit=ConstraintUnit.GROWTH_RATE,
                confidence=ConstraintConfidence.ASSUMED,
            ),
        ])

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        summary = result.constraint_confidence_summary
        assert summary.total_constraints == 2
        assert summary.hard_count == 1
        assert summary.assumed_count == 1

    def test_solver_method(self) -> None:
        solver = FeasibilitySolver()
        cs = _make_constraint_set([])
        result = solver.solve(
            unconstrained_delta_x=np.array([10.0, 20.0]),
            base_x=np.array([100.0, 200.0]),
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert result.solver_method == "iterative_clipping_v1"
        assert len(result.known_limitations) > 0
