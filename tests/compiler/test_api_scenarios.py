"""Tests for FastAPI scenario endpoints (MVP-4).

S0-4: Workspace-scoped routes.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())


def _scenario_create_payload() -> dict:
    return {
        "name": "NEOM Logistics Zone",
        "base_model_version_id": str(uuid7()),
        "base_year": 2023,
        "start_year": 2026,
        "end_year": 2030,
    }


class TestCreateScenarioEndpoint:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_create_returns_scenario_id(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        data = response.json()
        assert "scenario_spec_id" in data
        assert data["version"] == 1
        assert data["name"] == "NEOM Logistics Zone"


class TestCompileEndpoint:
    @pytest.mark.anyio
    async def test_compile_returns_200(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        line_item_id = str(uuid7())
        compile_payload = {
            "line_items": [
                {"line_item_id": line_item_id, "description": "Structural Steel", "total_value": 1000000.0, "currency_code": "SAR"},
            ],
            "decisions": [
                {"line_item_id": line_item_id, "final_sector_code": "C41", "decision_type": "APPROVED", "suggested_confidence": 0.90, "decided_by": str(uuid7())},
            ],
            "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
            "default_domestic_share": 0.65,
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile", json=compile_payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_compile_returns_shock_items(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        line_item_id = str(uuid7())
        compile_payload = {
            "line_items": [
                {"line_item_id": line_item_id, "description": "Steel", "total_value": 1000000.0, "currency_code": "SAR"},
            ],
            "decisions": [
                {"line_item_id": line_item_id, "final_sector_code": "C41", "decision_type": "APPROVED", "suggested_confidence": 0.90, "decided_by": str(uuid7())},
            ],
            "phasing": {"2026": 1.0},
            "default_domestic_share": 0.65,
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile", json=compile_payload)
        data = response.json()
        assert "shock_items" in data
        assert len(data["shock_items"]) >= 1
        assert "data_quality_summary" in data

    @pytest.mark.anyio
    async def test_compile_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{uuid7()}/compile",
            json={"line_items": [], "decisions": [], "phasing": {}, "default_domestic_share": 0.65},
        )
        assert response.status_code == 404


class TestMappingDecisionsEndpoint:
    @pytest.mark.anyio
    async def test_bulk_decisions_returns_200(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        payload = {
            "decisions": [
                {"line_item_id": str(uuid7()), "final_sector_code": "C41", "decision_type": "APPROVED", "decided_by": str(uuid7()), "rationale": "Correct mapping"},
            ],
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/mapping-decisions", json=payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_bulk_decisions_increments_version(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        payload = {
            "decisions": [
                {"line_item_id": str(uuid7()), "final_sector_code": "F", "decision_type": "OVERRIDDEN", "decided_by": str(uuid7()), "rationale": "Changed to construction"},
            ],
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/mapping-decisions", json=payload)
        data = response.json()
        assert data["new_version"] == 2


class TestGetVersionsEndpoint:
    @pytest.mark.anyio
    async def test_versions_returns_200(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/versions")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_versions_returns_list(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/versions")
        data = response.json()
        assert "versions" in data
        assert len(data["versions"]) >= 1

    @pytest.mark.anyio
    async def test_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/scenarios/{uuid7()}/versions")
        assert response.status_code == 404


class TestLockEndpoint:
    @pytest.mark.anyio
    async def test_lock_returns_200(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        payload = {"actor": str(uuid7())}
        response = await client.post(f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/lock", json=payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_lock_increments_version(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json=_scenario_create_payload())
        scenario_id = create_resp.json()["scenario_spec_id"]
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/lock",
            json={"actor": str(uuid7())},
        )
        data = response.json()
        assert data["new_version"] == 2
