"""Phase 4 tests: Governance Autowiring and Disclosure Enforcement.

P4-1: Auto-create claims from run results (claim_extractor)
P4-2: Auto-draft assumptions on scenario compile (scenario_compiler)
P4-3: Publication gate blocks on DRAFT assumptions
P4-4: Disclosure tier filtering in export orchestrator
P4-5: ClaimRepository.list_by_workspace (tested separately in repositories)
"""

from uuid import UUID

from uuid_extensions import uuid7

from src.compiler.scenario_compiler import (
    CompilationInput,
    ScenarioCompiler,
    draft_compilation_assumptions,
)
from src.export.orchestrator import (
    ExportOrchestrator,
    ExportRequest,
    ExportStatus,
)
from src.governance.claim_extractor import ClaimExtractor, create_claims_from_results
from src.governance.publication_gate import PublicationGate
from src.models.common import (
    AssumptionStatus,
    AssumptionType,
    ClaimStatus,
    ClaimType,
    DisclosureTier,
    ExportMode,
)
from src.models.document import BoQLineItem
from src.models.governance import Assumption, Claim
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon
from src.quality.models import RunQualityAssessment

_CLEAN_QA = RunQualityAssessment.model_construct(used_synthetic_fallback=False)


# ===================================================================
# P4-1: Auto-create claims from run results
# ===================================================================


class TestAutoClaimsFromResults:
    """P4-1: create_claims_from_results produces Claims from result_summary."""

    def test_creates_claim_per_metric(self) -> None:
        result_summary = {
            "gdp_impact": {"2025": 4200000.0},
            "jobs": {"2025": 21200},
        }
        run_id = uuid7()
        claims = create_claims_from_results(result_summary, run_id=run_id)
        assert len(claims) == 2

    def test_claims_are_model_type(self) -> None:
        result_summary = {"gdp_impact": {"2025": 4200000.0}}
        claims = create_claims_from_results(result_summary, run_id=uuid7())
        assert all(c.claim_type == ClaimType.MODEL for c in claims)

    def test_claims_start_as_extracted(self) -> None:
        result_summary = {"gdp_impact": {"2025": 4200000.0}}
        claims = create_claims_from_results(result_summary, run_id=uuid7())
        assert all(c.status == ClaimStatus.EXTRACTED for c in claims)

    def test_claim_text_contains_metric_name(self) -> None:
        result_summary = {"gdp_impact": {"2025": 4200000.0}}
        claims = create_claims_from_results(result_summary, run_id=uuid7())
        assert any("gdp_impact" in c.text for c in claims)

    def test_empty_results_no_claims(self) -> None:
        claims = create_claims_from_results({}, run_id=uuid7())
        assert claims == []

    def test_claims_have_unique_ids(self) -> None:
        result_summary = {
            "gdp_impact": {"2025": 4200000.0},
            "jobs": {"2025": 21200},
        }
        claims = create_claims_from_results(result_summary, run_id=uuid7())
        ids = {c.claim_id for c in claims}
        assert len(ids) == 2


# ===================================================================
# P4-2: Auto-draft assumptions on scenario compile
# ===================================================================


