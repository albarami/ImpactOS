"""Tests for MVP-9 Depth Engine amendments.

Covers all 9 amendments:
1. DB-backed artifact storage (tested in test_repositories_depth.py)
2. Structured shock specs (ProposedShockSpec)
3. Workspace-scoped API (tested in test_api_depth.py)
4. Classification-aware provider routing (tested in test_orchestrator.py)
5. Evidence/assumption hooks (evidence_refs fields)
6. LLM scores + deterministic threshold (tested in test_muhasaba.py)
7. ASCII class names only (tested in test_models_depth.py)
8. ExportMode verified as SANDBOX/GOVERNED
9. Per-step metadata (StepMetadata)

Additional new features:
- DirectionLabel enum
- ContrarianType enum
- AssumptionDraft model
- EngagementContext model
- PromptPack versioning
- DepthEngineResult model
- MuraqabaAgent assumption draft generation
- MuraqabaAgent framing assessment
- MuraqabaAgent missing perspectives
"""

from uuid import uuid4

import pytest

from src.agents.depth.context import EngagementContext
from src.agents.depth.prompts import PROMPT_PACK_VERSION, PromptPack
from src.models.common import (
    AssumptionStatus,
    AssumptionType,
    DisclosureTier,
    ExportMode,
    new_uuid7,
)
from src.models.depth import (
    AssumptionDraft,
    CandidateDirection,
    ContrarianDirection,
    ContrarianType,
    DepthEngineResult,
    DepthPlan,
    DepthPlanStatus,
    DepthStepName,
    DirectionLabel,
    KhawatirOutput,
    MuhasabaOutput,
    MujahadaOutput,
    MuraqabaOutput,
    ProposedShockSpec,
    QualitativeRisk,
    ScenarioSuitePlan,
    ScoredCandidate,
    StepMetadata,
    SuiteRun,
)

# ---------------------------------------------------------------------------
# Amendment 2: ProposedShockSpec
# ---------------------------------------------------------------------------


class TestProposedShockSpec:
    """Amendment 2: Structured shock specs replace dict[str, float]."""

    def test_valid_shock_spec(self):
        spec = ProposedShockSpec(
            sector_code="F",
            shock_value=100_000_000.0,
        )
        assert spec.sector_code == "F"
        assert spec.shock_value == 100_000_000.0
        assert spec.denomination == "SAR_MILLIONS"

    def test_shock_spec_with_year(self):
        spec = ProposedShockSpec(
            sector_code="C",
            shock_value=50_000.0,
            shock_year=2025,
        )
        assert spec.shock_year == 2025

    def test_import_share_override(self):
        spec = ProposedShockSpec(
            sector_code="B",
            shock_value=200_000.0,
            import_share_override=0.15,
        )
        assert spec.import_share_override == 0.15

    def test_notes_field(self):
        spec = ProposedShockSpec(
            sector_code="G",
            shock_value=10_000.0,
            notes="Retail sector demand shift",
        )
        assert spec.notes == "Retail sector demand shift"

    def test_serialization_roundtrip(self):
        spec = ProposedShockSpec(
            sector_code="F",
            shock_value=100_000.0,
            shock_year=2024,
            denomination="SAR_MILLIONS",
            import_share_override=0.20,
            notes="Construction surge",
        )
        data = spec.model_dump(mode="json")
        restored = ProposedShockSpec.model_validate(data)
        assert restored.sector_code == spec.sector_code
        assert restored.shock_value == spec.shock_value
        assert restored.notes == spec.notes

    def test_suite_run_with_shock_specs(self):
        """SuiteRun.proposed_shock_specs integrates ProposedShockSpec."""
        run = SuiteRun(
            name="Construction scenario",
            direction_id=uuid4(),
            proposed_shock_specs=[
                ProposedShockSpec(sector_code="F", shock_value=50_000.0),
                ProposedShockSpec(sector_code="C", shock_value=30_000.0),
            ],
        )
        assert len(run.proposed_shock_specs) == 2
        assert run.proposed_shock_specs[0].sector_code == "F"

    def test_contrarian_with_shock_specs(self):
        """ContrarianDirection.proposed_shock_specs integrates ProposedShockSpec."""
        cd = ContrarianDirection(
            label="Oil price collapse",
            description="Sharp oil revenue decline",
            uncomfortable_truth="Mining revenue is fragile",
            rationale="Global demand shift",
            broken_assumption="Stable oil prices",
            contrarian_type=ContrarianType.QUANTIFIED,
            proposed_shock_specs=[
                ProposedShockSpec(sector_code="B", shock_value=-200_000.0),
            ],
        )
        assert cd.proposed_shock_specs is not None
        assert len(cd.proposed_shock_specs) == 1
        assert cd.proposed_shock_specs[0].shock_value == -200_000.0


