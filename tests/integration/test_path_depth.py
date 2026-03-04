# tests/integration/test_path_depth.py
"""Integration Path: Depth Engine (DepthOrchestrator) with mocked LLM.

Tests verify:
1. Every artifact has a valid disclosure tier
2. Pipeline produces expected 5-step sequence
3. Suite plan contains executable scenario stubs
4. Depth outputs do not mutate engine numbers (agent-to-math boundary)
5. Mocked LLM returns step-specific typed outputs

Uses DepthOrchestrator directly with mocked repositories and LLM client.
No real LLM calls, no database -- all dependencies are mocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.agents.depth.orchestrator import _STEP_DISCLOSURE, DepthOrchestrator
from src.agents.llm_client import LLMClient, LLMProvider, TokenUsage
from src.models.common import DataClassification, DisclosureTier
from src.models.depth import (
    DepthPlanStatus,
    DepthStepName,
    KhawatirOutput,
    MuhasabaOutput,
    MujahadaOutput,
    MuraqabaOutput,
    SuitePlanningOutput,
)

ALLOWED_LEVERS = {
    "FINAL_DEMAND_SHOCK",
    "IMPORT_SHARE_ADJUSTMENT",
    "LOCAL_CONTENT_TARGET",
    "PHASING_SHIFT",
    "CONSTRAINT_SET_TOGGLE",
    "SENSITIVITY_SWEEP",
}


def _make_mock_llm_client() -> MagicMock:
    """Create a mock LLM client that reports availability but never calls real APIs."""
    client = MagicMock(spec=LLMClient)
    client.is_available_for.return_value = False
    client.cumulative_usage.return_value = TokenUsage(input_tokens=0, output_tokens=0)
    router = MagicMock()
    router.select_provider.return_value = LLMProvider.LOCAL
    client._router = router
    return client


def _make_mock_plan_repo() -> AsyncMock:
    """Create a mock DepthPlanRepository that records calls."""

    @dataclass
    class FakePlanRow:
        plan_id: UUID
        status: str = "PENDING"
        current_step: str | None = None
        degraded_steps: list[str] | None = None
        step_errors: dict | None = None
        step_metadata: list[dict] | None = None
        error_message: str | None = None

    repo = AsyncMock()
    _state: dict[UUID, FakePlanRow] = {}

    async def mock_update_status(plan_id, status, **kwargs):
        row = _state.get(plan_id)
        if row is None:
            row = FakePlanRow(plan_id=plan_id)
            _state[plan_id] = row
        row.status = status
        row.current_step = kwargs.get("current_step")
        if kwargs.get("degraded_steps") is not None:
            row.degraded_steps = kwargs["degraded_steps"]
        if kwargs.get("step_errors") is not None:
            row.step_errors = kwargs["step_errors"]
        if kwargs.get("step_metadata") is not None:
            row.step_metadata = kwargs["step_metadata"]
        if kwargs.get("error_message") is not None:
            row.error_message = kwargs["error_message"]
        return row

    repo.update_status = AsyncMock(side_effect=mock_update_status)
    repo._state = _state
    return repo


def _make_mock_artifact_repo() -> AsyncMock:
    """Create a mock DepthArtifactRepository that stores artifacts in memory."""

    @dataclass
    class FakeArtifactRow:
        artifact_id: UUID
        plan_id: UUID
        step: str
        payload: dict
        disclosure_tier: str
        metadata_json: dict

    repo = AsyncMock()
    _artifacts: list[FakeArtifactRow] = []

    async def mock_create(
        *, artifact_id, plan_id, step, payload, disclosure_tier="TIER0", metadata_json=None,
    ):
        row = FakeArtifactRow(
            artifact_id=artifact_id,
            plan_id=plan_id,
            step=step,
            payload=payload,
            disclosure_tier=disclosure_tier,
            metadata_json=metadata_json or {},
        )
        _artifacts.append(row)
        return row

    async def mock_get_by_plan(plan_id):
        return [a for a in _artifacts if a.plan_id == plan_id]

    async def mock_get_by_plan_and_step(plan_id, step):
        for a in _artifacts:
            if a.plan_id == plan_id and a.step == step:
                return a
        return None

    repo.create = AsyncMock(side_effect=mock_create)
    repo.get_by_plan = AsyncMock(side_effect=mock_get_by_plan)
    repo.get_by_plan_and_step = AsyncMock(side_effect=mock_get_by_plan_and_step)
    repo._artifacts = _artifacts
    return repo


@pytest.mark.integration
class TestPathDepth:
    """Depth Engine integration: orchestrator with mocked LLM + repos."""

    @pytest.fixture
    def workspace_id(self) -> UUID:
        return uuid7()

    @pytest.fixture
    def plan_id(self) -> UUID:
        return uuid7()

    @pytest.fixture
    def plan_repo(self) -> AsyncMock:
        return _make_mock_plan_repo()

    @pytest.fixture
    def artifact_repo(self) -> AsyncMock:
        return _make_mock_artifact_repo()

    @pytest.fixture
    def llm_client(self) -> MagicMock:
        return _make_mock_llm_client()

    @pytest.fixture
    def orchestrator(self) -> DepthOrchestrator:
        return DepthOrchestrator()

    async def _run_full_pipeline(
        self,
        orchestrator: DepthOrchestrator,
        plan_id: UUID,
        workspace_id: UUID,
        llm_client: MagicMock,
        plan_repo: AsyncMock,
        artifact_repo: AsyncMock,
    ) -> DepthPlanStatus:
        """Helper: run the full pipeline and return final status."""
        return await orchestrator.run(
            plan_id=plan_id,
            workspace_id=workspace_id,
            context={"sector_codes": ["F", "C"]},
            classification=DataClassification.RESTRICTED,
            llm_client=llm_client,
            plan_repo=plan_repo,
            artifact_repo=artifact_repo,
        )

    @pytest.mark.asyncio
    async def test_each_artifact_has_disclosure_tier(
        self, orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
    ) -> None:
        """Every persisted artifact has a valid DisclosureTier from the spec.

        Steps 1-4 (KHAWATIR, MURAQABA, MUJAHADA, MUHASABA) = TIER0.
        Step 5 (SUITE_PLANNING) = TIER1.
        """
        status = await self._run_full_pipeline(
            orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED
        artifacts = artifact_repo._artifacts
        assert len(artifacts) == 5, f"Expected 5 artifacts, got {len(artifacts)}"
        valid_tiers = {tier.value for tier in DisclosureTier}
        for artifact in artifacts:
            assert artifact.disclosure_tier in valid_tiers, (
                f"Artifact step={artifact.step} has invalid tier={artifact.disclosure_tier!r}"
            )
        step_to_tier = {a.step: a.disclosure_tier for a in artifacts}
        for step_name, expected_tier in _STEP_DISCLOSURE.items():
            assert step_to_tier[step_name.value] == expected_tier.value, (
                f"Step {step_name.value}: expected {expected_tier.value}, got {step_to_tier[step_name.value]}"
            )

    @pytest.mark.asyncio
    async def test_pipeline_produces_expected_step_sequence(
        self, orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
    ) -> None:
        """Artifacts are produced in the canonical 5-step order:
        KHAWATIR -> MURAQABA -> MUJAHADA -> MUHASABA -> SUITE_PLANNING.
        """
        status = await self._run_full_pipeline(
            orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED
        artifacts = artifact_repo._artifacts
        actual_steps = [a.step for a in artifacts]
        expected_steps = [
            DepthStepName.KHAWATIR.value,
            DepthStepName.MURAQABA.value,
            DepthStepName.MUJAHADA.value,
            DepthStepName.MUHASABA.value,
            DepthStepName.SUITE_PLANNING.value,
        ]
        assert actual_steps == expected_steps, (
            f"Step order mismatch: expected {expected_steps}, got {actual_steps}"
        )
        update_calls = plan_repo.update_status.call_args_list
        assert len(update_calls) >= 6, (
            f"Expected >= 6 update_status calls, got {len(update_calls)}"
        )

    @pytest.mark.asyncio
    async def test_suite_plan_contains_executable_scenarios(
        self, orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
    ) -> None:
        """Suite plan has runs with valid names, direction_ids, modes, and levers."""
        status = await self._run_full_pipeline(
            orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED
        suite_artifact = None
        for a in artifact_repo._artifacts:
            if a.step == DepthStepName.SUITE_PLANNING.value:
                suite_artifact = a
                break
        assert suite_artifact is not None, "SUITE_PLANNING artifact not found"
        payload = suite_artifact.payload
        assert "suite_plan" in payload, "Suite artifact missing suite_plan key"
        suite_plan = payload["suite_plan"]
        runs = suite_plan.get("runs", [])
        assert len(runs) >= 1, "Suite plan has no runs"
        for run in runs:
            assert "name" in run, "Run missing name"
            assert "direction_id" in run, "Run missing direction_id"
            assert "mode" in run, "Run missing mode"
            assert run["mode"] in ("SANDBOX", "GOVERNED")
            for lever in run.get("executable_levers", []):
                if isinstance(lever, dict) and "type" in lever:
                    assert lever["type"] in ALLOWED_LEVERS
        recommended = suite_plan.get("recommended_outputs", [])
        assert len(recommended) >= 1, "Suite plan has no recommended_outputs"

    @pytest.mark.asyncio
    async def test_depth_outputs_do_not_mutate_engine(
        self, orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
    ) -> None:
        """Depth engine produces structured JSON only -- never engine results."""
        status = await self._run_full_pipeline(
            orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED
        forbidden_result_keys = {
            "output_vector", "multiplier_matrix", "gdp_impact",
            "total_output", "leontief_inverse", "result_sets",
            "employment_impact_total", "import_leakage_total",
        }
        for artifact in artifact_repo._artifacts:
            payload = artifact.payload
            for key in forbidden_result_keys:
                assert key not in payload, (
                    f"Artifact step={artifact.step} has forbidden key {key}"
                )
        mujahada_artifact = None
        for a in artifact_repo._artifacts:
            if a.step == DepthStepName.MUJAHADA.value:
                mujahada_artifact = a
                break
        assert mujahada_artifact is not None
        for risk in mujahada_artifact.payload.get("qualitative_risks", []):
            assert risk.get("not_modeled") is True, (
                "QualitativeRisk must have not_modeled=True"
            )
        suite_artifact = None
        for a in artifact_repo._artifacts:
            if a.step == DepthStepName.SUITE_PLANNING.value:
                suite_artifact = a
                break
        assert suite_artifact is not None
        for run in suite_artifact.payload.get("suite_plan", {}).get("runs", []):
            mode = run["mode"]
            assert mode == "SANDBOX", (
                f"Suite run has mode={mode!r}, expected SANDBOX"
            )

    @pytest.mark.asyncio
    async def test_mock_llm_returns_typed_outputs(
        self, orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
    ) -> None:
        """Each step artifact validates against its typed Pydantic output model."""
        status = await self._run_full_pipeline(
            orchestrator, plan_id, workspace_id, llm_client, plan_repo, artifact_repo,
        )
        assert status == DepthPlanStatus.COMPLETED
        step_to_model = {
            DepthStepName.KHAWATIR.value: KhawatirOutput,
            DepthStepName.MURAQABA.value: MuraqabaOutput,
            DepthStepName.MUJAHADA.value: MujahadaOutput,
            DepthStepName.MUHASABA.value: MuhasabaOutput,
            DepthStepName.SUITE_PLANNING.value: SuitePlanningOutput,
        }
        for artifact in artifact_repo._artifacts:
            model_cls = step_to_model.get(artifact.step)
            assert model_cls is not None
            try:
                validated = model_cls.model_validate(artifact.payload)
            except Exception as exc:
                pytest.fail(
                    f"Step {artifact.step} failed validation against "
                    f"{model_cls.__name__}: {exc}"
                )
            dumped = validated.model_dump(mode="json")
            assert isinstance(dumped, dict)
        assert llm_client.is_available_for.called
        for artifact in artifact_repo._artifacts:
            meta = artifact.metadata_json
            assert "generation_mode" in meta
            assert meta["generation_mode"] in ("LLM", "FALLBACK")
            assert "context_hash" in meta
            assert "classification" in meta
