"""Tests for depth engine Pydantic models — src/models/depth.py.

Covers:
- Schema validation (field constraints, required fields)
- Al-Muhasabi source labeling (source_type)
- Agent-to-math boundary (QualitativeRisk.not_modeled always True)
- Score bounds (0-10)
- ScoredCandidate accept/reject with rationale
- SuiteRun executable levers structure
- ScenarioSuitePlan runs + recommended_outputs
- DepthPlan degraded_steps + step_errors tracking
- Typed output models per step
- Disclosure tier defaults
"""

import pytest
from uuid import uuid4

from src.models.common import DisclosureTier, new_uuid7
from src.models.depth import (
    BiasEntry,
    BiasRegister,
    CandidateDirection,
    ContrarianDirection,
    DepthArtifact,
    DepthPlan,
    DepthPlanStatus,
    DepthStepName,
    KhawatirOutput,
    MuhasabaOutput,
    MujahadaOutput,
    MuraqabaOutput,
    QualitativeRisk,
    ScenarioSuitePlan,
    ScoredCandidate,
    SuiteRun,
    SuitePlanningOutput,
)


# ---------------------------------------------------------------------------
# DepthStepName enum
# ---------------------------------------------------------------------------


class TestDepthStepName:
    def test_all_five_steps_exist(self):
        assert DepthStepName.KHAWATIR == "KHAWATIR"
        assert DepthStepName.MURAQABA == "MURAQABA"
        assert DepthStepName.MUJAHADA == "MUJAHADA"
        assert DepthStepName.MUHASABA == "MUHASABA"
        assert DepthStepName.SUITE_PLANNING == "SUITE_PLANNING"

    def test_step_count(self):
        assert len(DepthStepName) == 5


class TestDepthPlanStatus:
    def test_all_statuses(self):
        assert DepthPlanStatus.PENDING == "PENDING"
        assert DepthPlanStatus.RUNNING == "RUNNING"
        assert DepthPlanStatus.COMPLETED == "COMPLETED"
        assert DepthPlanStatus.PARTIAL == "PARTIAL"
        assert DepthPlanStatus.FAILED == "FAILED"


# ---------------------------------------------------------------------------
# CandidateDirection (Step 1 output)
# ---------------------------------------------------------------------------


class TestCandidateDirection:
    def test_valid_candidate(self):
        cd = CandidateDirection(
            label="High domestic content scenario",
            description="Maximize local sourcing across construction sectors",
            sector_codes=["SEC01", "SEC02"],
            rationale="Saudi Vision 2030 local content targets",
            source_type="insight",
            test_plan="Apply LOCAL_CONTENT shock to SEC01, SEC02 at 80% target",
            required_levers=["LOCAL_CONTENT", "FINAL_DEMAND_SHOCK"],
        )
        assert cd.label == "High domestic content scenario"
        assert cd.source_type == "insight"
        assert cd.direction_id is not None
        assert len(cd.required_levers) == 2

    def test_source_type_nafs(self):
        cd = CandidateDirection(
            label="Business as usual",
            description="Continue current trajectory",
            rationale="Comfortable option",
            source_type="nafs",
            test_plan="No shocks needed",
        )
        assert cd.source_type == "nafs"

    def test_source_type_waswas(self):
        cd = CandidateDirection(
            label="Distraction scenario",
            description="Not analytically useful",
            rationale="Noise",
            source_type="waswas",
            test_plan="N/A",
        )
        assert cd.source_type == "waswas"

    def test_invalid_source_type_rejected(self):
        with pytest.raises(Exception):
            CandidateDirection(
                label="Bad",
                description="X",
                rationale="Y",
                source_type="invalid",
                test_plan="Z",
            )

    def test_empty_label_rejected(self):
        with pytest.raises(Exception):
            CandidateDirection(
                label="",
                description="X",
                rationale="Y",
                source_type="insight",
                test_plan="Z",
            )

    def test_required_levers_default_empty(self):
        cd = CandidateDirection(
            label="Test",
            description="X",
            rationale="Y",
            source_type="insight",
            test_plan="Z",
        )
        assert cd.required_levers == []

    def test_no_novelty_score_field(self):
        """CandidateDirection must NOT have novelty_score — scoring is Step 4 only."""
        cd = CandidateDirection(
            label="Test",
            description="X",
            rationale="Y",
            source_type="insight",
            test_plan="Z",
        )
        assert not hasattr(cd, "novelty_score")

    def test_serialization_roundtrip(self):
        cd = CandidateDirection(
            label="Test",
            description="X",
            sector_codes=["A", "B"],
            rationale="Y",
            source_type="insight",
            test_plan="Apply shocks",
            required_levers=["FINAL_DEMAND_SHOCK"],
        )
        data = cd.model_dump()
        restored = CandidateDirection.model_validate(data)
        assert restored.label == cd.label
        assert restored.source_type == cd.source_type
        assert restored.required_levers == cd.required_levers


