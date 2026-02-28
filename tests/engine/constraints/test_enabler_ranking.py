"""Tests for enabler generation and ranking."""

from uuid import uuid4

import numpy as np

from src.engine.constraints.schema import (
    Constraint,
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


class TestOutputEnablers:
    """Enablers from binding output constraints."""

    def test_enablers_generated_for_binding(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([50.0, 100.0])
        base = np.array([100.0, 200.0])
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[cap],
        )

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        assert len(result.output_enablers) >= 1
        assert result.output_enablers[0].sector_code == "F"
        assert result.output_enablers[0].gap_unlocked > 0

    def test_ranked_by_gap_descending(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([80.0, 100.0])
        base = np.array([100.0, 200.0])
        cap_a = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["A"]),
            description="A cap at 110",
            upper_bound=110.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cap_f = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="F cap at 250",
            upper_bound=250.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[cap_a, cap_f],
        )

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        enablers = result.output_enablers
        assert len(enablers) >= 2
        # First enabler has priority_rank=1 and biggest gap
        assert enablers[0].priority_rank == 1
        for i in range(1, len(enablers)):
            assert enablers[i].gap_unlocked <= enablers[i - 1].gap_unlocked
            assert enablers[i].priority_rank == i + 1

    def test_non_binding_produces_no_enablers(self) -> None:
        solver = FeasibilitySolver()
        unconstrained = np.array([10.0, 20.0])
        base = np.array([100.0, 200.0])
        cap = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="High cap",
            upper_bound=500.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[cap],
        )

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        assert len(result.output_enablers) == 0


class TestComplianceEnablers:
    """Amendment 11: separate compliance enablers from output enablers."""

    def test_saudization_produces_compliance_enablers(self) -> None:
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
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[saud],
        )

        result = solver.solve(
            unconstrained_delta_x=unconstrained,
            base_x=base,
            satellite_coefficients=_make_coefficients(),
            constraint_set=cs,
            sector_codes=["A", "F"],
        )

        # Compliance enablers (not output enablers)
        assert len(result.compliance_enablers) >= 1
        assert result.compliance_enablers[0].sector_code == "F"
        # Output enablers should be empty (no output clipping)
        assert len(result.output_enablers) == 0
