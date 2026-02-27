"""Tests for feasibility repositories — MVP-10.

Uses SAVEPOINT-isolated db_session from conftest.py.
"""

from uuid import uuid4

import pytest

from src.models.common import new_uuid7
from src.repositories.feasibility import (
    ConstraintSetRepository,
    FeasibilityResultRepository,
)

# ---------------------------------------------------------------------------
# ConstraintSetRepository
# ---------------------------------------------------------------------------


class TestConstraintSetRepository:
    @pytest.fixture
    def repo(self, db_session):
        return ConstraintSetRepository(db_session)

    async def test_create_and_get(self, repo):
        cs_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        row = await repo.create(
            constraint_set_id=cs_id,
            version=1,
            workspace_id=ws_id,
            model_version_id=mv_id,
            name="Base constraints",
            constraints=[
                {
                    "constraint_type": "CAPACITY_CAP",
                    "applies_to": "SEC01",
                    "value": 100.0,
                    "unit": "SAR",
                    "confidence": "HARD",
                },
            ],
        )
        assert row.constraint_set_id == cs_id
        assert row.version == 1
        assert row.name == "Base constraints"
        assert len(row.constraints) == 1

        fetched = await repo.get(cs_id, 1)
        assert fetched is not None
        assert fetched.constraint_set_id == cs_id

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4(), 1)
        assert result is None

    async def test_get_latest(self, repo):
        cs_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            constraint_set_id=cs_id, version=1,
            workspace_id=ws_id, model_version_id=mv_id,
            name="V1", constraints=[],
        )
        await repo.create(
            constraint_set_id=cs_id, version=2,
            workspace_id=ws_id, model_version_id=mv_id,
            name="V2", constraints=[{"type": "updated"}],
        )
        latest = await repo.get_latest(cs_id)
        assert latest is not None
        assert latest.version == 2
        assert latest.name == "V2"

    async def test_get_latest_nonexistent_returns_none(self, repo):
        result = await repo.get_latest(uuid4())
        assert result is None

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        mv_id = uuid4()
        cs1 = new_uuid7()
        cs2 = new_uuid7()
        await repo.create(
            constraint_set_id=cs1, version=1,
            workspace_id=ws_id, model_version_id=mv_id,
            name="Set A", constraints=[],
        )
        await repo.create(
            constraint_set_id=cs2, version=1,
            workspace_id=ws_id, model_version_id=mv_id,
            name="Set B", constraints=[],
        )
        # Different workspace
        await repo.create(
            constraint_set_id=new_uuid7(), version=1,
            workspace_id=uuid4(), model_version_id=mv_id,
            name="Other WS", constraints=[],
        )

        sets = await repo.get_by_workspace(ws_id)
        assert len(sets) == 2
        names = {s.name for s in sets}
        assert "Set A" in names
        assert "Set B" in names

    async def test_version_uniqueness(self, repo):
        """Duplicate (constraint_set_id, version) should raise."""
        cs_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            constraint_set_id=cs_id, version=1,
            workspace_id=ws_id, model_version_id=mv_id,
            name="V1", constraints=[],
        )
        with pytest.raises(Exception):
            await repo.create(
                constraint_set_id=cs_id, version=1,
                workspace_id=ws_id, model_version_id=mv_id,
                name="V1 duplicate", constraints=[],
            )

    async def test_created_by_optional(self, repo):
        row = await repo.create(
            constraint_set_id=new_uuid7(), version=1,
            workspace_id=uuid4(), model_version_id=uuid4(),
            name="No creator", constraints=[],
        )
        assert row.created_by is None

    async def test_created_by_set(self, repo):
        actor = uuid4()
        row = await repo.create(
            constraint_set_id=new_uuid7(), version=1,
            workspace_id=uuid4(), model_version_id=uuid4(),
            name="With creator", constraints=[],
            created_by=actor,
        )
        assert row.created_by == actor


# ---------------------------------------------------------------------------
# FeasibilityResultRepository
# ---------------------------------------------------------------------------