# ---------------------------------------------------------------------------
# Amendment 5: Evidence/Assumption hooks
# ---------------------------------------------------------------------------


class TestEvidenceRefs:
    """Amendment 5: evidence_refs on all fact-bearing models."""

    def test_candidate_direction_evidence_refs(self):
        ref = uuid4()
        cd = CandidateDirection(
            label="Test direction",
            description="Test",
            rationale="Test",
            source_type="insight",
            test_plan="Test",
            evidence_refs=[ref],
        )
        assert cd.evidence_refs == [ref]

    def test_candidate_direction_evidence_refs_default_none(self):
        cd = CandidateDirection(
            label="Test direction",
            description="Test",
            rationale="Test",
            source_type="insight",
            test_plan="Test",
        )
        assert cd.evidence_refs is None

    def test_khawatir_output_evidence_refs(self):
        ref = uuid4()
        output = KhawatirOutput(evidence_refs=[ref])
        assert output.evidence_refs == [ref]

    def test_bias_entry_evidence_refs(self):
        from src.models.depth import BiasEntry
        ref = uuid4()
        entry = BiasEntry(
            bias_type="anchoring",
            description="Test bias",
            severity=5.0,
            evidence_refs=[ref],
        )
        assert entry.evidence_refs == [ref]

    def test_muraqaba_output_evidence_refs(self):
        from src.models.depth import BiasRegister
        ref = uuid4()
        output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
            evidence_refs=[ref],
        )
        assert output.evidence_refs == [ref]

    def test_contrarian_direction_evidence_refs(self):
        ref1, ref2 = uuid4(), uuid4()
        cd = ContrarianDirection(
            label="Test contrarian",
            description="Test",
            uncomfortable_truth="Test",
            rationale="Test",
            broken_assumption="Test",
            evidence_refs=[ref1, ref2],
        )
        assert cd.evidence_refs == [ref1, ref2]

    def test_qualitative_risk_evidence_refs(self):
        ref = uuid4()
        risk = QualitativeRisk(
            label="Test risk",
            description="Test",
            evidence_refs=[ref],
        )
        assert risk.evidence_refs == [ref]

    def test_scored_candidate_evidence_refs(self):
        ref = uuid4()
        sc = ScoredCandidate(
            direction_id=uuid4(),
            label="Test",
            composite_score=7.0,
            novelty_score=8.0,
            feasibility_score=6.0,
            data_availability_score=7.0,
            rank=1,
            evidence_refs=[ref],
        )
        assert sc.evidence_refs == [ref]

    def test_assumption_draft_evidence_refs(self):
        ref = uuid4()
        draft = AssumptionDraft(
            name="Test assumption",
            description="Test",
            assumption_type=AssumptionType.IMPORT_SHARE,
            proposed_value="0.15",
            rationale="Test",
            evidence_refs=[ref],
        )
        assert draft.evidence_refs == [ref]


# ---------------------------------------------------------------------------
# Amendment 8: ExportMode verification
# ---------------------------------------------------------------------------


class TestExportMode:
    """Amendment 8: ExportMode on ScenarioSuitePlan must be SANDBOX or GOVERNED."""

    def test_suite_plan_default_sandbox(self):
        plan = ScenarioSuitePlan(workspace_id=uuid4())
        assert plan.export_mode == ExportMode.SANDBOX

    def test_suite_plan_governed(self):
        plan = ScenarioSuitePlan(
            workspace_id=uuid4(),
            export_mode=ExportMode.GOVERNED,
        )
        assert plan.export_mode == ExportMode.GOVERNED

    def test_depth_engine_result_default_sandbox(self):
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.COMPLETED,
        )
        assert result.export_mode == ExportMode.SANDBOX


# ---------------------------------------------------------------------------
# Amendment 9: StepMetadata
# ---------------------------------------------------------------------------


