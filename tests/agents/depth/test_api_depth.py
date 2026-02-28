"""Tests for FastAPI depth engine endpoints — MVP-9.

Tests the 4 workspace-scoped endpoints:
- POST trigger (sync mode)
- GET plan status + artifact summaries
- GET artifact by step
- GET suite convenience endpoint

Plus: disclosure tier filtering, error cases, 400/403/404 responses.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


WS_ID = str(uuid7())


class TestTriggerDepthPlan:
    @pytest.mark.anyio
    async def test_trigger_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {
                    "workspace_description": "Saudi mega-project",
                    "sector_codes": ["SEC01", "SEC02", "SEC03"],
                },
            },
        )
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_trigger_returns_plan_id_and_status(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {
                    "sector_codes": ["SEC01"],
                },
            },
        )
        data = response.json()
        assert "plan_id" in data
        assert "status" in data
        # Sync mode: should complete inline
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_trigger_with_scenario_spec_id(self, client: AsyncClient) -> None:
        spec_id = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "scenario_spec_id": spec_id,
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_trigger_minimal_context(self, client: AsyncClient) -> None:
        """Empty context should still work (deterministic fallback)."""
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={"classification": "RESTRICTED"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "COMPLETED"


class TestGetDepthPlanStatus:
    @pytest.mark.anyio
    async def test_get_status_returns_200(self, client: AsyncClient) -> None:
        # First trigger a plan
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
        )
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_status_contains_all_fields(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
        )
        data = response.json()
        assert data["plan_id"] == plan_id
        assert data["status"] == "COMPLETED"
        assert "workspace_id" in data
        assert "degraded_steps" in data
        assert "step_errors" in data
        assert "artifacts" in data

    @pytest.mark.anyio
    async def test_status_shows_5_artifacts(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
        )
        data = response.json()
        assert len(data["artifacts"]) == 5

        steps = {a["step"] for a in data["artifacts"]}
        assert steps == {
            "KHAWATIR", "MURAQABA", "MUJAHADA", "MUHASABA", "SUITE_PLANNING",
        }

    @pytest.mark.anyio
    async def test_status_shows_degraded_steps(self, client: AsyncClient) -> None:
        """RESTRICTED classification → all 5 steps should be degraded."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
        )
        data = response.json()
        assert len(data["degraded_steps"]) == 5

    @pytest.mark.anyio
    async def test_status_404_for_missing_plan(self, client: AsyncClient) -> None:
        fake_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{fake_id}",
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_status_disclosure_tier_filter(self, client: AsyncClient) -> None:
        """Filtering by TIER1 should exclude TIER0 artifacts."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        # TIER1 filter: only SUITE_PLANNING (TIER1) should pass
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
            params={"max_disclosure_tier": "TIER1"},
        )
        data = response.json()
        # All 5 artifacts visible (TIER0 <= TIER1, TIER1 <= TIER1)
        tier_values = {a["disclosure_tier"] for a in data["artifacts"]}
        for tier in tier_values:
            assert tier in ("TIER0", "TIER1")

    @pytest.mark.anyio
    async def test_status_disclosure_tier0_filter(self, client: AsyncClient) -> None:
        """Filtering by TIER0 should only show TIER0 artifacts."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}",
            params={"max_disclosure_tier": "TIER0"},
        )
        data = response.json()
        # TIER0 filter: should exclude SUITE_PLANNING (TIER1)
        for a in data["artifacts"]:
            assert a["disclosure_tier"] == "TIER0"
        # SUITE_PLANNING is TIER1, so should not be in list
        steps = {a["step"] for a in data["artifacts"]}
        assert "SUITE_PLANNING" not in steps


