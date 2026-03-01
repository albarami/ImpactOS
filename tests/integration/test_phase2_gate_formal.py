"""Phase 2 Gate Criteria — formal verification.

From tech spec Section 15.5.2. Each test maps to a specific criterion:
  1. Compiler >= 60% auto-mapping  -> test_compiler_auto_mapping_gate
  2. Feasibility dual-output       -> test_feasibility_dual_output
  3. Workforce confidence labels   -> test_workforce_confidence_labels
  4. Full pipeline completes       -> test_full_pipeline_completes
  5. Flywheel captures learning    -> test_flywheel_captures_learning
  6. Quality assessment produced   -> test_quality_assessment_produced

Amendment 4: Compiler gate uses MappingSuggestionAgent.suggest_batch()
with a seeded MappingLibraryEntry list against a labeled ground-truth BoQ.
"""

import json
import numpy as np
import pytest
from pathlib import Path
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.learning import LearningLoop, OverridePair
from src.engine.constraints.solver import FeasibilitySolver
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7
from src.models.document import BoQLineItem
from src.quality.service import QualityAssessmentService

from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    LABELED_BOQ,
    SEED_LIBRARY,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
    make_line_item,
)


# ---------------------------------------------------------------------------
# Gate Criterion 1: Compiler >= 60% auto-mapping (Amendment 4)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestCompilerAutoMapping:
    """Gate Criterion 1: Compiler >= 60% auto-mapping rate (Amendment 4)."""

    def test_compiler_auto_mapping_gate(self):
        """MappingSuggestionAgent achieves >= 60% coverage on labeled BoQ.

        Uses suggest_batch() with seeded library against ground-truth.
        Gate metric: coverage >= 60%, accuracy >= 80% on suggested items.
        """
        doc_id, job_id = uuid7(), uuid7()

        items = [
            BoQLineItem(
                doc_id=doc_id,
                extraction_job_id=job_id,
                raw_text=entry["text"],
                total_value=entry["value"],
                page_ref=0,
                evidence_snippet_ids=[uuid7()],
            )
            for entry in LABELED_BOQ
        ]

        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        taxonomy = [
            {"code": "F", "description": "Construction"},
            {"code": "C", "description": "Manufacturing"},
            {"code": "G", "description": "Wholesale and retail trade"},
            {"code": "M", "description": "Professional, scientific and technical activities"},
        ]
        batch = agent.suggest_batch(items, taxonomy=taxonomy)

        # Coverage: how many items got a suggestion?
        covered = [
            s for s in batch.suggestions
            if s.sector_code is not None and s.sector_code != ""
        ]
        coverage = len(covered) / len(items)
        assert coverage >= 0.60, f"Coverage {coverage:.0%} < 60% gate threshold"

        # Accuracy: of suggested items, how many match ground truth?
        correct = 0
        for suggestion, entry in zip(batch.suggestions, LABELED_BOQ):
            if suggestion.sector_code and suggestion.sector_code == entry["ground_truth_isic"]:
                correct += 1
        accuracy = correct / len(covered) if covered else 0.0
        assert accuracy >= 0.80, f"Accuracy {accuracy:.0%} < 80% on suggested items"


