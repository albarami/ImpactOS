"""Tests for depth engine repositories — src/repositories/depth.py.

Uses SAVEPOINT-isolated db_session from conftest.py.
"""

import pytest
from uuid import uuid4

from src.models.common import new_uuid7
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository


# ---------------------------------------------------------------------------
# DepthPlanRepository
# ---------------------------------------------------------------------------


class TestDepthPlanRepository:
    @pytest.fixture
    def repo(self, db_session):
        return DepthPlanRepository(db_session)

    async def test_create_and_get(self, repo, workspace_id, plan_id):
        row = await repo.create(
            plan_id=plan_id,
            workspace_id=workspace_id,
        )
        assert row.plan_id == plan_id
        assert row.workspace_id == workspace_id
        assert row.status == "PENDING"
        assert row.current_step is None
        assert row.degraded_steps == []
        assert row.step_errors == {}

        fetched = await repo.get(plan_id)
        assert fetched is not None
        assert fetched.plan_id == plan_id

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4())
        assert result is None

    async def test_get_by_workspace(self, repo, workspace_id):
        p1 = new_uuid7()
        p2 = new_uuid7()
        await repo.create(plan_id=p1, workspace_id=workspace_id)
        await repo.create(plan_id=p2, workspace_id=workspace_id)

        # Different workspace
        other_ws = uuid4()
        await repo.create(plan_id=new_uuid7(), workspace_id=other_ws)

        plans = await repo.get_by_workspace(workspace_id)
        assert len(plans) == 2
        plan_ids = {p.plan_id for p in plans}
        assert p1 in plan_ids
        assert p2 in plan_ids

    async def test_update_status(self, repo, workspace_id, plan_id):
        await repo.create(plan_id=plan_id, workspace_id=workspace_id)

        updated = await repo.update_status(
            plan_id,
            "RUNNING",
            current_step="KHAWATIR",
        )
        assert updated.status == "RUNNING"
        assert updated.current_step == "KHAWATIR"

    async def test_update_status_with_degraded_steps(self, repo, workspace_id, plan_id):
        await repo.create(plan_id=plan_id, workspace_id=workspace_id)

        updated = await repo.update_status(
            plan_id,
            "COMPLETED",
            degraded_steps=["KHAWATIR", "MURAQABA"],
            step_errors={"KHAWATIR": "LLM timeout"},
        )
        assert updated.status == "COMPLETED"
        assert updated.degraded_steps == ["KHAWATIR", "MURAQABA"]
        assert updated.step_errors["KHAWATIR"] == "LLM timeout"

    async def test_update_status_with_error(self, repo, workspace_id, plan_id):
        await repo.create(plan_id=plan_id, workspace_id=workspace_id)

        updated = await repo.update_status(
            plan_id,
            "FAILED",
            error_message="Pipeline crashed",
        )
        assert updated.status == "FAILED"
        assert updated.error_message == "Pipeline crashed"

    async def test_update_nonexistent_returns_none(self, repo):
        result = await repo.update_status(uuid4(), "RUNNING")
        assert result is None

    async def test_list_all(self, repo, workspace_id):
        await repo.create(plan_id=new_uuid7(), workspace_id=workspace_id)
        await repo.create(plan_id=new_uuid7(), workspace_id=workspace_id)

        all_plans = await repo.list_all()
        assert len(all_plans) == 2

    async def test_create_with_scenario_spec(self, repo, workspace_id, plan_id):
        spec_id = uuid4()
        row = await repo.create(
            plan_id=plan_id,
            workspace_id=workspace_id,
            scenario_spec_id=spec_id,
        )
        assert row.scenario_spec_id == spec_id


# ---------------------------------------------------------------------------
# DepthArtifactRepository
# ---------------------------------------------------------------------------


class TestDepthArtifactRepository:
    @pytest.fixture
    def plan_repo(self, db_session):
        return DepthPlanRepository(db_session)

    @pytest.fixture
    def repo(self, db_session):
        return DepthArtifactRepository(db_session)

    @pytest.fixture
    async def persisted_plan_id(self, plan_repo, workspace_id):
        pid = new_uuid7()
        await plan_repo.create(plan_id=pid, workspace_id=workspace_id)
        return pid

    async def test_create_and_get(self, repo, persisted_plan_id):
        aid = new_uuid7()
        row = await repo.create(
            artifact_id=aid,
            plan_id=persisted_plan_id,
            step="KHAWATIR",
            payload={"candidates": [{"label": "Test"}]},
            disclosure_tier="TIER0",
            metadata_json={"generation_mode": "FALLBACK"},
        )
        assert row.artifact_id == aid
        assert row.step == "KHAWATIR"
        assert row.payload["candidates"][0]["label"] == "Test"
        assert row.metadata_json["generation_mode"] == "FALLBACK"

        fetched = await repo.get(aid)
        assert fetched is not None
        assert fetched.artifact_id == aid

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4())
        assert result is None

    async def test_get_by_plan(self, repo, persisted_plan_id):
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="KHAWATIR",
            payload={"candidates": []},
        )
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="MURAQABA",
            payload={"bias_register": {}},
        )

        artifacts = await repo.get_by_plan(persisted_plan_id)
        assert len(artifacts) == 2
        steps = {a.step for a in artifacts}
        assert "KHAWATIR" in steps
        assert "MURAQABA" in steps

    async def test_get_by_plan_and_step(self, repo, persisted_plan_id):
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="KHAWATIR",
            payload={"candidates": []},
        )
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="MURAQABA",
            payload={"bias_register": {}},
        )

        art = await repo.get_by_plan_and_step(persisted_plan_id, "KHAWATIR")
        assert art is not None
        assert art.step == "KHAWATIR"

        missing = await repo.get_by_plan_and_step(persisted_plan_id, "MUJAHADA")
        assert missing is None

    async def test_unique_constraint_plan_step(self, repo, persisted_plan_id):
        """Only one artifact per (plan_id, step) is allowed."""
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="KHAWATIR",
            payload={"candidates": []},
        )
        with pytest.raises(Exception):
            await repo.create(
                artifact_id=new_uuid7(),
                plan_id=persisted_plan_id,
                step="KHAWATIR",
                payload={"candidates": ["duplicate"]},
            )

    async def test_default_disclosure_tier(self, repo, persisted_plan_id):
        row = await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="MUJAHADA",
            payload={},
        )
        assert row.disclosure_tier == "TIER0"

    async def test_metadata_default_empty(self, repo, persisted_plan_id):
        row = await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="MUHASABA",
            payload={},
        )
        assert row.metadata_json == {}

    async def test_list_all(self, repo, persisted_plan_id):
        await repo.create(
            artifact_id=new_uuid7(),
            plan_id=persisted_plan_id,
            step="KHAWATIR",
            payload={},
        )
        all_artifacts = await repo.list_all()
        assert len(all_artifacts) == 1