# ---------------------------------------------------------------------------
# KhawatirOutput (Step 1 typed output)
# ---------------------------------------------------------------------------


class TestKhawatirOutput:
    def test_empty_candidates(self):
        out = KhawatirOutput()
        assert out.candidates == []

    def test_with_candidates(self):
        cd = CandidateDirection(
            label="Test",
            description="X",
            rationale="Y",
            source_type="insight",
            test_plan="Z",
        )
        out = KhawatirOutput(candidates=[cd])
        assert len(out.candidates) == 1


# ---------------------------------------------------------------------------
# BiasEntry + BiasRegister (Step 2 output)
# ---------------------------------------------------------------------------


class TestBiasEntry:
    def test_valid_entry(self):
        be = BiasEntry(
            bias_type="anchoring",
            description="Over-reliance on initial estimates",
            severity=7.5,
        )
        assert be.bias_type == "anchoring"
        assert be.severity == 7.5

    def test_severity_bounds(self):
        with pytest.raises(Exception):
            BiasEntry(bias_type="x", description="y", severity=-1.0)
        with pytest.raises(Exception):
            BiasEntry(bias_type="x", description="y", severity=11.0)

    def test_affected_directions_default_empty(self):
        be = BiasEntry(bias_type="x", description="y", severity=5.0)
        assert be.affected_directions == []


class TestBiasRegister:
    def test_empty_register(self):
        br = BiasRegister(overall_bias_risk=0.0)
        assert br.entries == []
        assert br.overall_bias_risk == 0.0

    def test_with_entries(self):
        entry = BiasEntry(bias_type="optimism", description="x", severity=6.0)
        br = BiasRegister(entries=[entry], overall_bias_risk=6.0)
        assert len(br.entries) == 1

    def test_overall_risk_bounds(self):
        with pytest.raises(Exception):
            BiasRegister(overall_bias_risk=-0.1)
        with pytest.raises(Exception):
            BiasRegister(overall_bias_risk=10.1)


class TestMuraqabaOutput:
    def test_typed_output(self):
        br = BiasRegister(overall_bias_risk=3.0)
        out = MuraqabaOutput(bias_register=br)
        assert out.bias_register.overall_bias_risk == 3.0


# ---------------------------------------------------------------------------
# ContrarianDirection (Step 3 output)
# ---------------------------------------------------------------------------


class TestContrarianDirection:
    def test_valid_contrarian(self):
        cd = ContrarianDirection(
            label="Import shock stress test",
            description="What if import costs surge 40%?",
            uncomfortable_truth="Current import share assumptions are optimistic",
            sector_codes=["SEC01"],
            rationale="Historical precedent in 2015 oil shock",
            broken_assumption="Import share remains at 30% for construction",
            is_quantifiable=True,
            quantified_levers=[
                {
                    "type": "IMPORT_SUBSTITUTION",
                    "sector_code": "SEC01",
                    "delta_import_share": 0.4,
                }
            ],
        )
        assert cd.broken_assumption.startswith("Import share")
        assert cd.is_quantifiable is True
        assert len(cd.quantified_levers) == 1

    def test_non_quantifiable_contrarian(self):
        cd = ContrarianDirection(
            label="Regulatory upheaval",
            description="What if regulations change?",
            uncomfortable_truth="Policy environment is unstable",
            rationale="Political risk",
            broken_assumption="Stable regulatory environment",
            is_quantifiable=False,
        )
        assert cd.is_quantifiable is False
        assert cd.quantified_levers is None

    def test_no_novelty_score_field(self):
        """ContrarianDirection must NOT have novelty_score."""
        cd = ContrarianDirection(
            label="Test",
            description="X",
            uncomfortable_truth="Y",
            rationale="Z",
            broken_assumption="A",
        )
        assert not hasattr(cd, "novelty_score")