class TestGetDepthArtifact:
    @pytest.mark.anyio
    async def test_get_artifact_returns_200(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/KHAWATIR",
        )
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_artifact_contains_payload(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/KHAWATIR",
        )
        data = response.json()
        assert "artifact_id" in data
        assert "plan_id" in data
        assert data["step"] == "KHAWATIR"
        assert "payload" in data
        assert "disclosure_tier" in data
        assert "metadata" in data

    @pytest.mark.anyio
    async def test_khawatir_artifact_has_candidates(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/KHAWATIR",
        )
        data = response.json()
        assert "candidates" in data["payload"]
        assert len(data["payload"]["candidates"]) >= 3

    @pytest.mark.anyio
    async def test_muraqaba_artifact_has_bias_register(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/MURAQABA",
        )
        data = response.json()
        assert "bias_register" in data["payload"]

    @pytest.mark.anyio
    async def test_mujahada_artifact_has_contrarians(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/MUJAHADA",
        )
        data = response.json()
        assert "contrarians" in data["payload"]
        assert "qualitative_risks" in data["payload"]

    @pytest.mark.anyio
    async def test_muhasaba_artifact_has_scored(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/MUHASABA",
        )
        data = response.json()
        assert "scored" in data["payload"]
        assert len(data["payload"]["scored"]) > 0

    @pytest.mark.anyio
    async def test_artifact_metadata_has_generation_mode(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/KHAWATIR",
        )
        data = response.json()
        assert data["metadata"]["generation_mode"] == "FALLBACK"
        assert data["metadata"]["classification"] == "RESTRICTED"

    @pytest.mark.anyio
    async def test_artifact_invalid_step_returns_400(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={"classification": "RESTRICTED"},
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/INVALID_STEP",
        )
        assert response.status_code == 400

    @pytest.mark.anyio
    async def test_artifact_missing_plan_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{fake_id}/artifacts/KHAWATIR",
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_artifact_disclosure_tier_filtering(self, client: AsyncClient) -> None:
        """Request TIER0 max → TIER1 artifact should return 403."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        # SUITE_PLANNING is TIER1 — requesting with TIER0 max should be blocked
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/SUITE_PLANNING",
            params={"max_disclosure_tier": "TIER0"},
        )
        assert response.status_code == 403

    @pytest.mark.anyio
    async def test_artifact_disclosure_tier_allows_same_level(self, client: AsyncClient) -> None:
        """Request TIER1 max → TIER1 artifact should return 200."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/artifacts/SUITE_PLANNING",
            params={"max_disclosure_tier": "TIER1"},
        )
        assert response.status_code == 200


class TestGetDepthSuite:
    @pytest.mark.anyio
    async def test_suite_returns_200(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/suite",
        )
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_suite_contains_plan_data(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/suite",
        )
        data = response.json()
        assert data["plan_id"] == plan_id
        assert "suite_plan" in data

    @pytest.mark.anyio
    async def test_suite_has_runs(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/suite",
        )
        suite = response.json()["suite_plan"]
        assert "runs" in suite
        assert len(suite["runs"]) > 0
        assert "recommended_outputs" in suite
        assert "qualitative_risks" in suite

    @pytest.mark.anyio
    async def test_suite_runs_have_executable_levers(self, client: AsyncClient) -> None:
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01", "SEC02", "SEC03"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/suite",
        )
        suite = response.json()["suite_plan"]
        for run in suite["runs"]:
            assert "name" in run
            assert "executable_levers" in run
            assert "mode" in run
            assert "disclosure_tier" in run

    @pytest.mark.anyio
    async def test_suite_qualitative_risks_not_modeled(self, client: AsyncClient) -> None:
        """All qualitative risks should have not_modeled=True (agent-to-math boundary)."""
        trigger_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/depth/plans",
            json={
                "classification": "RESTRICTED",
                "context": {"sector_codes": ["SEC01"]},
            },
        )
        plan_id = trigger_resp.json()["plan_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{plan_id}/suite",
        )
        suite = response.json()["suite_plan"]
        for risk in suite.get("qualitative_risks", []):
            assert risk["not_modeled"] is True

    @pytest.mark.anyio
    async def test_suite_404_for_missing_plan(self, client: AsyncClient) -> None:
        fake_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/depth/plans/{fake_id}/suite",
        )
        assert response.status_code == 404
