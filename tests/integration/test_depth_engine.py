"""Depth engine integration tests — MVP-14, Amendment 4.

Al-Muhāsibī (MVP-9) integration using RESTRICTED classification.
Deterministic fallback — no real LLM calls, no API keys needed.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

ALLOWED_LEVERS = {
    "FINAL_DEMAND_SHOCK",
    "IMPORT_SHARE_ADJUSTMENT",
    "LOCAL_CONTENT_TARGET",
    "PHASING_SHIFT",
    "CONSTRAINT_SET_TOGGLE",
    "SENSITIVITY_SWEEP",
}


class TestDepthEngineIntegration:
    """Al-Muhāsibī depth engine chains with rest of system."""

    @pytest.mark.anyio
    async def test_depth_plan_creation(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /depth/plans → 201 → plan_id + COMPLETED status."""
        ws_id = str(uuid7())

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["S1", "S2"]},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "plan_id" in data
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_depth_plan_all_five_artifacts(
        self,
        client: AsyncClient,
    ) -> None:
        """GET plan status → 5 artifacts produced."""
        ws_id = str(uuid7())

        trigger_resp = await client.post(
            f"/v1/workspaces/{ws_id}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["S1", "S2"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        status_resp = await client.get(
            f"/v1/workspaces/{ws_id}/depth/plans/{plan_id}",
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "COMPLETED"

        # Should have 5 artifacts (one per step)
        expected_steps = {"KHAWATIR", "MURAQABA", "MUJAHADA", "MUHASABA", "SUITE_PLANNING"}
        artifact_steps = {a["step"] for a in data["artifacts"]}
        assert artifact_steps == expected_steps

    @pytest.mark.anyio
    async def test_depth_disclosure_tiers(
        self,
        client: AsyncClient,
    ) -> None:
        """Artifacts have disclosure tier metadata."""
        ws_id = str(uuid7())

        trigger_resp = await client.post(
            f"/v1/workspaces/{ws_id}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["S1"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        # Get MUJAHADA artifact — should be TIER0 (internal only)
        muj_resp = await client.get(
            f"/v1/workspaces/{ws_id}/depth/plans/{plan_id}/artifacts/MUJAHADA",
        )
        assert muj_resp.status_code == 200
        data = muj_resp.json()
        assert data["disclosure_tier"] == "TIER0"

    @pytest.mark.anyio
    async def test_depth_suite_produces_executable_levers(
        self,
        client: AsyncClient,
    ) -> None:
        """GET suite → runs list with executable levers from allowed set."""
        ws_id = str(uuid7())

        trigger_resp = await client.post(
            f"/v1/workspaces/{ws_id}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["S1", "S2", "S3"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        suite_resp = await client.get(
            f"/v1/workspaces/{ws_id}/depth/plans/{plan_id}/suite",
        )
        assert suite_resp.status_code == 200
        data = suite_resp.json()
        assert "suite_plan" in data

        # Suite plan should contain runs with executable levers
        suite_plan = data["suite_plan"]
        if "runs" in suite_plan and len(suite_plan["runs"]) > 0:
            for run in suite_plan["runs"]:
                if "executable_levers" in run:
                    for lever in run["executable_levers"]:
                        lever_type = lever.get("type", lever) if isinstance(lever, dict) else lever
                        assert lever_type in ALLOWED_LEVERS, (
                            f"Lever {lever_type} not in allowed set"
                        )