class TestStepMetadata:
    """Amendment 9: Per-step metadata for audit and cost tracking."""

    def test_valid_step_metadata(self):
        meta = StepMetadata(
            step=1,
            step_name=DepthStepName.KHAWATIR,
            prompt_pack_version="mvp9_v1",
            provider="none",
            model="fallback",
        )
        assert meta.step == 1
        assert meta.step_name == DepthStepName.KHAWATIR
        assert meta.generation_mode == "FALLBACK"

    def test_llm_metadata(self):
        meta = StepMetadata(
            step=2,
            step_name=DepthStepName.MURAQABA,
            prompt_pack_version="mvp9_v1",
            provider="anthropic",
            model="claude-sonnet",
            input_tokens=1500,
            output_tokens=800,
            duration_ms=2500,
            generation_mode="LLM",
        )
        assert meta.input_tokens == 1500
        assert meta.output_tokens == 800
        assert meta.duration_ms == 2500
        assert meta.generation_mode == "LLM"

    def test_default_tokens_zero(self):
        meta = StepMetadata(
            step=3,
            step_name=DepthStepName.MUJAHADA,
            prompt_pack_version="mvp9_v1",
            provider="none",
            model="fallback",
        )
        assert meta.input_tokens == 0
        assert meta.output_tokens == 0

    def test_timestamp_auto_generated(self):
        meta = StepMetadata(
            step=4,
            step_name=DepthStepName.MUHASABA,
            prompt_pack_version="mvp9_v1",
            provider="none",
            model="fallback",
        )
        assert meta.timestamp is not None

    def test_serialization_roundtrip(self):
        meta = StepMetadata(
            step=5,
            step_name=DepthStepName.SUITE_PLANNING,
            prompt_pack_version="mvp9_v1",
            provider="openai",
            model="gpt-4",
            input_tokens=2000,
            output_tokens=1000,
            duration_ms=5000,
            generation_mode="LLM",
        )
        data = meta.model_dump(mode="json")
        restored = StepMetadata.model_validate(data)
        assert restored.step == 5
        assert restored.provider == "openai"
        assert restored.input_tokens == 2000

    def test_depth_plan_has_step_metadata_list(self):
        plan = DepthPlan(
            workspace_id=uuid4(),
            step_metadata=[
                StepMetadata(
                    step=1,
                    step_name=DepthStepName.KHAWATIR,
                    prompt_pack_version="mvp9_v1",
                    provider="none",
                    model="fallback",
                ),
            ],
        )
        assert len(plan.step_metadata) == 1
        assert plan.step_metadata[0].step_name == DepthStepName.KHAWATIR

    def test_depth_plan_step_metadata_default_empty(self):
        plan = DepthPlan(workspace_id=uuid4())
        assert plan.step_metadata == []


# ---------------------------------------------------------------------------
# New enums: DirectionLabel, ContrarianType
# ---------------------------------------------------------------------------


class TestDirectionLabel:
    """DirectionLabel enum for Khawatir source classification."""

    def test_nafs_value(self):
        assert DirectionLabel.NAFS == "nafs"

    def test_waswas_value(self):
        assert DirectionLabel.WASWAS == "waswas"

    def test_insight_value(self):
        assert DirectionLabel.INSIGHT == "insight"

    def test_all_values_match_source_type_literal(self):
        """DirectionLabel values must match CandidateDirection.source_type literals."""
        valid_types = {"nafs", "waswas", "insight"}
        label_values = {dl.value for dl in DirectionLabel}
        assert label_values == valid_types


class TestContrarianType:
    """ContrarianType enum for quantification classification."""

    def test_quantified(self):
        assert ContrarianType.QUANTIFIED == "QUANTIFIED"

    def test_qualitative_only(self):
        assert ContrarianType.QUALITATIVE_ONLY == "QUALITATIVE_ONLY"

    def test_contrarian_direction_uses_type(self):
        cd = ContrarianDirection(
            label="Oil disruption",
            description="Test",
            uncomfortable_truth="Test",
            rationale="Test",
            broken_assumption="Test",
            contrarian_type=ContrarianType.QUANTIFIED,
        )
        assert cd.contrarian_type == ContrarianType.QUANTIFIED


# ---------------------------------------------------------------------------
# AssumptionDraft model
# ---------------------------------------------------------------------------