# ---------------------------------------------------------------------------
# QualitativeRisk — Agent-to-math boundary
# ---------------------------------------------------------------------------


class TestQualitativeRisk:
    def test_not_modeled_always_true(self):
        qr = QualitativeRisk(
            label="Political instability",
            description="Risk of policy reversal",
            affected_sectors=["SEC01"],
        )
        assert qr.not_modeled is True

    def test_setting_not_modeled_false_raises(self):
        """Agent-to-math boundary: not_modeled=False is rejected."""
        with pytest.raises(ValueError, match="not_modeled must always be True"):
            QualitativeRisk(
                label="Bad risk",
                description="Trying to model it",
                not_modeled=False,
            )

    def test_default_empty_sectors(self):
        qr = QualitativeRisk(label="X", description="Y")
        assert qr.affected_sectors == []

    def test_risk_id_generated(self):
        qr = QualitativeRisk(label="X", description="Y")
        assert qr.risk_id is not None


class TestMujahadaOutput:
    def test_typed_output(self):
        c = ContrarianDirection(
            label="Test",
            description="X",
            uncomfortable_truth="Y",
            rationale="Z",
            broken_assumption="A",
        )
        r = QualitativeRisk(label="R", description="D")
        out = MujahadaOutput(contrarians=[c], qualitative_risks=[r])
        assert len(out.contrarians) == 1
        assert len(out.qualitative_risks) == 1
        assert out.qualitative_risks[0].not_modeled is True


# ---------------------------------------------------------------------------
# ScoredCandidate (Step 4 output)
# ---------------------------------------------------------------------------


class TestScoredCandidate:
    def test_accepted_candidate(self):
        sc = ScoredCandidate(
            direction_id=uuid4(),
            label="High local content",
            composite_score=8.5,
            novelty_score=7.0,
            feasibility_score=9.0,
            data_availability_score=8.0,
            is_contrarian=False,
            rank=1,
            accepted=True,
        )
        assert sc.accepted is True
        assert sc.rejection_reason is None

    def test_rejected_candidate_with_reason(self):
        sc = ScoredCandidate(
            direction_id=uuid4(),
            label="Noise scenario",
            composite_score=2.0,
            novelty_score=1.0,
            feasibility_score=3.0,
            data_availability_score=2.0,
            is_contrarian=False,
            rank=5,
            accepted=False,
            rejection_reason="Below minimum feasibility threshold",
        )
        assert sc.accepted is False
        assert "threshold" in sc.rejection_reason

    def test_score_bounds(self):
        with pytest.raises(Exception):
            ScoredCandidate(
                direction_id=uuid4(),
                label="X",
                composite_score=11.0,
                novelty_score=5.0,
                feasibility_score=5.0,
                data_availability_score=5.0,
                rank=1,
            )

    def test_rank_must_be_positive(self):
        with pytest.raises(Exception):
            ScoredCandidate(
                direction_id=uuid4(),
                label="X",
                composite_score=5.0,
                novelty_score=5.0,
                feasibility_score=5.0,
                data_availability_score=5.0,
                rank=0,
            )

    def test_contrarian_flag(self):
        sc = ScoredCandidate(
            direction_id=uuid4(),
            label="Contrarian",
            composite_score=7.0,
            novelty_score=8.0,
            feasibility_score=6.0,
            data_availability_score=5.0,
            is_contrarian=True,
            rank=2,
        )
        assert sc.is_contrarian is True


