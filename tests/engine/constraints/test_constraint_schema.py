"""Tests for constraint schema models and validation."""

from uuid import uuid4

import pytest

from src.engine.constraints.schema import (
    DIAGNOSTIC_ONLY_TYPES,
    POST_SOLVE_CLIPPING_TYPES,
    PRE_SOLVE_TYPES,
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence


class TestConstraintType:
    """All ConstraintType values are valid."""

    def test_all_values(self) -> None:
        expected = {
            "CAPACITY_CAP", "RAMP", "LABOR", "IMPORT",
            "BUDGET", "SAUDIZATION", "OTHER",
        }
        actual = {ct.value for ct in ConstraintType}
        assert actual == expected

    def test_pre_solve_types(self) -> None:
        assert ConstraintType.BUDGET in PRE_SOLVE_TYPES

    def test_diagnostic_types(self) -> None:
        assert ConstraintType.SAUDIZATION in DIAGNOSTIC_ONLY_TYPES

    def test_post_solve_types(self) -> None:
        assert ConstraintType.CAPACITY_CAP in POST_SOLVE_CLIPPING_TYPES
        assert ConstraintType.RAMP in POST_SOLVE_CLIPPING_TYPES
        assert ConstraintType.LABOR in POST_SOLVE_CLIPPING_TYPES
        assert ConstraintType.IMPORT in POST_SOLVE_CLIPPING_TYPES

    def test_budget_not_in_post_solve(self) -> None:
        """Amendment 2: BUDGET is pre-solve, not post-solve."""
        assert ConstraintType.BUDGET not in POST_SOLVE_CLIPPING_TYPES

    def test_saudization_not_in_post_solve(self) -> None:
        """Amendment 5: SAUDIZATION is diagnostic only."""
        assert ConstraintType.SAUDIZATION not in POST_SOLVE_CLIPPING_TYPES


class TestConstraintScope:
    """Amendment 3: ConstraintScope validation."""

    def test_valid_sector_scope(self) -> None:
        scope = ConstraintScope(scope_type="sector", scope_values=["F"])
        assert scope.scope_type == "sector"

    def test_sector_requires_one_value(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            ConstraintScope(scope_type="sector", scope_values=["F", "C"])

    def test_sector_requires_values(self) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            ConstraintScope(scope_type="sector", scope_values=[])

    def test_valid_group_scope(self) -> None:
        scope = ConstraintScope(scope_type="group", scope_values=["F", "C"])
        assert len(scope.scope_values) == 2

    def test_group_requires_two_values(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            ConstraintScope(scope_type="group", scope_values=["F"])

    def test_valid_all_scope(self) -> None:
        scope = ConstraintScope(
            scope_type="all", allocation_rule="proportional",
        )
        assert scope.scope_values is None

    def test_all_rejects_scope_values(self) -> None:
        with pytest.raises(ValueError, match="scope_values=None"):
            ConstraintScope(scope_type="all", scope_values=["F"])


class TestConstraint:
    """Core Constraint model validation."""

    def test_valid_constraint(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Test",
            upper_bound=1000.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.constraint_id is not None
        assert c.constraint_type == ConstraintType.CAPACITY_CAP

    def test_at_least_one_bound_required(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            Constraint(
                constraint_type=ConstraintType.CAPACITY_CAP,
                scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                description="No bounds",
                unit=ConstraintUnit.SAR_MILLIONS,
                confidence=ConstraintConfidence.HARD,
            )

    def test_lower_exceeds_upper_rejected(self) -> None:
        with pytest.raises(ValueError, match="lower_bound.*upper_bound"):
            Constraint(
                constraint_type=ConstraintType.CAPACITY_CAP,
                scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                description="Invalid bounds",
                lower_bound=200.0,
                upper_bound=100.0,
                unit=ConstraintUnit.SAR_MILLIONS,
                confidence=ConstraintConfidence.HARD,
            )

    def test_growth_rate_only_valid(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Ramp only",
            max_growth_rate=0.15,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
        )
        assert c.max_growth_rate == 0.15

    def test_effective_bound_scope_default(self) -> None:
        """Amendment 1: CAPACITY_CAP defaults to ABSOLUTE_TOTAL."""
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Default scope",
            upper_bound=1000.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.effective_bound_scope == ConstraintBoundScope.ABSOLUTE_TOTAL

    def test_effective_bound_scope_override(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Override",
            upper_bound=100.0,
            bound_scope=ConstraintBoundScope.DELTA_ONLY,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.effective_bound_scope == ConstraintBoundScope.DELTA_ONLY

    def test_applies_to_sector(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Test",
            upper_bound=100.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.applies_to_sector("F")
        assert not c.applies_to_sector("A")

    def test_economy_wide_applies_to_all(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="all", allocation_rule="proportional"),
            description="Test",
            max_growth_rate=0.25,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
        )
        assert c.applies_to_sector("F")
        assert c.applies_to_sector("A")
        assert c.applies_to_sector("XYZ")

    def test_applies_in_year(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Windowed",
            upper_bound=100.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
            time_window=(2024, 2026),
        )
        assert c.applies_in_year(2024)
        assert c.applies_in_year(2025)
        assert c.applies_in_year(2026)
        assert not c.applies_in_year(2023)
        assert not c.applies_in_year(2027)
        assert c.applies_in_year(None)  # None means "any year"

    def test_is_pre_solve(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.BUDGET,
            scope=ConstraintScope(scope_type="all", allocation_rule="proportional"),
            description="Budget",
            upper_bound=1000.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.is_pre_solve
        assert not c.is_post_solve_clipping

    def test_is_diagnostic_only(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.SAUDIZATION,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Saudization",
            lower_bound=0.25,
            unit=ConstraintUnit.FRACTION,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        assert c.is_diagnostic_only
        assert not c.is_post_solve_clipping

    def test_confidence_reuses_common(self) -> None:
        """ConstraintConfidence is the shared enum from common.py."""
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Test",
            upper_bound=100.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.confidence == ConstraintConfidence.HARD

    def test_evidence_refs(self) -> None:
        ref = uuid4()
        c = Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="With evidence",
            upper_bound=100.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
            evidence_refs=[ref],
        )
        assert c.evidence_refs == [ref]
