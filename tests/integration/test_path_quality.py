"""Integration Path 6: Quality Assessment integration.

Tests that QualityAssessmentService receives real signals from all modules
and produces valid RunQualityAssessment results.

Includes one test with REAL upstream modules (no mocks):
  REAL compiler -> REAL engine -> REAL constraints -> QualityAssessmentService
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.quality.models import QualityGrade
from src.quality.service import QualityAssessmentService
from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
    make_line_item,
)


@pytest.mark.integration
@pytest.mark.gate
class TestQualityAssessment:
    """Quality assessment from constructed signal inputs."""

    def test_all_good_signals_high_grade(self):
        """All perfect signals -> grade A or B."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            mapping_residual_pct=0.03,
            mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.8,
            assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 8, "ESTIMATED": 2, "ASSUMED": 0},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0,
            plausibility_flagged_count=1,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.composite_score > 0
        assert assessment.grade in (QualityGrade.A, QualityGrade.B)
        assert len(assessment.dimension_assessments) >= 6

    def test_degraded_signals_lower_grade(self):
        """Old model, low confidence -> grade C or D."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2018,
            current_year=2026,
            mapping_coverage_pct=0.60,
            mapping_confidence_dist={"HIGH": 0.2, "MEDIUM": 0.3, "LOW": 0.5},
            mapping_residual_pct=0.15,
            mapping_unresolved_pct=0.10,
            mapping_unresolved_spend_pct=3.0,
            assumption_ranges_coverage_pct=0.4,
            assumption_approval_rate=0.5,
            constraint_confidence_summary={"HARD": 1, "ESTIMATED": 2, "ASSUMED": 7},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=60.0,
            plausibility_flagged_count=8,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.composite_score > 0
        assert assessment.grade in (QualityGrade.C, QualityGrade.D, QualityGrade.F)
        # Should have vintage warning (model 8 years old)
        vintage_warnings = [
            w for w in assessment.warnings
            if w.dimension.value == "VINTAGE"
        ]
        assert len(vintage_warnings) > 0

    def test_quality_assessment_produced(self):
        """Basic assertion: quality has score + grade."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05,
            mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.0,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.composite_score > 0
        assert assessment.grade in list(QualityGrade)
        assert len(assessment.dimension_assessments) > 0


@pytest.mark.integration
class TestQualityFromRealUpstream:
    """Quality assessment with real upstream modules -- no mocks.

    Feeds compiler output -> engine -> constraints ->
    QualityAssessmentService using the 3-sector toy model. This verifies
    that the actual signals produced by upstream modules are compatible
    with the quality scorer.
    """

    def test_quality_from_real_upstream(self):
        """Full real pipeline: compiler -> engine -> constraints -> quality."""
        from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
        from src.engine.constraints.schema import (
            Constraint,
            ConstraintBoundScope,
            ConstraintScope,
            ConstraintSet,
            ConstraintType,
            ConstraintUnit,
        )
        from src.engine.constraints.solver import FeasibilitySolver
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore
        from src.engine.satellites import SatelliteCoefficients
        from src.models.common import ConstraintConfidence, new_uuid7
        from src.models.mapping import DecisionType, MappingDecision
        from src.models.scenario import TimeHorizon

        # 1. REAL compiler
        items = [
            make_line_item("concrete foundation", 50_000_000),
            make_line_item("steel fabrication", 30_000_000),
        ]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F",
                suggested_confidence=0.9,
                final_sector_code="F",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
            MappingDecision(
                line_item_id=items[1].line_item_id,
                suggested_sector_code="C",
                suggested_confidence=0.85,
                final_sector_code="C",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Quality Real Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
        ))

        # 2. REAL engine
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="quality-real-test",
        )
        loaded = store.get(mv.model_version_id)

        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {c: i for i, c in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # 3. REAL constraints
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        constraint_set = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                    upper_bound=500.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity",
                ),
            ],
            workspace_id=uuid7(),
            model_version_id=loaded.model_version.model_version_id,
            name="quality-real-test-constraints",
        )
        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraint_set,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # 4. REAL quality assessment -- feed actual upstream signals
        svc = QualityAssessmentService()
        conf_summary = feas_result.constraint_confidence_summary
        assessment = svc.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=1.0,
            mapping_confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            mapping_residual_pct=0.0,
            mapping_unresolved_pct=0.0,
            mapping_unresolved_spend_pct=0.0,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary={
                "HARD": conf_summary.hard_count,
                "ESTIMATED": conf_summary.estimated_count,
                "ASSUMED": conf_summary.assumed_count,
            },
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.grade in list(QualityGrade)
        assert assessment.composite_score > 0
        assert len(assessment.dimension_assessments) > 0
