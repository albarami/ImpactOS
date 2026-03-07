"""Test P6-4 fix: depth_engine data flows through RunResponse API.

Proves the backend GET /v1/workspaces/{ws}/engine/runs/{run_id} returns
depth_engine data when a linked DepthPlan exists for the run's scenario.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import DepthArtifactRow, DepthPlanRow
from src.models.common import new_uuid7, utc_now


class TestDepthEngineOnRunResponse:
    """P6-4: depth_engine field populated on run response when depth plan exists."""

    @pytest.mark.anyio
    async def test_run_response_has_depth_engine_when_plan_exists(
        self,
        client: AsyncClient,
        seeded_run: dict,
        db_session: AsyncSession,
    ) -> None:
        """GET runs/{run_id} returns depth_engine when a linked DepthPlan exists."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        # Get the run to find scenario_spec_id
        resp = await client.get(f"/v1/workspaces/{ws_id}/engine/runs/{run_id}")
        assert resp.status_code == 200
        # At this point, depth_engine should be None (no plan exists)
        data = resp.json()
        assert data.get("depth_engine") is None

        # Find the scenario_spec_id from the run snapshot
        from src.db.tables import RunSnapshotRow
        from sqlalchemy import select

        result = await db_session.execute(
            select(RunSnapshotRow).where(
                RunSnapshotRow.run_id == UUID(run_id),
            )
        )
        snap_row = result.scalar_one()
        scenario_spec_id = snap_row.scenario_spec_id

        # Create a DepthPlan linked to this scenario
        plan_id = new_uuid7()
        now = utc_now()
        plan_row = DepthPlanRow(
            plan_id=plan_id,
            workspace_id=UUID(ws_id),
            scenario_spec_id=scenario_spec_id,
            status="COMPLETED",
            current_step="SUITE_PLANNING",
            degraded_steps=[],
            step_errors={},
            step_metadata=[
                {
                    "step": 1,
                    "step_name": "KHAWATIR",
                    "generation_mode": "FALLBACK",
                    "provider": "none",
                    "model": "fallback",
                    "duration_ms": 50,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
                {
                    "step": 5,
                    "step_name": "SUITE_PLANNING",
                    "generation_mode": "FALLBACK",
                    "provider": "none",
                    "model": "fallback",
                    "duration_ms": 30,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            ],
            created_at=now,
            updated_at=now,
        )
        db_session.add(plan_row)
        await db_session.flush()

        # Create MUJAHADA artifact with qualitative_risks
        muj_art = DepthArtifactRow(
            artifact_id=new_uuid7(),
            plan_id=plan_id,
            step="MUJAHADA",
            payload={
                "qualitative_risks": [
                    {
                        "risk_id": "r1",
                        "label": "Supply chain disruption",
                        "description": "Port closure risk",
                        "not_modeled": True,
                    },
                ],
                "contrarians": [],
            },
            disclosure_tier="TIER0",
            metadata_json={},
            created_at=now,
        )
        db_session.add(muj_art)

        # Create SUITE_PLANNING artifact with suite_plan
        suite_art = DepthArtifactRow(
            artifact_id=new_uuid7(),
            plan_id=plan_id,
            step="SUITE_PLANNING",
            payload={
                "suite_plan": {
                    "suite_id": str(new_uuid7()),
                    "runs": [
                        {
                            "name": "Base Case",
                            "mode": "SANDBOX",
                            "is_contrarian": False,
                            "sensitivities": [],
                            "executable_levers": [],
                        },
                        {
                            "name": "Contrarian",
                            "mode": "SANDBOX",
                            "is_contrarian": True,
                            "sensitivities": ["sweep"],
                            "executable_levers": [],
                        },
                    ],
                    "rationale": "Testing depth engine wiring",
                },
            },
            disclosure_tier="TIER1",
            metadata_json={},
            created_at=now,
        )
        db_session.add(suite_art)
        await db_session.flush()

        # Now GET the run again — should have depth_engine populated
        resp2 = await client.get(f"/v1/workspaces/{ws_id}/engine/runs/{run_id}")
        assert resp2.status_code == 200
        data2 = resp2.json()

        # depth_engine should now be present
        de = data2.get("depth_engine")
        assert de is not None, "depth_engine should be populated when linked depth plan exists"

        # Verify suite runs
        assert len(de["suite_runs"]) == 2
        assert de["suite_runs"][0]["name"] == "Base Case"
        assert de["suite_runs"][1]["name"] == "Contrarian"
        assert de["suite_runs"][1]["is_contrarian"] is True

        # Verify qualitative risks
        assert len(de["qualitative_risks"]) == 1
        assert de["qualitative_risks"][0]["label"] == "Supply chain disruption"

        # Verify trace steps
        assert len(de["trace_steps"]) == 2
        assert de["trace_steps"][0]["step_name"] == "KHAWATIR"
        assert de["trace_steps"][1]["step_name"] == "SUITE_PLANNING"

        # Verify plan metadata
        assert de["plan_id"] is not None
        assert de["suite_rationale"] == "Testing depth engine wiring"

    @pytest.mark.anyio
    async def test_run_response_depth_engine_null_without_plan(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """GET runs/{run_id} returns depth_engine=null when no plan linked."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        resp = await client.get(f"/v1/workspaces/{ws_id}/engine/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        # No depth plan → null
        assert data.get("depth_engine") is None
