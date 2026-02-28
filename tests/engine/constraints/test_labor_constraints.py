"""Tests for D-4 labor constraint builder."""

from dataclasses import dataclass

from src.engine.constraints.labor_constraints import build_labor_constraints_from_d4
from src.engine.constraints.schema import ConstraintType
from src.models.common import ConstraintConfidence


@dataclass(frozen=True)
class _MockEmploymentCoefficient:
    sector_code: str
    total_employment: float


@dataclass(frozen=True)
class _MockEmploymentCoefficientSet:
    coefficients: list[_MockEmploymentCoefficient]


@dataclass(frozen=True)
class _MockSectorTarget:
    effective_target_pct: float


@dataclass(frozen=True)
class _MockMacroTargets:
    targets: dict[str, _MockSectorTarget | None]


class TestBuildLaborConstraints:
    """build_labor_constraints_from_d4 tests."""

    def test_labor_cap_from_employment(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
                _MockEmploymentCoefficient(sector_code="C", total_employment=5000),
            ],
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
            max_employment_growth=1.0,
        )

        labor = [c for c in constraints if c.constraint_type == ConstraintType.LABOR]
        assert len(labor) == 2
        f_labor = [c for c in labor if c.scope.scope_values == ["F"]][0]
        assert f_labor.upper_bound == 20000.0  # 10000 * (1 + 1.0)

    def test_confidence_is_estimated(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
            ],
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
        )

        for c in constraints:
            assert c.confidence == ConstraintConfidence.ESTIMATED

    def test_saudization_from_nitaqat(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
            ],
        )
        targets = _MockMacroTargets(
            targets={"F": _MockSectorTarget(effective_target_pct=0.25)},
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
            nitaqat_targets=targets,
        )

        saud = [c for c in constraints if c.constraint_type == ConstraintType.SAUDIZATION]
        assert len(saud) == 1
        assert saud[0].lower_bound == 0.25
        assert saud[0].scope.scope_values == ["F"]

    def test_missing_sector_handled(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
            ],
        )
        targets = _MockMacroTargets(
            targets={"G": _MockSectorTarget(effective_target_pct=0.30)},
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
            nitaqat_targets=targets,
        )

        # G has target but no employment data — no saudization constraint for G
        saud = [c for c in constraints if c.constraint_type == ConstraintType.SAUDIZATION]
        assert len(saud) == 0

    def test_none_target_skipped(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
            ],
        )
        targets = _MockMacroTargets(
            targets={"F": None},
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
            nitaqat_targets=targets,
        )

        saud = [c for c in constraints if c.constraint_type == ConstraintType.SAUDIZATION]
        assert len(saud) == 0

    def test_filter_by_sector_codes(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=10000),
                _MockEmploymentCoefficient(sector_code="C", total_employment=5000),
            ],
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
            sector_codes=["F"],
        )

        # Only F should have constraints
        assert all(c.scope.scope_values == ["F"] for c in constraints)

    def test_zero_employment_skipped(self) -> None:
        coeff_set = _MockEmploymentCoefficientSet(
            coefficients=[
                _MockEmploymentCoefficient(sector_code="F", total_employment=0),
            ],
        )
        constraints = build_labor_constraints_from_d4(
            employment_coefficients=coeff_set,
        )

        assert len(constraints) == 0