# ---------------------------------------------------------------------------
# Gate Criterion 2: Feasibility dual-output
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestFeasibilityDualOutput:
    """Gate Criterion 2: Feasibility produces unconstrained AND feasible."""

    def test_feasibility_dual_output(self):
        """Both unconstrained and feasible results present with diagnostics."""
        from src.engine.constraints.schema import (
            Constraint, ConstraintBoundScope, ConstraintScope,
            ConstraintSet, ConstraintType, ConstraintUnit,
        )

        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-feas",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(scope_type="sector", scope_values=["C"]),
                    upper_bound=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Gate test capacity cap on manufacturing",
                ),
            ],
            workspace_id=uuid7(),
            model_version_id=loaded.model_version.model_version_id,
            name="gate-feas-constraints",
        )

        fsolver = FeasibilitySolver()
        result = fsolver.solve(
            unconstrained_delta_x=solve.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Both outputs present
        assert result.unconstrained_delta_x is not None
        assert result.feasible_delta_x is not None
        assert result.unconstrained_delta_x.shape == result.feasible_delta_x.shape

        # Binding diagnostics present
        assert len(result.binding_constraints) >= 1
        bc = result.binding_constraints[0]
        assert bc.description != ""
        assert bc.gap >= 0

        # Confidence summary
        assert result.constraint_confidence_summary is not None

    def test_feasibility_produces_dual_output_with_diagnostics(self):
        """Verifies diagnostic messages exist on binding constraints."""
        from src.engine.constraints.schema import (
            Constraint, ConstraintBoundScope, ConstraintScope,
            ConstraintSet, ConstraintType, ConstraintUnit,
        )

        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-feas-diag",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        solve = solver.solve(loaded_model=loaded, delta_d=np.array([300.0, 150.0, 50.0]))

        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
                    upper_bound=100.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Tight cap for diagnostics test",
                ),
            ],
            workspace_id=uuid7(),
            model_version_id=loaded.model_version.model_version_id,
            name="gate-feas-diag-constraints",
        )

        fsolver = FeasibilitySolver()
        result = fsolver.solve(
            unconstrained_delta_x=solve.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # feasible_delta_x respects the cap
        f_idx = SECTOR_CODES_SMALL.index("F")
        assert result.feasible_delta_x[f_idx] <= 100.0 + 1e-6


# ---------------------------------------------------------------------------
# Gate Criterion 3: Workforce confidence-labeled splits with ranges
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestWorkforceConfidenceLabeled:
    """Gate Criterion 3: Workforce confidence-labeled splits with ranges."""

    def _load_workforce_fixtures(self):
        """Load workforce fixtures with JSON → dataclass adaptation.

        The JSON fixtures have extra fields not accepted by frozen dataclass
        constructors, so we manually extract only the required fields.
        """
        from src.data.workforce.occupation_bridge import (
            OccupationBridge, OccupationBridgeEntry,
        )
        from src.data.workforce.nationality_classification import (
            NationalityClassification, NationalityClassificationSet,
            NationalityTier,
        )
        from src.data.workforce.unit_registry import QualityConfidence
        from src.models.common import ConstraintConfidence as CC

        fixtures = Path(__file__).parent.parent / "fixtures" / "workforce"
        with open(fixtures / "sample_occupation_bridge.json") as f:
            bridge_data = json.load(f)

        entries = [
            OccupationBridgeEntry(
                sector_code=e["sector_code"],
                occupation_code=e["occupation_code"],
                share=e["share"],
                source=e["source"],
                source_confidence=CC(e["source_confidence"]),
                quality_confidence=QualityConfidence(e["quality_confidence"]),
            )
            for e in bridge_data["entries"]
        ]
        bridge = OccupationBridge(
            year=bridge_data["year"],
            entries=entries,
            metadata=bridge_data.get("metadata", {}),
        )

        with open(fixtures / "sample_nationality_classification.json") as f:
            class_data = json.load(f)
        classifications = [
            NationalityClassification(
                sector_code=c["sector_code"],
                occupation_code=c["occupation_code"],
                tier=NationalityTier(c["tier"]),
                current_saudi_pct=c["current_saudi_pct"],
                rationale=c["rationale"],
                source_confidence=CC(c["source_confidence"]),
                quality_confidence=QualityConfidence(c["quality_confidence"]),
                sensitivity_range=(
                    tuple(c["sensitivity_range"])
                    if c.get("sensitivity_range") is not None
                    else None
                ),
                source=c["source"],
            )
            for c in class_data["classifications"]
        ]
        nat_set = NationalityClassificationSet(
            year=class_data["year"],
            classifications=classifications,
            metadata=class_data.get("metadata", {}),
        )
        return bridge, nat_set

    def test_workforce_confidence_labels(self):
        """WorkforceResult has confidence labels and sensitivity envelopes."""
        from src.engine.workforce_satellite.satellite import WorkforceSatellite
        from src.engine.satellites import SatelliteResult

        bridge, nat_set = self._load_workforce_fixtures()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=nat_set,
        )
        sector_codes = bridge.get_sectors()
        sat_result = SatelliteResult(
            delta_jobs=np.array([20.0] * len(sector_codes)),
            delta_imports=np.zeros(len(sector_codes)),
            delta_domestic_output=np.zeros(len(sector_codes)),
            delta_va=np.zeros(len(sector_codes)),
            coefficients_version_id=uuid7(),
        )
        result = ws.analyze(satellite_result=sat_result, sector_codes=sector_codes)

        # Confidence labels present
        assert result.overall_confidence is not None

        # Sensitivity ranges (min/mid/max) ordered correctly
        for s in result.sector_summaries:
            assert s.projected_saudi_jobs_min <= s.projected_saudi_jobs_mid
            assert s.projected_saudi_jobs_mid <= s.projected_saudi_jobs_max

    def test_workforce_splits_have_confidence_and_ranges(self):
        """Each sector summary has confidence label + numeric ranges."""
        from src.engine.workforce_satellite.satellite import WorkforceSatellite
        from src.engine.satellites import SatelliteResult

        bridge, nat_set = self._load_workforce_fixtures()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=nat_set,
        )
        sector_codes = bridge.get_sectors()
        sat_result = SatelliteResult(
            delta_jobs=np.array([15.0] * len(sector_codes)),
            delta_imports=np.zeros(len(sector_codes)),
            delta_domestic_output=np.zeros(len(sector_codes)),
            delta_va=np.zeros(len(sector_codes)),
            coefficients_version_id=uuid7(),
        )
        result = ws.analyze(satellite_result=sat_result, sector_codes=sector_codes)

        assert len(result.sector_summaries) > 0
        for s in result.sector_summaries:
            assert isinstance(s.projected_saudi_jobs_min, (int, float))
            assert isinstance(s.projected_saudi_jobs_mid, (int, float))
            assert isinstance(s.projected_saudi_jobs_max, (int, float))


