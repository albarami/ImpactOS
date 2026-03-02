"""Integration Path 7: Doc -> Export (Amendment 3).

The full pipeline that the Build Plan requires:
1. Pre-extracted BoQ fixture (committed, not hand-constructed)
2. MappingSuggestionAgent.suggest_batch (REAL suggestions from SEED_LIBRARY)
3. Analyst approves suggestions -> MappingDecisions
4. ScenarioCompiler -> ScenarioSpec
5. Engine run -> SolveResult
6. Satellite -> SatelliteResult
7. Feasibility -> FeasibilityResult
8. Quality assessment -> RunQualityAssessment
9. Governance gate check (GOVERNED mode with resolved claims)
10. Export -> ExportRecord

Tests GOVERNED mode with resolved Claims, not just SANDBOX.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.export.orchestrator import ExportOrchestrator, ExportRequest
from src.governance.publication_gate import PublicationGate
from src.models.common import ClaimStatus, ClaimType, ExportMode
from src.models.document import BoQLineItem
from src.models.governance import Claim
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon
from src.quality.service import QualityAssessmentService

from tests.integration.golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SEED_LIBRARY,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
    make_line_item,
)


def _committed_extraction_fixture() -> list[BoQLineItem]:
    """Committed extraction fixture simulating real document extraction output.

    These items have realistic text that the SEED_LIBRARY can match against.
    """
    doc_id, job_id = uuid7(), uuid7()
    return [
        make_line_item("reinforced concrete foundation works", 50_000_000, doc_id, job_id),
        make_line_item("structural steel fabrication", 30_000_000, doc_id, job_id),
        make_line_item("engineering design consultancy services", 10_000_000, doc_id, job_id),
        make_line_item("wholesale trade building supplies", 5_000_000, doc_id, job_id),
    ]


# Taxonomy entries covering the 3 sectors in SECTOR_CODES_SMALL plus M
_TAXONOMY = [
    {"sector_code": "F", "description": "Construction"},
    {"sector_code": "C", "description": "Manufacturing"},
    {"sector_code": "G", "description": "Wholesale"},
    {"sector_code": "M", "description": "Professional services"},
]


def _run_suggestion_and_compile(
    items: list[BoQLineItem],
) -> tuple:
    """Run suggestion + compilation shared by multiple tests.

    Returns (spec, decisions, batch_result) for downstream assertions.
    """
    # 1. REAL auto-mapping suggestions from SEED_LIBRARY
    agent = MappingSuggestionAgent(library=SEED_LIBRARY)
    batch_result = agent.suggest_batch(items, taxonomy=_TAXONOMY)

    # 2. Analyst approves all suggestions -> MappingDecisions
    analyst = uuid7()
    decisions = []
    for suggestion in batch_result.suggestions:
        decisions.append(
            MappingDecision(
                line_item_id=suggestion.line_item_id,
                suggested_sector_code=suggestion.sector_code,
                suggested_confidence=suggestion.confidence,
                final_sector_code=suggestion.sector_code,
                decision_type=DecisionType.APPROVED,
                decided_by=analyst,
            )
        )

    # 3. Compile — phasing must be provided for shocks to be generated
    compiler = ScenarioCompiler()
    spec = compiler.compile(CompilationInput(
        workspace_id=uuid7(),
        scenario_name="Doc-to-Export Test",
        base_model_version_id=uuid7(),
        base_year=GOLDEN_BASE_YEAR,
        time_horizon=TimeHorizon(start_year=2024, end_year=2024),
        line_items=items,
        decisions=decisions,
        phasing={2024: 1.0},
    ))
    return spec, decisions, batch_result


def _run_engine(spec):
    """Register model, solve, compute satellites. Returns (solve_result, sat_result)."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="doc-to-export-test",
    )
    loaded = store.get(mv.model_version_id)

    # Extract delta_d from shock items
    delta_d = np.zeros(len(SECTOR_CODES_SMALL))
    sector_idx = {c: i for i, c in enumerate(SECTOR_CODES_SMALL)}
    for shock in spec.shock_items:
        if shock.sector_code in sector_idx:
            delta_d[sector_idx[shock.sector_code]] += (
                shock.amount_real_base_year * shock.domestic_share
            )

    solver = LeontiefSolver()
    solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

    sa = SatelliteAccounts()
    sat_coeff = SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )
    sat_result = sa.compute(
        delta_x=solve_result.delta_x_total,
        coefficients=sat_coeff,
    )
    return solve_result, sat_result


def _run_quality_assessment() -> object:
    """Run quality assessment with mapping-only inputs."""
    qas = QualityAssessmentService()
    assessment = qas.assess(
        base_year=GOLDEN_BASE_YEAR,
        current_year=2026,
        mapping_coverage_pct=1.0,
        mapping_confidence_dist={"HIGH": 0.75, "MEDIUM": 0.25, "LOW": 0.0},
        mapping_residual_pct=0.0,
        mapping_unresolved_pct=0.0,
        mapping_unresolved_spend_pct=0.0,
        assumption_ranges_coverage_pct=None,
        assumption_approval_rate=None,
        constraint_confidence_summary=None,
        workforce_overall_confidence=None,
        plausibility_in_range_pct=None,
        plausibility_flagged_count=None,
        source_ages=[],
        run_id=uuid7(),
    )
    return assessment


