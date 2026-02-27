"""Tests for FastAPI export endpoints (MVP-6).

Covers: POST create export, GET export status, POST variance bridge.
S0-4: Workspace-scoped routes.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())


def _make_export_payload() -> dict:
    return {
        "run_id": str(uuid7()),
        "mode": "SANDBOX",
        "export_formats": ["excel"],
        "pack_data": {
            "run_id": str(uuid7()),
            "scenario_name": "Test Scenario",
            "base_year": 2023,
            "currency": "SAR",
            "model_version_id": str(uuid7()),
            "scenario_version": 1,
            "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
            "sector_impacts": [
                {"sector_code": "C41", "sector_name": "Steel", "direct_impact": 500.0,
                 "indirect_impact": 250.0, "total_impact": 750.0, "multiplier": 1.5,
                 "domestic_share": 0.65, "import_leakage": 0.35},
            ],
            "input_vectors": {"C41": 1000.0},
            "sensitivity": [],
            "assumptions": [],
            "evidence_ledger": [],
        },
    }


class TestCreateExport:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_create_returns_export_id(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        data = response.json()
        assert "export_id" in data
        assert "status" in data

    @pytest.mark.anyio
    async def test_create_sandbox_succeeds(self, client: AsyncClient) -> None:
        payload = _make_export_payload()
        payload["mode"] = "SANDBOX"
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_create_with_pptx_format(self, client: AsyncClient) -> None:
        payload = _make_export_payload()
        payload["export_formats"] = ["pptx"]
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=payload)
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_create_returns_checksums(self, client: AsyncClient) -> None:
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        data = response.json()
        assert "checksums" in data


class TestGetExportStatus:
    @pytest.mark.anyio
    async def test_get_status_returns_200(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        export_id = create_resp.json()["export_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{export_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_get_status_contains_fields(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/exports", json=_make_export_payload())
        export_id = create_resp.json()["export_id"]
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{export_id}")
        data = response.json()
        assert "export_id" in data
        assert "status" in data
        assert "mode" in data

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/exports/{uuid7()}")
        assert response.status_code == 404


class TestVarianceBridge:
    @pytest.mark.anyio
    async def test_bridge_returns_200(self, client: AsyncClient) -> None:
        payload = {
            "run_a": {
                "run_id": str(uuid7()),
                "total_impact": 4_200_000_000.0,
                "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
                "import_shares": {"C41": 0.35},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
            "run_b": {
                "run_id": str(uuid7()),
                "total_impact": 4_500_000_000.0,
                "phasing": {"2026": 0.5, "2027": 0.3, "2028": 0.2},
                "import_shares": {"C41": 0.35},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports/variance-bridge", json=payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_bridge_returns_waterfall(self, client: AsyncClient) -> None:
        payload = {
            "run_a": {
                "run_id": str(uuid7()),
                "total_impact": 4_200_000_000.0,
                "phasing": {"2026": 0.3},
                "import_shares": {},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v1",
            },
            "run_b": {
                "run_id": str(uuid7()),
                "total_impact": 4_500_000_000.0,
                "phasing": {"2026": 0.3},
                "import_shares": {},
                "mapping_count": 50,
                "constraints_active": 0,
                "model_version": "v2",
            },
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/exports/variance-bridge", json=payload)
        data = response.json()
        assert "start_value" in data
        assert "end_value" in data
        assert "total_variance" in data
        assert "drivers" in data
