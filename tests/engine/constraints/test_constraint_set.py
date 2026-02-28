"""Tests for ConstraintSet lookups, validation, and conflict detection."""

from uuid import uuid4

from src.engine.constraints.schema import (
    Constraint,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence, new_uuid7


def _make_constraint(
    ctype: ConstraintType = ConstraintType.CAPACITY_CAP,
    sector: str = "F",
    upper: float | None = 1000.0,
    lower: float | None = None,
    growth: float | None = None,
    scope_type: str = "sector",
    **kwargs,
) -> Constraint:
    """Helper to build test constraints."""
    if scope_type == "sector":
        scope = ConstraintScope(scope_type="sector", scope_values=[sector])
    elif scope_type == "all":
        scope = ConstraintScope(scope_type="all", allocation_rule="proportional")
    else:
        scope = ConstraintScope(scope_type=scope_type, scope_values=[sector, "C"])

    return Constraint(
        constraint_type=ctype,
        scope=scope,
        description=f"Test {ctype.value} on {sector}",
        upper_bound=upper,
        lower_bound=lower,
        max_growth_rate=growth,
        unit=ConstraintUnit.SAR_MILLIONS,
        confidence=ConstraintConfidence.ASSUMED,
        **kwargs,
    )


class TestConstraintSetLookups:
    """ConstraintSet query methods."""

    def test_get_constraints_for_sector(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(sector="F"),
                _make_constraint(sector="A"),
            ],
        )
        result = cs.get_constraints_for_sector("F")
        assert len(result) == 1
        assert result[0].scope.scope_values == ["F"]

    def test_economy_wide_included_in_sector_lookup(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(sector="F"),
                _make_constraint(
                    ctype=ConstraintType.RAMP,
                    scope_type="all",
                    upper=None,
                    growth=0.25,
                ),
            ],
        )
        result = cs.get_constraints_for_sector("F")
        assert len(result) == 2  # sector + economy-wide

    def test_get_constraints_by_type(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(ctype=ConstraintType.CAPACITY_CAP),
                _make_constraint(ctype=ConstraintType.RAMP, upper=None, growth=0.15),
                _make_constraint(ctype=ConstraintType.CAPACITY_CAP, sector="A"),
            ],
        )
        caps = cs.get_constraints_by_type(ConstraintType.CAPACITY_CAP)
        assert len(caps) == 2
        ramps = cs.get_constraints_by_type(ConstraintType.RAMP)
        assert len(ramps) == 1

    def test_get_post_solve_constraints(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(ctype=ConstraintType.CAPACITY_CAP),
                _make_constraint(
                    ctype=ConstraintType.BUDGET,
                    scope_type="all",
                ),
                _make_constraint(
                    ctype=ConstraintType.SAUDIZATION,
                    upper=None, lower=0.25,
                ),
            ],
        )
        post = cs.get_post_solve_constraints()
        assert len(post) == 1
        assert post[0].constraint_type == ConstraintType.CAPACITY_CAP

    def test_get_diagnostic_constraints(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(ctype=ConstraintType.CAPACITY_CAP),
                _make_constraint(
                    ctype=ConstraintType.SAUDIZATION,
                    upper=None, lower=0.25,
                ),
            ],
        )
        diags = cs.get_diagnostic_constraints()
        assert len(diags) == 1
        assert diags[0].constraint_type == ConstraintType.SAUDIZATION

    def test_year_filtering(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[
                _make_constraint(time_window=(2024, 2026)),
                _make_constraint(sector="A"),  # No time window = always
            ],
        )
        result = cs.get_constraints_for_sector("F", year=2025)
        assert len(result) == 1  # Only the windowed one for F
        result_a = cs.get_constraints_for_sector("A", year=2023)
        assert len(result_a) == 1  # No time window, always applies


class TestConstraintSetValidation:
    """Amendment 12: ConstraintSet.validate() checks."""

    def test_valid_set_no_issues(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[_make_constraint()],
        )
        assert cs.validate() == []

    def test_empty_set_valid(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="empty",
            constraints=[],
        )
        assert cs.validate() == []

    def test_duplicate_constraints_flagged(self) -> None:
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="dupes",
            constraints=[
                _make_constraint(),
                _make_constraint(),
            ],
        )
        issues = cs.validate()
        assert any("Duplicate" in issue for issue in issues)

    def test_economy_wide_missing_allocation_flagged(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(scope_type="all"),
            description="No allocation rule",
            upper_bound=10000.0,
            unit=ConstraintUnit.JOBS,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[c],
        )
        issues = cs.validate()
        assert any("allocation_rule" in issue for issue in issues)

    def test_unsupported_allocation_rule_flagged(self) -> None:
        c = Constraint(
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(scope_type="all", allocation_rule="equal"),
            description="Equal allocation",
            upper_bound=10000.0,
            unit=ConstraintUnit.JOBS,
            confidence=ConstraintConfidence.ASSUMED,
        )
        cs = ConstraintSet(
            workspace_id=uuid4(),
            model_version_id=new_uuid7(),
            name="test",
            constraints=[c],
        )
        issues = cs.validate()
        assert any("not implemented" in issue for issue in issues)