@pytest.mark.integration
@pytest.mark.gate
class TestDocToExport:
    """Full doc -> export pipeline with real suggestions + governed export."""

    def test_full_pipeline_sandbox_mode(self):
        """Full pipeline: BoQ -> suggestions -> compile -> engine -> satellite -> quality -> SANDBOX export."""
        # 1. Pre-extracted BoQ (committed fixture)
        items = _committed_extraction_fixture()

        # 2-4. Suggest + compile
        spec, decisions, batch_result = _run_suggestion_and_compile(items)
        assert len(spec.shock_items) > 0, "Compiler must produce at least one shock"

        # 5-6. Engine + satellite
        solve_result, sat_result = _run_engine(spec)
        assert float(solve_result.delta_x_total.sum()) > 0
        assert float(sat_result.delta_jobs.sum()) > 0

        # 7. Quality assessment
        assessment = _run_quality_assessment()
        assert assessment.composite_score > 0

        # 8. Export in SANDBOX mode (no claims needed)
        export_orch = ExportOrchestrator()
        record = export_orch.execute(
            request=ExportRequest(
                run_id=uuid7(),
                workspace_id=uuid7(),
                mode=ExportMode.SANDBOX,
                export_formats=["excel"],
                pack_data={
                    "scenario_name": spec.name,
                    "total_output": float(solve_result.delta_x_total.sum()),
                    "total_gdp": float(sat_result.delta_va.sum()),
                    "total_jobs": float(sat_result.delta_jobs.sum()),
                },
            ),
            claims=[],
        )
        assert record.status.value == "COMPLETED"
        assert "excel" in record.artifacts
        assert "excel" in record.checksums

    def test_full_pipeline_with_real_suggestions(self):
        """Full pipeline using MappingSuggestionAgent.suggest_batch with SEED_LIBRARY for real auto-mapping."""
        # 1. Pre-extracted BoQ (committed fixture)
        items = _committed_extraction_fixture()

        # 2. REAL auto-mapping suggestions from SEED_LIBRARY
        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        batch_result = agent.suggest_batch(items, taxonomy=_TAXONOMY)

        # Verify real suggestions are produced (not fallback)
        assert len(batch_result.suggestions) == len(items)
        for suggestion in batch_result.suggestions:
            assert suggestion.confidence > 0.1, (
                f"Suggestion for {suggestion.line_item_id} has low confidence "
                f"({suggestion.confidence}), expected library match"
            )

        # 3. Analyst approves all suggestions -> MappingDecisions
        analyst = uuid7()
        decisions = []
        for suggestion in batch_result.suggestions:
            decisions.append(
                MappingDecision(
                    line_item_id=suggestion.line_item_id,
                    suggested_sector_code=suggestion.sector_code,
                    suggested_confidence=suggestion.confidence,
                    final_sector_code=suggestion.sector_code,
                    decision_type=DecisionType.APPROVED,
                    decided_by=analyst,
                )
            )

        # 4. Compile with phasing
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Doc-to-Export Real Suggestions",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
            phasing={2024: 1.0},
        ))
        assert len(spec.shock_items) > 0

        # 5. Register model and solve
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="doc-to-export-real-suggestions",
        )
        loaded = store.get(mv.model_version_id)

        # Extract delta_d
        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {c: i for i, c in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # 6. Satellite
        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coeff,
        )

        # 7. Quality assessment
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=1.0,
            mapping_confidence_dist={"HIGH": 0.75, "MEDIUM": 0.25, "LOW": 0.0},
            mapping_residual_pct=0.0,
            mapping_unresolved_pct=0.0,
            mapping_unresolved_spend_pct=0.0,
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

        # 8. Governance: GOVERNED mode with RESOLVED claims
        gate = PublicationGate()
        resolved_claims = [
            Claim(
                text="Construction output multiplier is within OECD range",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.SUPPORTED,
            ),
            Claim(
                text="Import share based on GASTAT 2023 data",
                claim_type=ClaimType.SOURCE_FACT,
                status=ClaimStatus.SUPPORTED,
            ),
        ]
        gate_result = gate.check(claims=resolved_claims)
        assert gate_result.passed, f"Gate blocked: {gate_result.blocking_reasons}"

        # 9. Export in GOVERNED mode
        export_orch = ExportOrchestrator()
        record = export_orch.execute(
            request=ExportRequest(
                run_id=uuid7(),
                workspace_id=uuid7(),
                mode=ExportMode.GOVERNED,
                export_formats=["excel"],
                pack_data={
                    "scenario_name": spec.name,
                    "total_output": float(solve_result.delta_x_total.sum()),
                    "total_gdp": float(sat_result.delta_va.sum()),
                    "total_jobs": float(sat_result.delta_jobs.sum()),
                },
            ),
            claims=resolved_claims,
            quality_assessment=assessment,
        )
        assert record.status.value == "COMPLETED"

    def test_governed_export_blocked_without_claims(self):
        """Governed mode blocked if claims unresolved."""
        gate = PublicationGate()
        claim = Claim(
            text="Unresolved claim about labor data",
            claim_type=ClaimType.MODEL,
            status=ClaimStatus.NEEDS_EVIDENCE,
        )
        result = gate.check(claims=[claim])
        assert not result.passed
        assert len(result.blocking_reasons) > 0

    def test_governed_export_succeeds_with_resolved(self):
        """Governed mode passes after all claims resolved."""
        gate = PublicationGate()
        claims = [
            Claim(
                text="Model vintage is acceptable",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.SUPPORTED,
            ),
            Claim(
                text="Assumption about import shares",
                claim_type=ClaimType.ASSUMPTION,
                status=ClaimStatus.APPROVED_FOR_EXPORT,
            ),
            Claim(
                text="Outdated constraint removed",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.DELETED,
            ),
        ]
        result = gate.check(claims=claims)
        assert result.passed
