"""Tests for Depth Engine Orchestrator.

Tests the full 5-step pipeline including:
- Complete pipeline execution
- Partial failure handling
- Degraded step tracking
- Artifact persistence
- Status semantics (COMPLETED vs PARTIAL)
"""

import pytest
from uuid import uuid4

from src.agents.depth.orchestrator import DepthOrchestrator
from src.models.common import DataClassification, new_uuid7
from src.models.depth import DepthPlanStatus, DepthStepName
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository


class TestDepthOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        return DepthOrchestrator()

    @pytest.fixture
    def plan_repo(self, db_session):
        return DepthPlanRepository(db_session)

    @pytest.fixture
    def artifact_repo(self, db_session):
        return DepthArtifactRepository(db_session)

    @pytest.fixture
    async def plan_id(self, plan_repo, workspace_id):
        pid = new_uuid7()
        await plan_repo.create(plan_id=pid, workspace_id=workspace_id)
        return pid

    @pytest.fixture
    def context(self):
        return {
            "workspace_description": "Saudi mega-project",
            "sector_codes": ["SEC01", "SEC02", "SEC03"],
            "existing_shocks": [],
            "time_horizon": {"start_year": 2025, "end_year": 2035},
        }

    async def test_full_pipeline_completes(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """Full pipeline with no LLM (deterministic fallback) should complete."""
        status = await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            llm_client=None,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED

    async def test_creates_5_artifacts(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        artifacts = await artifact_repo.get_by_plan(plan_id)
        assert len(artifacts) == 5

        steps = {a.step for a in artifacts}
        assert steps == {
            "KHAWATIR", "MURAQABA", "MUJAHADA", "MUHASABA", "SUITE_PLANNING",
        }

    async def test_artifacts_have_payload(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        artifacts = await artifact_repo.get_by_plan(plan_id)
        for a in artifacts:
            assert a.payload is not None
            assert isinstance(a.payload, dict)

    async def test_artifacts_have_metadata(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        artifacts = await artifact_repo.get_by_plan(plan_id)
        for a in artifacts:
            meta = a.metadata_json
            assert meta is not None
            assert meta["generation_mode"] == "FALLBACK"
            assert "context_hash" in meta
            assert meta["classification"] == "RESTRICTED"

    async def test_plan_status_updated(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        plan = await plan_repo.get(plan_id)
        assert plan.status == "COMPLETED"
        assert plan.current_step is None  # Pipeline finished

    async def test_degraded_steps_tracked(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """All steps should be degraded when no LLM is available."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            llm_client=None,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        plan = await plan_repo.get(plan_id)
        # All 5 steps used fallback
        assert len(plan.degraded_steps) == 5

    async def test_khawatir_output_feeds_muraqaba(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """Step 1 output should be available in Step 2."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        # Step 1 should have candidates
        khawatir = await artifact_repo.get_by_plan_and_step(plan_id, "KHAWATIR")
        assert "candidates" in khawatir.payload
        assert len(khawatir.payload["candidates"]) >= 3

        # Step 2 should have analyzed the candidates
        muraqaba = await artifact_repo.get_by_plan_and_step(plan_id, "MURAQABA")
        assert "bias_register" in muraqaba.payload

    async def test_suite_plan_has_runs(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """Final step should produce a suite plan with executable runs."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        suite = await artifact_repo.get_by_plan_and_step(plan_id, "SUITE_PLANNING")
        assert "suite_plan" in suite.payload
        plan_data = suite.payload["suite_plan"]
        assert "runs" in plan_data
        assert len(plan_data["runs"]) > 0
        assert "recommended_outputs" in plan_data
        assert "qualitative_risks" in plan_data

    async def test_mujahada_disclosure_tier0(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """Contrarian step artifacts should be TIER0 (internal only)."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        mujahada = await artifact_repo.get_by_plan_and_step(plan_id, "MUJAHADA")
        assert mujahada.disclosure_tier == "TIER0"

    async def test_suite_planning_disclosure_tier1(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """Suite planning artifact should be TIER1."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        suite = await artifact_repo.get_by_plan_and_step(plan_id, "SUITE_PLANNING")
        assert suite.disclosure_tier == "TIER1"

    async def test_qualitative_risks_always_not_modeled(
        self, orchestrator, plan_id, workspace_id, context,
        plan_repo, artifact_repo,
    ):
        """All qualitative risks in the pipeline should have not_modeled=True."""
        await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context=context,
            classification=DataClassification.RESTRICTED,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

        # Check Mujahada output
        mujahada = await artifact_repo.get_by_plan_and_step(plan_id, "MUJAHADA")
        for risk in mujahada.payload.get("qualitative_risks", []):
            assert risk["not_modeled"] is True

        # Check Suite Plan output
        suite = await artifact_repo.get_by_plan_and_step(plan_id, "SUITE_PLANNING")
        for risk in suite.payload["suite_plan"].get("qualitative_risks", []):
            assert risk["not_modeled"] is True

    async def test_steps_constant(self, orchestrator):
        assert len(orchestrator.STEPS) == 5
        assert orchestrator.STEPS[0] == DepthStepName.KHAWATIR
        assert orchestrator.STEPS[4] == DepthStepName.SUITE_PLANNING