class TestAutoDraftAssumptions:
    """P4-2: draft_compilation_assumptions creates DRAFT assumptions."""

    def _make_input(self) -> CompilationInput:
        line = BoQLineItem(
            line_item_id=uuid7(),
            doc_id=uuid7(),
            extraction_job_id=uuid7(),
            raw_text="Steel supply contract",
            description="Steel supply",
            total_value=10_000_000.0,
            page_ref=0,
            evidence_snippet_ids=[uuid7()],
        )
        decision = MappingDecision(
            line_item_id=line.line_item_id,
            decision_type=DecisionType.APPROVED,
            final_sector_code="C41",
            suggested_confidence=0.9,
            decided_by=uuid7(),
        )
        return CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test Scenario",
            base_model_version_id=uuid7(),
            base_year=2023,
            time_horizon=TimeHorizon(start_year=2023, end_year=2025),
            line_items=[line],
            decisions=[decision],
            default_domestic_share=0.65,
            default_import_share=0.35,
            phasing={2023: 0.3, 2024: 0.4, 2025: 0.3},
            deflators={2024: 1.03, 2025: 1.06},
        )

    def test_drafts_import_share_assumption(self) -> None:
        inp = self._make_input()
        assumptions = draft_compilation_assumptions(inp)
        types = {a.type for a in assumptions}
        assert AssumptionType.IMPORT_SHARE in types

    def test_drafts_phasing_assumption(self) -> None:
        inp = self._make_input()
        assumptions = draft_compilation_assumptions(inp)
        types = {a.type for a in assumptions}
        assert AssumptionType.PHASING in types

    def test_drafts_deflator_assumption(self) -> None:
        inp = self._make_input()
        assumptions = draft_compilation_assumptions(inp)
        types = {a.type for a in assumptions}
        assert AssumptionType.DEFLATOR in types

    def test_all_assumptions_are_draft(self) -> None:
        inp = self._make_input()
        assumptions = draft_compilation_assumptions(inp)
        assert all(a.status == AssumptionStatus.DRAFT for a in assumptions)

    def test_assumptions_have_justification(self) -> None:
        inp = self._make_input()
        assumptions = draft_compilation_assumptions(inp)
        assert all(len(a.justification) > 0 for a in assumptions)

    def test_no_deflators_no_deflator_assumption(self) -> None:
        inp = self._make_input()
        inp.deflators = {}
        assumptions = draft_compilation_assumptions(inp)
        types = {a.type for a in assumptions}
        assert AssumptionType.DEFLATOR not in types

    def test_compile_updates_assumptions_count(self) -> None:
        compiler = ScenarioCompiler()
        inp = self._make_input()
        spec = compiler.compile(inp)
        # assumptions_count should reflect the auto-drafted assumptions
        assert spec.data_quality_summary.assumptions_count > 0


# ===================================================================
# P4-3: Publication gate blocks on DRAFT assumptions
# ===================================================================


def _make_claim(
    status: ClaimStatus = ClaimStatus.SUPPORTED,
) -> Claim:
    return Claim(text="Some claim.", claim_type=ClaimType.MODEL, status=status)


def _make_assumption(
    status: AssumptionStatus = AssumptionStatus.DRAFT,
) -> Assumption:
    return Assumption(
        type=AssumptionType.IMPORT_SHARE,
        value=0.35,
        units="ratio",
        justification="Default import share assumption.",
        status=status,
    )


class TestGateBlocksOnAssumptions:
    """P4-3: PublicationGate.check blocks when DRAFT assumptions present."""

    def test_draft_assumption_blocks(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.SUPPORTED)]
        assumptions = [_make_assumption(AssumptionStatus.DRAFT)]
        result = gate.check(claims, assumptions=assumptions)
        assert result.passed is False

    def test_approved_assumption_passes(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.SUPPORTED)]
        from src.models.governance import AssumptionRange

        assumption = Assumption(
            type=AssumptionType.IMPORT_SHARE,
            value=0.35,
            range=AssumptionRange(min=0.25, max=0.45),
            units="ratio",
            justification="Approved import share.",
            status=AssumptionStatus.APPROVED,
        )
        result = gate.check(claims, assumptions=[assumption])
        assert result.passed is True

    def test_rejected_assumption_passes(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.SUPPORTED)]
        assumptions = [_make_assumption(AssumptionStatus.REJECTED)]
        result = gate.check(claims, assumptions=assumptions)
        assert result.passed is True

    def test_no_assumptions_passes(self) -> None:
        """Backward compat: check() without assumptions still works."""
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.SUPPORTED)]
        result = gate.check(claims)
        assert result.passed is True

    def test_blocking_reason_mentions_assumption(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.SUPPORTED)]
        assumptions = [_make_assumption(AssumptionStatus.DRAFT)]
        result = gate.check(claims, assumptions=assumptions)
        reasons = [br.reason for br in result.blocking_reasons]
        assert any("assumption" in r.lower() for r in reasons)

    def test_both_claims_and_assumptions_can_block(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(ClaimStatus.NEEDS_EVIDENCE)]
        assumptions = [_make_assumption(AssumptionStatus.DRAFT)]
        result = gate.check(claims, assumptions=assumptions)
        assert result.passed is False
        assert len(result.blocking_reasons) >= 2