class TestAssumptionDraft:
    """AssumptionDraft — surfaced during Muraqaba for governance review."""

    def test_valid_draft(self):
        draft = AssumptionDraft(
            name="Import share assumption",
            description="Assumed 15% import share for sector F",
            assumption_type=AssumptionType.IMPORT_SHARE,
            proposed_value="0.15",
            rationale="Based on industry benchmark",
        )
        assert draft.name == "Import share assumption"
        assert draft.status == AssumptionStatus.DRAFT
        assert draft.assumption_draft_id is not None

    def test_with_range(self):
        draft = AssumptionDraft(
            name="Phasing assumption",
            description="Project ramp-up over 3 years",
            assumption_type=AssumptionType.PHASING,
            proposed_value="3 years",
            proposed_range=("2 years", "5 years"),
            rationale="Historical project timelines",
        )
        assert draft.proposed_range == ("2 years", "5 years")

    def test_default_status_draft(self):
        draft = AssumptionDraft(
            name="Test",
            description="Test",
            assumption_type=AssumptionType.DEFLATOR,
            proposed_value="0.02",
            rationale="Test",
        )
        assert draft.status == AssumptionStatus.DRAFT

    def test_serialization_roundtrip(self):
        draft = AssumptionDraft(
            name="Capacity cap",
            description="Max output constraint",
            assumption_type=AssumptionType.CAPACITY_CAP,
            proposed_value="500M SAR",
            proposed_range=("400M SAR", "600M SAR"),
            rationale="Engineering assessment",
        )
        data = draft.model_dump(mode="json")
        restored = AssumptionDraft.model_validate(data)
        assert restored.name == draft.name
        assert restored.assumption_type == draft.assumption_type

    def test_muraqaba_output_has_assumption_drafts(self):
        from src.models.depth import BiasRegister
        output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
            assumption_drafts=[
                AssumptionDraft(
                    name="Test",
                    description="Test",
                    assumption_type=AssumptionType.JOBS_COEFF,
                    proposed_value="5.0",
                    rationale="Test",
                ),
            ],
        )
        assert len(output.assumption_drafts) == 1


# ---------------------------------------------------------------------------
# EngagementContext model
# ---------------------------------------------------------------------------


class TestEngagementContext:
    """EngagementContext — structured business context for depth analysis."""

    def test_minimal_context(self):
        ctx = EngagementContext()
        assert ctx.context_id is not None
        assert ctx.geography == "SAU"

    def test_full_context(self):
        ws = uuid4()
        ctx = EngagementContext(
            workspace_id=ws,
            engagement_name="NEOM Phase 2 Analysis",
            client_sector="F",
            target_sectors=["F", "C", "B"],
            geography="SAU",
            base_year=2024,
            key_questions=[
                "What is the import substitution multiplier?",
                "How many jobs will be created?",
            ],
            existing_assumptions=["Construction phasing over 5 years"],
            constraints=["No division-level data available"],
        )
        assert ctx.workspace_id == ws
        assert ctx.client_sector == "F"
        assert len(ctx.target_sectors) == 3

    def test_to_context_dict(self):
        ctx = EngagementContext(
            engagement_name="Test",
            client_sector="F",
            target_sectors=["F", "C"],
            base_year=2024,
        )
        d = ctx.to_context_dict()
        assert d["engagement_name"] == "Test"
        assert d["client_sector"] == "F"
        assert d["target_sectors"] == ["F", "C"]
        assert d["base_year"] == 2024
        assert "geography" in d

    def test_to_context_dict_omits_none(self):
        ctx = EngagementContext()
        d = ctx.to_context_dict()
        # None fields like engagement_name should be omitted
        assert "engagement_name" not in d
        assert "client_sector" not in d
        assert "base_year" not in d

    def test_serialization_roundtrip(self):
        ctx = EngagementContext(
            engagement_name="Test Engagement",
            client_sector="G",
            key_questions=["Q1", "Q2"],
        )
        data = ctx.model_dump(mode="json")
        restored = EngagementContext.model_validate(data)
        assert restored.engagement_name == ctx.engagement_name


# ---------------------------------------------------------------------------
# PromptPack versioning
# ---------------------------------------------------------------------------


class TestPromptPack:
    """PromptPack — versioned prompt template collection."""

    def test_current_pack_version(self):
        pack = PromptPack.current()
        assert pack.version == PROMPT_PACK_VERSION

    def test_current_pack_has_all_steps(self):
        pack = PromptPack.current()
        for step in DepthStepName:
            assert pack.has_step(step), f"Missing step: {step}"

    def test_build_produces_string(self):
        pack = PromptPack.current()
        context = {"candidates": [], "workspace_id": "test"}
        prompt = pack.build(DepthStepName.KHAWATIR, context)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_pack_is_frozen(self):
        pack = PromptPack.current()
        with pytest.raises(AttributeError):
            pack.version = "tampered"

    def test_missing_step_raises(self):
        pack = PromptPack(version="test", builders={})
        with pytest.raises(KeyError):
            pack.build(DepthStepName.KHAWATIR, {})


