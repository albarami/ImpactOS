"""Tests for default Saudi constraint templates."""

from src.engine.constraints.defaults import (
    _DEFAULT_MAX_GROWTH,
    _SECTOR_MAX_GROWTH,
    build_default_saudi_constraints,
)
from src.engine.constraints.schema import (
    ConstraintBoundScope,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence


class TestBuildDefaultSaudiConstraints:
    """build_default_saudi_constraints tests."""

    def test_returns_constraint_set(self) -> None:
        cs = build_default_saudi_constraints(["F", "C"])
        assert cs.name == "Saudi default constraints (ASSUMED)"
        assert cs.metadata["version"] == "mvp10_v1"

    def test_sector_specific_ramp_created(self) -> None:
        cs = build_default_saudi_constraints(["F"])
        ramps = cs.get_constraints_by_type(ConstraintType.RAMP)
        sector_ramps = [
            c for c in ramps
            if c.scope.scope_type == "sector" and c.scope.scope_values == ["F"]
        ]
        assert len(sector_ramps) == 1
        assert sector_ramps[0].max_growth_rate == 0.15  # Construction 15%

    def test_construction_rate_is_15_pct(self) -> None:
        cs = build_default_saudi_constraints(["F"])
        ramps = [
            c for c in cs.constraints
            if c.constraint_type == ConstraintType.RAMP
            and c.scope.scope_type == "sector"
        ]
        assert ramps[0].max_growth_rate == 0.15

    def test_mining_rate_is_8_pct(self) -> None:
        cs = build_default_saudi_constraints(["B"])
        ramps = [
            c for c in cs.constraints
            if c.constraint_type == ConstraintType.RAMP
            and c.scope.scope_type == "sector"
        ]
        assert ramps[0].max_growth_rate == 0.08

    def test_unknown_sector_gets_default_rate(self) -> None:
        cs = build_default_saudi_constraints(["Z"])
        ramps = [
            c for c in cs.constraints
            if c.constraint_type == ConstraintType.RAMP
            and c.scope.scope_type == "sector"
        ]
        assert ramps[0].max_growth_rate == _DEFAULT_MAX_GROWTH

    def test_economy_wide_ramp_always_included(self) -> None:
        cs = build_default_saudi_constraints(["F", "C"])
        economy_wide = [
            c for c in cs.constraints
            if c.scope.scope_type == "all"
        ]
        assert len(economy_wide) == 1
        assert economy_wide[0].max_growth_rate == _DEFAULT_MAX_GROWTH
        assert economy_wide[0].scope.allocation_rule == "proportional"

    def test_all_constraints_confidence_assumed(self) -> None:
        cs = build_default_saudi_constraints(["F", "C", "B"])
        for c in cs.constraints:
            assert c.confidence == ConstraintConfidence.ASSUMED

    def test_all_ramps_use_absolute_total_scope(self) -> None:
        cs = build_default_saudi_constraints(["F", "C"])
        for c in cs.constraints:
            if c.constraint_type == ConstraintType.RAMP:
                assert c.bound_scope == ConstraintBoundScope.ABSOLUTE_TOTAL

    def test_all_ramps_use_growth_rate_unit(self) -> None:
        cs = build_default_saudi_constraints(["F"])
        for c in cs.constraints:
            if c.constraint_type == ConstraintType.RAMP:
                assert c.unit == ConstraintUnit.GROWTH_RATE

    def test_notes_contain_rationale(self) -> None:
        cs = build_default_saudi_constraints(["F"])
        ramps = [
            c for c in cs.constraints
            if c.constraint_type == ConstraintType.RAMP
            and c.scope.scope_type == "sector"
        ]
        assert ramps[0].notes is not None
        assert "Construction" in ramps[0].notes

    def test_multiple_sectors_create_correct_count(self) -> None:
        codes = ["A", "B", "C", "F", "G"]
        cs = build_default_saudi_constraints(codes)
        sector_ramps = [
            c for c in cs.constraints
            if c.constraint_type == ConstraintType.RAMP
            and c.scope.scope_type == "sector"
        ]
        # One ramp per sector
        assert len(sector_ramps) == len(codes)
        # Plus one economy-wide
        economy = [c for c in cs.constraints if c.scope.scope_type == "all"]
        assert len(economy) == 1

    def test_all_known_sectors_have_rates(self) -> None:
        """Every sector in _SECTOR_MAX_GROWTH should get its rate."""
        known_codes = list(_SECTOR_MAX_GROWTH.keys())
        cs = build_default_saudi_constraints(known_codes)
        for code in known_codes:
            sector_ramps = [
                c for c in cs.constraints
                if c.constraint_type == ConstraintType.RAMP
                and c.scope.scope_type == "sector"
                and c.scope.scope_values == [code]
            ]
            assert len(sector_ramps) == 1
            expected_rate = _SECTOR_MAX_GROWTH[code][0]
            assert sector_ramps[0].max_growth_rate == expected_rate

    def test_workspace_and_model_ids_set(self) -> None:
        from uuid import uuid4
        ws = uuid4()
        mv = uuid4()
        cs = build_default_saudi_constraints(
            ["F"],
            workspace_id=ws,
            model_version_id=mv,
        )
        assert cs.workspace_id == ws
        assert cs.model_version_id == mv

    def test_validate_returns_no_issues(self) -> None:
        cs = build_default_saudi_constraints(["F", "C", "B"])
        issues = cs.validate()
        assert issues == []