# ===================================================================
# P4-4: Disclosure tier filtering in export orchestrator
# ===================================================================


def _make_pack_data_with_tiers() -> dict:
    return {
        "run_id": str(uuid7()),
        "scenario_name": "Test",
        "base_year": 2023,
        "currency": "SAR",
        "model_version_id": str(uuid7()),
        "scenario_version": 1,
        "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
        "sector_impacts": [
            {
                "sector_code": "C41",
                "sector_name": "Steel",
                "direct_impact": 500.0,
                "indirect_impact": 250.0,
                "total_impact": 750.0,
                "multiplier": 1.5,
                "domestic_share": 0.65,
                "import_leakage": 0.35,
                "disclosure_tier": "TIER1",
            },
            {
                "sector_code": "C42",
                "sector_name": "Contrarian Stress",
                "direct_impact": -100.0,
                "indirect_impact": -50.0,
                "total_impact": -150.0,
                "multiplier": 1.5,
                "domestic_share": 0.65,
                "import_leakage": 0.35,
                "disclosure_tier": "TIER0",
            },
        ],
        "input_vectors": {"C41": 1000.0},
        "sensitivity": [],
        "assumptions": [],
        "evidence_ledger": [],
    }


class TestDisclosureTierFiltering:
    """P4-4: ExportOrchestrator filters TIER0 items in GOVERNED mode."""

    def test_governed_filters_tier0_sectors(self) -> None:
        orch = ExportOrchestrator()
        pack_data = _make_pack_data_with_tiers()
        req = ExportRequest(
            run_id=uuid7(),
            workspace_id=uuid7(),
            mode=ExportMode.GOVERNED,
            export_formats=["excel"],
            pack_data=pack_data,
            disclosure_tier=DisclosureTier.TIER1,
        )
        record = orch.execute(
            request=req,
            claims=[_make_claim(ClaimStatus.SUPPORTED)],
            quality_assessment=_CLEAN_QA,
        )
        assert record.status == ExportStatus.COMPLETED
        # The pack_data used for generation should have had TIER0 items removed
        # We verify by checking the record metadata
        assert record.filtered_tier0_count == 1

    def test_sandbox_keeps_all_tiers(self) -> None:
        orch = ExportOrchestrator()
        pack_data = _make_pack_data_with_tiers()
        req = ExportRequest(
            run_id=uuid7(),
            workspace_id=uuid7(),
            mode=ExportMode.SANDBOX,
            export_formats=["excel"],
            pack_data=pack_data,
        )
        record = orch.execute(
            request=req,
            claims=[],
            quality_assessment=_CLEAN_QA,
        )
        assert record.status == ExportStatus.COMPLETED
        assert record.filtered_tier0_count == 0

    def test_default_disclosure_tier_is_tier1(self) -> None:
        """ExportRequest defaults to TIER1 disclosure tier."""
        req = ExportRequest(
            run_id=uuid7(),
            workspace_id=uuid7(),
            mode=ExportMode.GOVERNED,
            export_formats=["excel"],
            pack_data={"sector_impacts": []},
        )
        assert req.disclosure_tier == DisclosureTier.TIER1


# ===================================================================
# P4-5: ClaimRepository.list_by_workspace
# ===================================================================
# NOTE: This is tested separately in tests/repositories/ since it needs
# an async DB session. Here we verify the method signature exists.


class TestClaimRepoListByWorkspaceSignature:
    """P4-5: ClaimRepository has list_by_workspace method."""

    def test_method_exists(self) -> None:
        from src.repositories.governance import ClaimRepository

        assert hasattr(ClaimRepository, "list_by_workspace")

    def test_method_is_callable(self) -> None:
        from src.repositories.governance import ClaimRepository

        assert callable(getattr(ClaimRepository, "list_by_workspace"))