class TestMuhasabaOutput:
    def test_typed_output(self):
        sc = ScoredCandidate(
            direction_id=uuid4(),
            label="X",
            composite_score=5.0,
            novelty_score=5.0,
            feasibility_score=5.0,
            data_availability_score=5.0,
            rank=1,
        )
        out = MuhasabaOutput(scored=[sc])
        assert len(out.scored) == 1


# ---------------------------------------------------------------------------
# SuiteRun + ScenarioSuitePlan (Step 5 output)
# ---------------------------------------------------------------------------


class TestSuiteRun:
    def test_valid_suite_run(self):
        sr = SuiteRun(
            name="Base + High Local Content",
            direction_id=uuid4(),
            executable_levers=[
                {
                    "type": "LOCAL_CONTENT_TARGET",
                    "sector": "SEC01",
                    "value": 0.8,
                },
                {
                    "type": "FINAL_DEMAND_SHOCK",
                    "sector": "SEC02",
                    "value": 50_000_000,
                },
            ],
            mode="SANDBOX",
            sensitivities=["import_share", "phasing"],
            disclosure_tier=DisclosureTier.TIER1,
        )
        assert sr.name == "Base + High Local Content"
        assert len(sr.executable_levers) == 2
        assert sr.mode == "SANDBOX"

    def test_default_values(self):
        sr = SuiteRun(
            name="Test",
            direction_id=uuid4(),
        )
        assert sr.executable_levers == []
        assert sr.mode == "SANDBOX"
        assert sr.sensitivities == []
        assert sr.disclosure_tier == DisclosureTier.TIER1


class TestScenarioSuitePlan:
    def test_valid_suite_plan(self):
        ws_id = uuid4()
        run = SuiteRun(name="Run 1", direction_id=uuid4())
        risk = QualitativeRisk(label="R1", description="D1")
        plan = ScenarioSuitePlan(
            workspace_id=ws_id,
            runs=[run],
            recommended_outputs=["multipliers", "jobs", "variance_bridge"],
            qualitative_risks=[risk],
            rationale="Selected top-scoring directions with contrarian stress test",
        )
        assert plan.workspace_id == ws_id
        assert len(plan.runs) == 1
        assert "multipliers" in plan.recommended_outputs
        assert plan.disclosure_tier == DisclosureTier.TIER1

    def test_no_ranked_or_selected_directions(self):
        """Suite plan uses runs, not ranked_directions/selected_directions."""
        plan = ScenarioSuitePlan(workspace_id=uuid4())
        assert not hasattr(plan, "ranked_directions")
        assert not hasattr(plan, "selected_directions")
        assert hasattr(plan, "runs")

    def test_default_disclosure_tier1(self):
        plan = ScenarioSuitePlan(workspace_id=uuid4())
        assert plan.disclosure_tier == DisclosureTier.TIER1


class TestSuitePlanningOutput:
    def test_typed_output(self):
        plan = ScenarioSuitePlan(workspace_id=uuid4())
        out = SuitePlanningOutput(suite_plan=plan)
        assert out.suite_plan.disclosure_tier == DisclosureTier.TIER1


# ---------------------------------------------------------------------------
# DepthArtifact
# ---------------------------------------------------------------------------


class TestDepthArtifact:
    def test_valid_artifact(self):
        a = DepthArtifact(
            plan_id=uuid4(),
            step=DepthStepName.KHAWATIR,
            payload={"candidates": []},
            disclosure_tier=DisclosureTier.TIER0,
            metadata={
                "provider": "anthropic",
                "model": "claude-sonnet-4-20250514",
                "generation_mode": "LLM",
            },
        )
        assert a.step == DepthStepName.KHAWATIR
        assert a.disclosure_tier == DisclosureTier.TIER0
        assert a.metadata["generation_mode"] == "LLM"

    def test_default_tier0(self):
        a = DepthArtifact(
            plan_id=uuid4(),
            step=DepthStepName.MUJAHADA,
            payload={},
        )
        assert a.disclosure_tier == DisclosureTier.TIER0

    def test_metadata_default_empty(self):
        a = DepthArtifact(
            plan_id=uuid4(),
            step=DepthStepName.KHAWATIR,
            payload={},
        )
        assert a.metadata == {}

    def test_artifact_id_generated(self):
        a = DepthArtifact(
            plan_id=uuid4(),
            step=DepthStepName.KHAWATIR,
            payload={},
        )
        assert a.artifact_id is not None

    def test_fallback_metadata(self):
        a = DepthArtifact(
            plan_id=uuid4(),
            step=DepthStepName.KHAWATIR,
            payload={},
            metadata={"generation_mode": "FALLBACK"},
        )
        assert a.metadata["generation_mode"] == "FALLBACK"


