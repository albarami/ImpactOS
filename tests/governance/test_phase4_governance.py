"""Phase 4 tests: Governance Autowiring and Disclosure Enforcement.

P4-1: Auto-create claims from run results (claim_extractor)
P4-2: Auto-draft assumptions on scenario compile (scenario_compiler)
P4-3: Publication gate blocks on DRAFT assumptions
P4-4: Disclosure tier filtering in export orchestrator
P4-5: ClaimRepository.list_by_workspace (tested separately in repositories)
P4-1/2/3 autowiring: Tests proving governance is wired on real service paths.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


# ===================================================================
# P4-1 autowiring: Claims auto-created on real run path
# ===================================================================

pytestmark_anyio = pytest.mark.anyio


class TestAutoClaimsOnRunPath:
    """P4-1: RunExecutionService.execute_from_scenario must auto-create claims."""

    @pytest.mark.anyio
    async def test_execute_from_scenario_creates_claims(self) -> None:
        """After a successful engine run, claims are persisted via claim_repo."""
        from src.services.run_execution import (
            RunExecutionService, RunFromScenarioInput, RunRepositories,
        )

        ws_id = uuid7()
        spec_id = uuid7()
        run_id = uuid7()
        mv_id = uuid7()

        # Mock scenario row
        scenario_row = MagicMock()
        scenario_row.scenario_spec_id = spec_id
        scenario_row.version = 1
        scenario_row.workspace_id = ws_id
        scenario_row.base_model_version_id = mv_id
        scenario_row.base_year = 2023
        scenario_row.name = "Test"
        scenario_row.shock_items = []

        # Mock model version row (curated_real provenance)
        mv_row = MagicMock()
        mv_row.provenance_class = "curated_real"

        # Mock repos
        scenario_repo = AsyncMock()
        scenario_repo.get_latest_by_workspace = AsyncMock(return_value=scenario_row)
        mv_repo = AsyncMock()
        mv_repo.get = AsyncMock(return_value=mv_row)
        md_repo = AsyncMock()
        snap_repo = AsyncMock()
        snap_repo.create = AsyncMock()
        rs_repo = AsyncMock()
        rs_repo.create = AsyncMock()

        # Mock result set rows from DB
        rs_row1 = MagicMock()
        rs_row1.metric_type = "total_output"
        rs_row1.values = {"2023": 5000.0}
        rs_row1.series_kind = None
        rs_row2 = MagicMock()
        rs_row2.metric_type = "jobs"
        rs_row2.values = {"2023": 200}
        rs_row2.series_kind = None
        rs_repo.get_by_run = AsyncMock(return_value=[rs_row1, rs_row2])

        # Mock claim_repo to capture creates
        claim_repo = AsyncMock()
        claim_repo.create = AsyncMock()

        repos = RunRepositories(
            scenario_repo=scenario_repo,
            mv_repo=mv_repo,
            md_repo=md_repo,
            snap_repo=snap_repo,
            rs_repo=rs_repo,
        )
        repos.claim_repo = claim_repo  # P4-1: new repo

        svc = RunExecutionService()

        # Mock _ensure_model_loaded and BatchRunner
        import numpy as np
        from src.engine.batch import SingleRunResult
        from src.models.common import new_uuid7
        from src.engine.model_store import LoadedModel

        mock_loaded = MagicMock(spec=LoadedModel)
        mock_loaded.sector_codes = ["A", "B", "C"]

        mock_snapshot = MagicMock()
        mock_snapshot.run_id = run_id
        mock_snapshot.model_version_id = mv_id
        mock_sr = MagicMock(spec=SingleRunResult)
        mock_sr.snapshot = mock_snapshot
        mock_sr.result_sets = []

        mock_batch_result = MagicMock()
        mock_batch_result.run_results = [mock_sr]

        with (
            patch.object(svc, "_ensure_model_loaded", return_value=mock_loaded),
            patch("src.services.run_execution.load_satellite_coefficients") as mock_sat,
            patch("src.services.run_execution.BatchRunner") as MockRunner,
        ):
            mock_sat_result = MagicMock()
            mock_sat_result.coefficients = MagicMock()
            mock_sat.return_value = mock_sat_result
            MockRunner.return_value.run.return_value = mock_batch_result

            inp = RunFromScenarioInput(
                workspace_id=ws_id,
                scenario_spec_id=spec_id,
            )
            result = await svc.execute_from_scenario(inp, repos)

        assert result.status == "COMPLETED"
        # P4-1: claim_repo.create must have been called (once per metric)
        assert claim_repo.create.call_count == 2, (
            f"Expected 2 claim creates (one per metric), got {claim_repo.create.call_count}"
        )


# ===================================================================
# P4-2 autowiring: Assumptions auto-created on real build path
# ===================================================================


class TestAutoDraftAssumptionsOnBuildPath:
    """P4-2: _handle_build_scenario must auto-draft assumptions."""

    @pytest.mark.anyio
    async def test_build_scenario_creates_assumptions(self) -> None:
        """After building a scenario, DRAFT assumptions are persisted."""
        from src.services.chat_tool_executor import ChatToolExecutor

        ws_id = uuid7()
        session = AsyncMock()

        # Mock ScenarioVersionRepository.create
        scenario_row = MagicMock()
        scenario_row.scenario_spec_id = uuid7()
        scenario_row.version = 1
        scenario_row.name = "Test"
        scenario_row.base_year = 2023

        assumption_repo = AsyncMock()
        assumption_repo.create = AsyncMock()

        mock_svr_class = MagicMock()
        mock_svr_class.return_value.create = AsyncMock(return_value=scenario_row)

        mock_ar_class = MagicMock()
        mock_ar_class.return_value = assumption_repo

        with (
            patch(
                "src.repositories.scenarios.ScenarioVersionRepository",
                mock_svr_class,
            ),
            patch(
                "src.repositories.governance.AssumptionRepository",
                mock_ar_class,
            ),
        ):
            executor = ChatToolExecutor(session=session, workspace_id=ws_id)
            result = await executor._handle_build_scenario({
                "name": "Test Scenario",
                "base_year": 2023,
                "base_model_version_id": str(uuid7()),
            })

        assert "scenario_spec_id" in result
        # P4-2: assumption_repo.create must have been called for DRAFT assumptions
        assert assumption_repo.create.call_count >= 1, (
            f"Expected assumption creates for import share, got {assumption_repo.create.call_count}"
        )


# ===================================================================
# P4-3 autowiring: Assumptions loaded and passed on export path
# ===================================================================


class TestAssumptionsOnExportPath:
    """P4-3: Export path must load and pass assumptions to orchestrator.

    Step 1 update: When run has scenario_spec_id, assumptions are loaded
    via list_linked_to (scoped to scenario), not list_by_workspace.
    Legacy runs without scenario_spec_id fall back to workspace scope.
    """

    @pytest.mark.anyio
    async def test_export_loads_and_passes_assumptions(self) -> None:
        """ExportExecutionService.execute must load assumptions and pass to orchestrator.

        Step 1: Now uses list_linked_to when scenario_spec_id is set.
        """
        from src.services.export_execution import (
            ExportExecutionService, ExportExecutionInput, ExportRepositories,
        )

        ws_id = uuid7()
        run_id = uuid7()
        scenario_id = uuid7()

        # Mock snapshot row — Step 1: has scenario_spec_id
        snap_row = MagicMock()
        snap_row.workspace_id = ws_id
        snap_row.model_version_id = uuid7()
        snap_row.scenario_spec_id = scenario_id

        snap_repo = AsyncMock()
        snap_repo.get = AsyncMock(return_value=snap_row)

        claim_repo = AsyncMock()
        claim_repo.get_by_run = AsyncMock(return_value=[])

        quality_repo = AsyncMock()
        quality_repo.get_by_run = AsyncMock(return_value=None)

        mv_row = MagicMock()
        mv_row.provenance_class = "curated_real"
        mv_repo = AsyncMock()
        mv_repo.get = AsyncMock(return_value=mv_row)

        export_repo = AsyncMock()
        export_repo.create = AsyncMock()

        artifact_store = MagicMock()

        # Mock assumption_repo with DRAFT assumptions
        from src.db.tables import AssumptionRow
        assumption_row = MagicMock()
        assumption_row.assumption_id = uuid7()
        assumption_row.type = "IMPORT_SHARE"
        assumption_row.value = 0.35
        assumption_row.range_json = None
        assumption_row.units = "ratio"
        assumption_row.justification = "Default import share"
        assumption_row.evidence_refs = []
        assumption_row.status = "DRAFT"
        assumption_row.approved_by = None
        assumption_row.approved_at = None
        assumption_row.created_at = MagicMock()
        assumption_row.updated_at = MagicMock()

        assumption_repo = AsyncMock()
        # Step 1: list_linked_to used when scenario_spec_id is present
        assumption_repo.list_linked_to = AsyncMock(
            return_value=[assumption_row],
        )
        # Legacy fallback still available
        assumption_repo.list_by_workspace = AsyncMock(
            return_value=([assumption_row], 1),
        )

        repos = ExportRepositories(
            export_repo=export_repo,
            claim_repo=claim_repo,
            quality_repo=quality_repo,
            snap_repo=snap_repo,
            mv_repo=mv_repo,
            artifact_store=artifact_store,
        )
        repos.assumption_repo = assumption_repo  # P4-3: new repo

        svc = ExportExecutionService()
        inp = ExportExecutionInput(
            workspace_id=ws_id,
            run_id=run_id,
            mode=ExportMode.GOVERNED,
            export_formats=["excel"],
            pack_data={"sector_impacts": []},
        )

        with patch(
            "src.services.export_execution._orchestrator"
        ) as mock_orch:
            # Make orchestrator return BLOCKED (since DRAFT assumption)
            from src.export.orchestrator import ExportRecord, ExportStatus
            mock_record = MagicMock(spec=ExportRecord)
            mock_record.export_id = uuid7()
            mock_record.run_id = run_id
            mock_record.mode = ExportMode.GOVERNED
            mock_record.status = ExportStatus.BLOCKED
            mock_record.blocking_reasons = ["DRAFT assumptions present"]
            mock_record.checksums = {}
            mock_record.artifacts = {}
            mock_orch.execute.return_value = mock_record

            result = await svc.execute(inp, repos)

            # Step 1: Verify scoped loading was used (not workspace-wide)
            assumption_repo.list_linked_to.assert_called_once_with(
                scenario_id, link_type="scenario",
            )
            # Workspace-wide should NOT have been called
            assumption_repo.list_by_workspace.assert_not_called()

            # Verify assumptions were passed to orchestrator
            call_kwargs = mock_orch.execute.call_args.kwargs
            assert "assumptions" in call_kwargs, (
                "P4-3: assumptions must be passed to orchestrator.execute()"
            )
            assert call_kwargs["assumptions"] is not None
