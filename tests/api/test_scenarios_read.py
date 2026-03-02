"""Tests for B-9 + B-10: Scenario list and scenario detail."""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


@pytest.fixture
def other_workspace_id() -> str:
    return str(uuid7())


async def _create_scenario(
    client: AsyncClient,
    workspace_id: str,
    *,
    name: str = "Test Scenario",
    base_year: int = 2023,
    start_year: int = 2024,
    end_year: int = 2028,
) -> str:
    """Create a scenario via the existing POST endpoint and return scenario_spec_id."""
    resp = await client.post(
        f"/v1/workspaces/{workspace_id}/scenarios",
        json={
            "name": name,
            "base_model_version_id": str(uuid7()),
            "base_year": base_year,
            "start_year": start_year,
            "end_year": end_year,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["scenario_spec_id"]


# =========================================================================
# B-9: Scenario List
# =========================================================================


class TestScenarioList:
    @pytest.mark.anyio
    async def test_list_empty(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(f"/v1/workspaces/{workspace_id}/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["next_cursor"] is None

    @pytest.mark.anyio
    async def test_list_populated(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        sid = await _create_scenario(client, workspace_id, name="Alpha")
        resp = await client.get(f"/v1/workspaces/{workspace_id}/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["scenario_spec_id"] == sid
        assert item["name"] == "Alpha"
        assert "version" in item
        assert "created_at" in item
        assert "status" in item

    @pytest.mark.anyio
    async def test_latest_version_only(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """If a scenario has multiple versions, only the latest should appear in the list."""
        sid = await _create_scenario(client, workspace_id, name="Versioned")
        # Bump version by posting mapping decisions
        await client.post(
            f"/v1/workspaces/{workspace_id}/scenarios/{sid}/mapping-decisions",
            json={"decisions": []},
        )
        resp = await client.get(f"/v1/workspaces/{workspace_id}/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        # Should have exactly 1 entry for this scenario, not 2
        matching = [i for i in data["items"] if i["scenario_spec_id"] == sid]
        assert len(matching) == 1
        assert matching[0]["version"] == 2  # bumped from 1 to 2

    @pytest.mark.anyio
    async def test_list_pagination(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Create 3 scenarios, request limit=2 — should get next_cursor."""
        for i in range(3):
            await _create_scenario(client, workspace_id, name=f"Scenario {i}")

        resp1 = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios",
            params={"limit": 2},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 2
        assert data1["total"] == 3
        assert data1["next_cursor"] is not None

        resp2 = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios",
            params={"limit": 2, "cursor": data1["next_cursor"]},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) == 1
        assert data2["next_cursor"] is None

    @pytest.mark.anyio
    async def test_workspace_isolation(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Scenarios in workspace A must not appear when querying workspace B."""
        await _create_scenario(client, workspace_id, name="WS_A_Scenario")
        await _create_scenario(client, other_workspace_id, name="WS_B_Scenario")

        resp_a = await client.get(f"/v1/workspaces/{workspace_id}/scenarios")
        resp_b = await client.get(f"/v1/workspaces/{other_workspace_id}/scenarios")

        names_a = [s["name"] for s in resp_a.json()["items"]]
        names_b = [s["name"] for s in resp_b.json()["items"]]
        assert "WS_A_Scenario" in names_a
        assert "WS_B_Scenario" not in names_a
        assert "WS_B_Scenario" in names_b
        assert "WS_A_Scenario" not in names_b


# =========================================================================
# B-10: Scenario Get
# =========================================================================


class TestScenarioDetail:
    @pytest.mark.anyio
    async def test_get_existing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        sid = await _create_scenario(
            client, workspace_id,
            name="Detail Test",
            start_year=2024,
            end_year=2030,
        )
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios/{sid}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenario_spec_id"] == sid
        assert data["name"] == "Detail Test"
        assert data["version"] == 1
        assert "time_horizon" in data
        assert data["time_horizon"]["start_year"] == 2024
        assert data["time_horizon"]["end_year"] == 2030
        assert "shock_items" in data
        assert "status" in data

    @pytest.mark.anyio
    async def test_draft_status(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """A freshly created scenario (no compile) should have status DRAFT."""
        sid = await _create_scenario(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios/{sid}",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "DRAFT"

    @pytest.mark.anyio
    async def test_404_missing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios/{uuid7()}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_404_wrong_workspace(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Scenario exists but belongs to a different workspace → 404."""
        sid = await _create_scenario(client, workspace_id, name="Private")
        resp = await client.get(
            f"/v1/workspaces/{other_workspace_id}/scenarios/{sid}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_response_contains_full_fields(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Response must include shock_items, time_horizon, version, status."""
        sid = await _create_scenario(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/scenarios/{sid}",
        )
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "scenario_spec_id", "name", "version", "workspace_id",
            "time_horizon", "shock_items", "status", "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