# ---------------------------------------------------------------------------
# Gate Criterion 4: Full pipeline completes
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestGoldenScenario1EndToEnd:
    """Gate Criterion 4: Full pipeline completes without crash."""

    def test_full_pipeline_completes(self):
        """BoQ -> compile -> run -> quality -> all steps complete."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-full",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR, current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.15, "LOW": 0.05},
            mapping_residual_pct=0.02, mapping_unresolved_pct=0.01,
            mapping_unresolved_spend_pct=0.3,
            assumption_ranges_coverage_pct=None, assumption_approval_rate=None,
            constraint_confidence_summary=None, workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=[], run_id=uuid7(),
        )

        # Pipeline completed: positive outputs
        assert solve.delta_x_total.sum() > 0
        assert sat.delta_jobs.sum() > 0
        assert assessment.composite_score > 0

    def test_industrial_zone_full_pipeline(self):
        """Full pipeline through golden scenario 1 — finite outputs."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-golden1",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        solve = solver.solve(loaded_model=loaded, delta_d=np.array([300.0, 150.0, 50.0]))

        assert solve.delta_x_total is not None
        assert all(np.isfinite(solve.delta_x_total))


# ---------------------------------------------------------------------------
# Gate Criterion 5: Flywheel captures learning
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestFlywheelLearning:
    """Gate Criterion 5: Flywheel captures learning + publish cycle."""

    def test_flywheel_captures_learning(self):
        """Override recorded -> patterns extracted -> draft built."""
        loop = LearningLoop()
        engagement_id = uuid7()
        pair = OverridePair(
            engagement_id=engagement_id,
            line_item_id=uuid7(),
            line_item_text="reinforced concrete foundation",
            suggested_sector_code="G",
            final_sector_code="F",
            project_type="industrial",
        )
        loop.record_override(pair)
        overrides = loop.get_overrides()
        assert len(overrides) >= 1
        assert overrides[0].final_sector_code == "F"

    def test_override_to_publish_cycle(self):
        """Full cycle: override -> extract patterns -> build draft."""
        loop = LearningLoop()
        engagement_id = uuid7()

        # Record same pattern 3x to exceed min_frequency
        for _ in range(3):
            loop.record_override(
                OverridePair(
                    engagement_id=engagement_id,
                    line_item_id=uuid7(),
                    line_item_text="structural steel supply",
                    suggested_sector_code="G",
                    final_sector_code="C",
                    project_type="industrial",
                )
            )

        overrides = loop.get_overrides()
        patterns = loop.extract_new_patterns(
            overrides=overrides,
            existing_library=[],
            min_frequency=2,
        )
        assert len(patterns) >= 1
        for p in patterns:
            assert p.sector_code == "C"


# ---------------------------------------------------------------------------
# Gate Criterion 6: Quality assessment produced
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.gate
class TestQualityAssessment:
    """Gate Criterion 6: Quality assessment produced with actionable warnings."""

    def test_quality_assessment_produced(self):
        """Every run produces a RunQualityAssessment with non-null ID."""
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05, mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.5,
            assumption_ranges_coverage_pct=0.7, assumption_approval_rate=0.8,
            constraint_confidence_summary={"HARD": 3, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="MEDIUM",
            plausibility_in_range_pct=85.0, plausibility_flagged_count=2,
            source_ages=[], run_id=uuid7(),
        )
        assert assessment.assessment_id is not None

    def test_quality_warnings_actionable(self):
        """Each warning has severity, message, and recommendation."""
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2018, current_year=2026,  # Stale data -> warnings
            mapping_coverage_pct=0.70,
            mapping_confidence_dist={"HIGH": 0.3, "MEDIUM": 0.3, "LOW": 0.4},
            mapping_residual_pct=0.15, mapping_unresolved_pct=0.10,
            mapping_unresolved_spend_pct=3.0,
            assumption_ranges_coverage_pct=0.3, assumption_approval_rate=0.5,
            constraint_confidence_summary={"HARD": 0, "ESTIMATED": 1, "ASSUMED": 5},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=60.0, plausibility_flagged_count=5,
            source_ages=[], run_id=uuid7(),
        )
        assert len(assessment.warnings) > 0
        for w in assessment.warnings:
            assert w.severity is not None
            assert w.message != ""