# ---------------------------------------------------------------------------
# DepthEngineResult model
# ---------------------------------------------------------------------------


class TestDepthEngineResult:
    """DepthEngineResult — aggregated pipeline result."""

    def test_completed_result(self):
        ws = uuid4()
        plan = new_uuid7()
        result = DepthEngineResult(
            plan_id=plan,
            workspace_id=ws,
            status=DepthPlanStatus.COMPLETED,
            khawatir=KhawatirOutput(),
            suite_plan=ScenarioSuitePlan(workspace_id=ws),
        )
        assert result.status == DepthPlanStatus.COMPLETED
        assert result.khawatir is not None
        assert result.suite_plan is not None

    def test_partial_result(self):
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.PARTIAL,
            khawatir=KhawatirOutput(),
            degraded_steps=["MURAQABA", "MUJAHADA"],
        )
        assert result.status == DepthPlanStatus.PARTIAL
        assert len(result.degraded_steps) == 2
        assert result.muraqaba is None

    def test_failed_result(self):
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.FAILED,
            step_errors={"KHAWATIR": "LLM timeout"},
        )
        assert result.status == DepthPlanStatus.FAILED
        assert "KHAWATIR" in result.step_errors

    def test_token_totals(self):
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.COMPLETED,
            total_input_tokens=5000,
            total_output_tokens=3000,
            total_duration_ms=15000,
        )
        assert result.total_input_tokens == 5000
        assert result.total_output_tokens == 3000
        assert result.total_duration_ms == 15000

    def test_step_metadata_on_result(self):
        meta = StepMetadata(
            step=1,
            step_name=DepthStepName.KHAWATIR,
            prompt_pack_version="mvp9_v1",
            provider="none",
            model="fallback",
            duration_ms=100,
        )
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.COMPLETED,
            step_metadata=[meta],
        )
        assert len(result.step_metadata) == 1
        assert result.step_metadata[0].duration_ms == 100

    def test_default_export_mode_sandbox(self):
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=uuid4(),
            status=DepthPlanStatus.COMPLETED,
        )
        assert result.export_mode == ExportMode.SANDBOX

    def test_serialization_roundtrip(self):
        ws = uuid4()
        result = DepthEngineResult(
            plan_id=new_uuid7(),
            workspace_id=ws,
            status=DepthPlanStatus.COMPLETED,
            khawatir=KhawatirOutput(),
            total_input_tokens=1000,
            prompt_pack_version="mvp9_v1",
        )
        data = result.model_dump(mode="json")
        restored = DepthEngineResult.model_validate(data)
        assert restored.status == DepthPlanStatus.COMPLETED
        assert restored.total_input_tokens == 1000


# ---------------------------------------------------------------------------
# MuraqabaAgent MVP-9 enhancements
# ---------------------------------------------------------------------------