# ---------------------------------------------------------------------------
# DepthPlan
# ---------------------------------------------------------------------------


class TestDepthPlan:
    def test_valid_plan(self):
        dp = DepthPlan(workspace_id=uuid4())
        assert dp.status == DepthPlanStatus.PENDING
        assert dp.current_step is None
        assert dp.degraded_steps == []
        assert dp.step_errors == {}
        assert dp.error_message is None

    def test_plan_with_scenario_spec(self):
        dp = DepthPlan(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
        )
        assert dp.scenario_spec_id is not None

    def test_degraded_steps_tracking(self):
        dp = DepthPlan(
            workspace_id=uuid4(),
            status=DepthPlanStatus.COMPLETED,
            degraded_steps=["KHAWATIR", "MURAQABA"],
            step_errors={"KHAWATIR": "LLM timeout, used fallback"},
        )
        assert len(dp.degraded_steps) == 2
        assert "KHAWATIR" in dp.step_errors

    def test_plan_id_generated(self):
        dp = DepthPlan(workspace_id=uuid4())
        assert dp.plan_id is not None

    def test_timestamps_set(self):
        dp = DepthPlan(workspace_id=uuid4())
        assert dp.created_at is not None
        assert dp.updated_at is not None


# ---------------------------------------------------------------------------
# Serialization roundtrips
# ---------------------------------------------------------------------------


class TestSerializationRoundtrips:
    def test_depth_plan_roundtrip(self):
        dp = DepthPlan(
            workspace_id=uuid4(),
            status=DepthPlanStatus.RUNNING,
            current_step=DepthStepName.MUJAHADA,
            degraded_steps=["KHAWATIR"],
        )
        data = dp.model_dump()
        restored = DepthPlan.model_validate(data)
        assert restored.status == DepthPlanStatus.RUNNING
        assert restored.current_step == DepthStepName.MUJAHADA

    def test_suite_plan_roundtrip(self):
        ws_id = uuid4()
        dir_id = uuid4()
        run = SuiteRun(
            name="Run A",
            direction_id=dir_id,
            executable_levers=[
                {"type": "FINAL_DEMAND_SHOCK", "sector": "S1", "value": 100},
            ],
        )
        risk = QualitativeRisk(label="R", description="D")
        plan = ScenarioSuitePlan(
            workspace_id=ws_id,
            runs=[run],
            qualitative_risks=[risk],
            recommended_outputs=["jobs"],
            rationale="Top picks",
        )
        data = plan.model_dump()
        restored = ScenarioSuitePlan.model_validate(data)
        assert restored.workspace_id == ws_id
        assert len(restored.runs) == 1
        assert restored.runs[0].direction_id == dir_id
        assert restored.qualitative_risks[0].not_modeled is True

    def test_contrarian_roundtrip(self):
        cd = ContrarianDirection(
            label="Import stress",
            description="Surge scenario",
            uncomfortable_truth="Imports may spike",
            rationale="Historical data",
            broken_assumption="Stable import share",
            is_quantifiable=True,
            quantified_levers=[{"type": "IMPORT_SUBSTITUTION", "delta": 0.3}],
        )
        data = cd.model_dump()
        restored = ContrarianDirection.model_validate(data)
        assert restored.is_quantifiable is True
        assert restored.broken_assumption == "Stable import share"
