"""Tests for binding constraint diagnostics and compliance diagnostics."""

import numpy as np

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.constraints.solver import FeasibilitySolver
from src.models.common import ConstraintConfidence


class TestBindingConstraintDiagnostics:
    """Tests for binding constraint metadata accuracy."""

    def test_binding_reports_correct_gap(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        """Gap = unconstrained - constrained."""
        # F base=200, delta_x=100 → total 300, cap at 250 → gap = 50
        constraint = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Cap F at 250",
            upper_bound=250.0,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        binding = result.binding_constraints
        assert len(binding) == 1
        bc = binding[0]
        assert bc.sector_code == "F"
        assert bc.unconstrained_value == 100.0
        assert bc.constrained_value == 50.0  # 250 - 200(base)
        assert bc.gap == 50.0
        assert bc.gap_pct == 0.5

    def test_binding_reports_correct_unit(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        constraint = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Cap F",
            upper_bound=250.0,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert result.binding_constraints[0].unit == ConstraintUnit.SAR_MILLIONS

    def test_non_binding_constraint_tracked(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        """Constraint that doesn't bind is tracked in non_binding list."""
        constraint = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Generous cap on F",
            upper_bound=9999.0,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert len(result.binding_constraints) == 0
        assert constraint.constraint_id in result.non_binding_constraints

    def test_binding_constraint_id_matches(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        constraint = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Cap F",
            upper_bound=250.0,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert result.binding_constraints[0].constraint_id == constraint.constraint_id


class TestComplianceDiagnostics:
    """Tests for compliance (non-clipping) diagnostics — Amendment 5."""

    def test_saudization_produces_diagnostic(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        constraint = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="30% saudization target",
            lower_bound=0.30,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert len(result.compliance_diagnostics) == 1
        diag = result.compliance_diagnostics[0]
        assert diag.constraint_type == ConstraintType.SAUDIZATION
        assert diag.sector_code == "F"
        assert diag.target_value == 0.30

    def test_saudization_does_not_affect_feasible(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        """SAUDIZATION must NOT clip output."""
        constraint = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="99% saudization target",
            lower_bound=0.99,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        delta_x = np.array([50.0, 100.0])
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=delta_x,
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        np.testing.assert_array_equal(
            result.unconstrained_delta_x,
            result.feasible_delta_x,
        )

    def test_compliance_diagnostic_gap_positive(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        constraint = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="25% target",
            lower_bound=0.25,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        # gap = target - projected (positive means non-compliant)
        assert result.compliance_diagnostics[0].gap == 0.25

    def test_economy_wide_saudization_all_sectors(
        self, two_sector_model, two_sector_coefficients, workspace_id, model_version_id,
    ) -> None:
        """Economy-wide SAUDIZATION produces diagnostics for ALL sectors."""
        constraint = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="all", allocation_rule="proportional"),
            description="30% economy-wide saudization",
            lower_bound=0.30,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.HARD,
        )
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[constraint],
        )
        solver = FeasibilitySolver()
        result = solver.solve(
            unconstrained_delta_x=np.array([50.0, 100.0]),
            base_x=two_sector_model.x,
            satellite_coefficients=two_sector_coefficients,
            constraint_set=cs,
            sector_codes=["A", "F"],
        )
        assert len(result.compliance_diagnostics) == 2
        codes = {d.sector_code for d in result.compliance_diagnostics}
        assert codes == {"A", "F"}


class TestConstraintSetStore:
    """Tests for InMemoryConstraintSetStore persistence."""

    def test_save_and_get(self, workspace_id, model_version_id) -> None:
        from src.engine.constraints.store import InMemoryConstraintSetStore

        store = InMemoryConstraintSetStore()
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[],
        )
        store.save(cs)
        retrieved = store.get(cs.constraint_set_id)
        assert retrieved is not None
        assert retrieved.constraint_set_id == cs.constraint_set_id

    def test_get_missing_returns_none(self) -> None:
        from uuid import uuid4

        from src.engine.constraints.store import InMemoryConstraintSetStore

        store = InMemoryConstraintSetStore()
        assert store.get(uuid4()) is None

    def test_get_by_workspace(self, workspace_id, model_version_id) -> None:
        from uuid import uuid4

        from src.engine.constraints.store import InMemoryConstraintSetStore

        store = InMemoryConstraintSetStore()
        cs1 = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="first",
            constraints=[],
        )
        cs2 = ConstraintSet(
            workspace_id=uuid4(),  # Different workspace
            model_version_id=model_version_id,
            name="second",
            constraints=[],
        )
        store.save(cs1)
        store.save(cs2)
        results = store.get_by_workspace(workspace_id)
        assert len(results) == 1
        assert results[0].name == "first"

    def test_list_all(self, workspace_id, model_version_id) -> None:
        from src.engine.constraints.store import InMemoryConstraintSetStore

        store = InMemoryConstraintSetStore()
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="test",
            constraints=[],
        )
        store.save(cs)
        all_sets = store.list_all()
        assert len(all_sets) == 1

    def test_overwrite_on_same_id(self, workspace_id, model_version_id) -> None:
        from src.engine.constraints.store import InMemoryConstraintSetStore

        store = InMemoryConstraintSetStore()
        cs = ConstraintSet(
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="original",
            constraints=[],
        )
        store.save(cs)
        # Overwrite with same ID but different name
        cs_updated = ConstraintSet(
            constraint_set_id=cs.constraint_set_id,
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name="updated",
            constraints=[],
        )
        store.save(cs_updated)
        retrieved = store.get(cs.constraint_set_id)
        assert retrieved is not None
        assert retrieved.name == "updated"
        assert len(store.list_all()) == 1