class TestMuraqabaAssumptionDrafts:
    """MuraqabaAgent generates AssumptionDrafts from biases."""

    def _make_candidates(self, source_types, sectors=None):
        """Helper to build candidate dicts."""
        candidates = []
        for i, st in enumerate(source_types):
            candidates.append({
                "direction_id": str(uuid4()),
                "label": f"Direction {i+1}",
                "description": f"Test direction {i+1}",
                "source_type": st,
                "sector_codes": sectors or [f"SEC{i:02d}"],
                "required_levers": [],
                "rationale": "test",
                "test_plan": "test",
            })
        return candidates

    def test_assumption_drafts_from_anchoring(self):
        from src.agents.depth.muraqaba import MuraqabaAgent
        agent = MuraqabaAgent()
        candidates = self._make_candidates(["insight"])  # Only 1 = anchoring
        output = agent.run(context={"candidates": candidates})
        assert "assumption_drafts" in output
        drafts = output["assumption_drafts"]
        assert len(drafts) >= 1
        anchoring_draft = [d for d in drafts if "exploration" in d["name"].lower()]
        assert len(anchoring_draft) == 1

    def test_assumption_drafts_from_status_quo(self):
        from src.agents.depth.muraqaba import MuraqabaAgent
        agent = MuraqabaAgent()
        candidates = self._make_candidates(
            ["nafs", "nafs", "nafs"],
            sectors=["SEC01", "SEC02", "SEC03"],  # Different sectors to avoid availability
        )
        output = agent.run(context={"candidates": candidates})
        drafts = output["assumption_drafts"]
        status_quo_drafts = [d for d in drafts if "status quo" in d["name"].lower()]
        assert len(status_quo_drafts) == 1

    def test_no_drafts_when_no_biases(self):
        from src.agents.depth.muraqaba import MuraqabaAgent
        agent = MuraqabaAgent()
        # Mixed source types, different sectors, different levers, includes stress
        candidates = [
            {
                "direction_id": str(uuid4()),
                "label": "Base case",
                "description": "Standard scenario",
                "source_type": "insight",
                "sector_codes": ["SEC01"],
                "required_levers": ["FINAL_DEMAND_SHOCK"],
                "rationale": "test",
                "test_plan": "test",
            },
            {
                "direction_id": str(uuid4()),
                "label": "Stress test scenario",
                "description": "Downside case",
                "source_type": "nafs",
                "sector_codes": ["SEC02"],
                "required_levers": ["IMPORT_SUBSTITUTION"],
                "rationale": "test",
                "test_plan": "test",
            },
            {
                "direction_id": str(uuid4()),
                "label": "Innovation push",
                "description": "Tech-driven growth",
                "source_type": "insight",
                "sector_codes": ["SEC03"],
                "required_levers": ["LOCAL_CONTENT"],
                "rationale": "test",
                "test_plan": "test",
            },
        ]
        output = agent.run(context={"candidates": candidates})
        drafts = output["assumption_drafts"]
        assert len(drafts) == 0

    def test_assumption_draft_has_valid_type(self):
        from src.agents.depth.muraqaba import MuraqabaAgent
        agent = MuraqabaAgent()
        candidates = self._make_candidates(["insight"])
        output = agent.run(context={"candidates": candidates})
        for draft in output["assumption_drafts"]:
            assert draft["assumption_type"] in [at.value for at in AssumptionType]

    def test_assumption_draft_default_status_draft(self):
        from src.agents.depth.muraqaba import MuraqabaAgent
        agent = MuraqabaAgent()
        candidates = self._make_candidates(["insight"])
        output = agent.run(context={"candidates": candidates})
        for draft in output["assumption_drafts"]:
            assert draft["status"] == AssumptionStatus.DRAFT.value


class TestMuraqabaFramingAssessment:
    """MuraqabaAgent framing assessment."""

    def test_all_nafs_framing(self):
        from src.agents.depth.muraqaba import _assess_framing
        candidates = [
            {"source_type": "nafs"},
            {"source_type": "nafs"},
        ]
        framing = _assess_framing(candidates)
        assert framing is not None
        assert "ego-driven" in framing.lower() or "nafs" in framing.lower()

    def test_all_insight_framing(self):
        from src.agents.depth.muraqaba import _assess_framing
        candidates = [
            {"source_type": "insight"},
            {"source_type": "insight"},
        ]
        framing = _assess_framing(candidates)
        assert framing is not None
        assert "insight" in framing.lower()

    def test_mixed_framing(self):
        from src.agents.depth.muraqaba import _assess_framing
        candidates = [
            {"source_type": "insight"},
            {"source_type": "nafs"},
            {"source_type": "waswas"},
        ]
        framing = _assess_framing(candidates)
        assert framing is not None
        assert "mixed" in framing.lower() or "insight" in framing.lower()

    def test_empty_returns_none(self):
        from src.agents.depth.muraqaba import _assess_framing
        assert _assess_framing([]) is None


class TestMuraqabaMissingPerspectives:
    """MuraqabaAgent missing perspective identification."""

    def test_identifies_missing_supply(self):
        from src.agents.depth.muraqaba import _identify_missing_perspectives
        candidates = [
            {"label": "Demand growth", "description": "GDP-driven demand increase"},
        ]
        missing = _identify_missing_perspectives(candidates)
        assert any("supply" in m.lower() for m in missing)

    def test_identifies_missing_regulatory(self):
        from src.agents.depth.muraqaba import _identify_missing_perspectives
        candidates = [
            {"label": "Construction surge", "description": "Building activity increase"},
        ]
        missing = _identify_missing_perspectives(candidates)
        assert any("regulat" in m.lower() or "policy" in m.lower() for m in missing)

    def test_no_missing_when_comprehensive(self):
        from src.agents.depth.muraqaba import _identify_missing_perspectives
        candidates = [
            {
                "label": "Supply disruption scenario",
                "description": (
                    "Supply chain regulatory policy shift with"
                    " technology innovation and workforce"
                    " employment impact"
                ),
            },
        ]
        missing = _identify_missing_perspectives(candidates)
        assert len(missing) == 0

    def test_empty_returns_empty(self):
        from src.agents.depth.muraqaba import _identify_missing_perspectives
        assert _identify_missing_perspectives([]) == []