class TestFeasibilityResultRepository:
    @pytest.fixture
    def repo(self, db_session):
        return FeasibilityResultRepository(db_session)

    def _make_result_kwargs(self, **overrides):
        defaults = {
            "feasibility_result_id": new_uuid7(),
            "workspace_id": uuid4(),
            "unconstrained_run_id": uuid4(),
            "constraint_set_id": uuid4(),
            "constraint_set_version": 1,
            "feasible_delta_x": {"SEC01": 50.0, "SEC02": 80.0},
            "unconstrained_delta_x": {"SEC01": 100.0, "SEC02": 80.0},
            "gap_vs_unconstrained": {"SEC01": 50.0, "SEC02": 0.0},
            "total_feasible_output": 130.0,
            "total_unconstrained_output": 180.0,
            "total_gap": 50.0,
            "binding_constraints": [
                {"constraint_id": str(uuid4()), "constraint_type": "CAPACITY_CAP",
                 "sector_code": "SEC01", "shadow_price": 50.0, "gap_to_feasible": 50.0},
            ],
            "slack_constraint_ids": [],
            "enabler_recommendations": [],
            "confidence_summary": {"hard_pct": 1.0, "estimated_pct": 0.0,
                                   "assumed_pct": 0.0, "total_constraints": 1},
            "satellite_coefficients_hash": "abc123def456",
            "satellite_coefficients_snapshot": {"jobs_coeff": [0.1, 0.15],
                                                 "import_ratio": [0.3, 0.2]},
            "solver_type": "ClippingSolver",
            "solver_version": "1.0.0",
        }
        defaults.update(overrides)
        return defaults

    async def test_create_and_get(self, repo):
        kwargs = self._make_result_kwargs()
        row = await repo.create(**kwargs)
        assert row.feasibility_result_id == kwargs["feasibility_result_id"]
        assert row.total_gap == 50.0
        assert row.solver_type == "ClippingSolver"

        fetched = await repo.get(kwargs["feasibility_result_id"])
        assert fetched is not None
        assert fetched.feasibility_result_id == kwargs["feasibility_result_id"]

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4())
        assert result is None

    async def test_get_by_run(self, repo):
        run_id = uuid4()
        ws_id = uuid4()
        await repo.create(**self._make_result_kwargs(
            unconstrained_run_id=run_id, workspace_id=ws_id,
        ))
        await repo.create(**self._make_result_kwargs(
            unconstrained_run_id=run_id, workspace_id=ws_id,
        ))
        # Different run
        await repo.create(**self._make_result_kwargs())

        results = await repo.get_by_run(run_id)
        assert len(results) == 2

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        await repo.create(**self._make_result_kwargs(workspace_id=ws_id))
        await repo.create(**self._make_result_kwargs(workspace_id=ws_id))
        # Different workspace
        await repo.create(**self._make_result_kwargs())

        results = await repo.get_by_workspace(ws_id)
        assert len(results) == 2

    async def test_get_comparison(self, repo):
        run_id = uuid4()
        cs_id = uuid4()
        ws_id = uuid4()
        await repo.create(**self._make_result_kwargs(
            unconstrained_run_id=run_id,
            constraint_set_id=cs_id,
            workspace_id=ws_id,
        ))
        result = await repo.get_comparison(run_id, cs_id)
        assert result is not None
        assert result.unconstrained_run_id == run_id
        assert result.constraint_set_id == cs_id

    async def test_get_comparison_not_found(self, repo):
        result = await repo.get_comparison(uuid4(), uuid4())
        assert result is None

    async def test_flexjson_roundtrip(self, repo):
        kwargs = self._make_result_kwargs()
        await repo.create(**kwargs)
        fetched = await repo.get(kwargs["feasibility_result_id"])
        assert fetched.feasible_delta_x == {"SEC01": 50.0, "SEC02": 80.0}
        assert fetched.binding_constraints[0]["constraint_type"] == "CAPACITY_CAP"
        assert fetched.confidence_summary["hard_pct"] == 1.0
        assert fetched.satellite_coefficients_snapshot["jobs_coeff"] == [0.1, 0.15]

    async def test_solver_metadata_stored(self, repo):
        kwargs = self._make_result_kwargs(
            solver_type="LPFeasibilitySolver",
            solver_version="1.0.0",
            lp_status="optimal",
            fallback_used=True,
        )
        await repo.create(**kwargs)
        fetched = await repo.get(kwargs["feasibility_result_id"])
        assert fetched.solver_type == "LPFeasibilitySolver"
        assert fetched.lp_status == "optimal"
        assert fetched.fallback_used is True