# ---------------------------------------------------------------------------
# Enhanced model fields
# ---------------------------------------------------------------------------


class TestEnhancedModelFields:
    """Tests for new fields added to existing models."""

    def test_khawatir_output_timestamp(self):
        output = KhawatirOutput()
        assert output.timestamp is not None

    def test_khawatir_output_engagement_context_summary(self):
        output = KhawatirOutput(
            engagement_context_summary="NEOM Phase 2 construction analysis"
        )
        assert output.engagement_context_summary is not None

    def test_muraqaba_output_framing_assessment(self):
        from src.models.depth import BiasRegister
        output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
            framing_assessment="Mostly analytical",
        )
        assert output.framing_assessment == "Mostly analytical"

    def test_muraqaba_output_missing_perspectives(self):
        from src.models.depth import BiasRegister
        output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
            missing_perspectives=["Supply-side scenarios", "Policy scenarios"],
        )
        assert len(output.missing_perspectives) == 2

    def test_muraqaba_output_timestamp(self):
        from src.models.depth import BiasRegister
        output = MuraqabaOutput(
            bias_register=BiasRegister(entries=[], overall_bias_risk=0.0),
        )
        assert output.timestamp is not None

    def test_mujahada_output_timestamp(self):
        output = MujahadaOutput()
        assert output.timestamp is not None

    def test_muhasaba_output_timestamp(self):
        output = MuhasabaOutput()
        assert output.timestamp is not None

    def test_contrarian_source_direction_ids(self):
        src_id = uuid4()
        cd = ContrarianDirection(
            label="Test",
            description="Test",
            uncomfortable_truth="Test",
            rationale="Test",
            broken_assumption="Test",
            source_direction_ids=[src_id],
        )
        assert cd.source_direction_ids == [src_id]

    def test_contrarian_disclosure_tier_default_tier0(self):
        cd = ContrarianDirection(
            label="Test",
            description="Test",
            uncomfortable_truth="Test",
            rationale="Test",
            broken_assumption="Test",
        )
        assert cd.disclosure_tier == DisclosureTier.TIER0

    def test_candidate_disclosure_tier_default_tier1(self):
        cd = CandidateDirection(
            label="Test",
            description="Test",
            rationale="Test",
            source_type="insight",
            test_plan="Test",
        )
        assert cd.disclosure_tier == DisclosureTier.TIER1

    def test_qualitative_risk_trigger_conditions(self):
        risk = QualitativeRisk(
            label="Test",
            description="Test",
            trigger_conditions=["Oil price < $40", "OPEC+ collapse"],
            expected_direction="negative",
        )
        assert len(risk.trigger_conditions) == 2
        assert risk.expected_direction == "negative"

    def test_bias_entry_mitigation(self):
        from src.models.depth import BiasEntry
        entry = BiasEntry(
            bias_type="anchoring",
            description="Test",
            severity=5.0,
            mitigation="Expand candidate set with contrarian directions",
        )
        assert entry.mitigation is not None

    def test_suite_run_is_contrarian_flag(self):
        run = SuiteRun(
            name="Contrarian run",
            direction_id=uuid4(),
            is_contrarian=True,
        )
        assert run.is_contrarian is True

    def test_suite_plan_engagement_id(self):
        eid = uuid4()
        plan = ScenarioSuitePlan(
            workspace_id=uuid4(),
            engagement_id=eid,
        )
        assert plan.engagement_id == eid

    def test_suite_plan_notes(self):
        plan = ScenarioSuitePlan(
            workspace_id=uuid4(),
            notes="Generated for Phase 2 review meeting",
        )
        assert plan.notes is not None

    def test_depth_plan_engagement_id(self):
        eid = uuid4()
        plan = DepthPlan(
            workspace_id=uuid4(),
            engagement_id=eid,
        )
        assert plan.engagement_id == eid
