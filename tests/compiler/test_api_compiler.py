"""Tests for AI compiler API endpoints (MVP-8).

S0-4: Workspace-scoped routes.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())


class TestTriggerCompilation:
    @pytest.mark.anyio
    async def test_compile_returns_201(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "NEOM Logistics Base",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2030,
            "line_items": [
                {"line_item_id": str(uuid7()), "raw_text": "concrete works", "total_value": 2000000.0},
                {"line_item_id": str(uuid7()), "raw_text": "steel reinforcement", "total_value": 1500000.0},
            ],
            "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "compilation_id" in data
        assert "suggestions" in data

    @pytest.mark.anyio
    async def test_compile_returns_suggestions(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2028,
            "line_items": [
                {"line_item_id": str(uuid7()), "raw_text": "concrete works", "total_value": 1000000.0},
            ],
            "phasing": {"2026": 1.0},
        })
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert "sector_code" in data["suggestions"][0]
        assert "confidence" in data["suggestions"][0]

    @pytest.mark.anyio
    async def test_compile_empty_items_returns_422(self, client: AsyncClient) -> None:
        """S0-4: empty line_items with no document_id → 422 (exactly one source required)."""
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "Empty",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2028,
            "line_items": [],
            "phasing": {},
        })
        assert resp.status_code == 422


class TestSuggestionStatus:
    @pytest.mark.anyio
    async def test_get_status(self, client: AsyncClient) -> None:
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "Status Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2028,
            "line_items": [
                {"line_item_id": str(uuid7()), "raw_text": "concrete works", "total_value": 1000000.0},
            ],
            "phasing": {"2026": 1.0},
        })
        comp_id = create_resp.json()["compilation_id"]
        resp = await client.get(f"/v1/workspaces/{WS_ID}/compiler/{comp_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["compilation_id"] == comp_id
        assert "high_confidence" in data
        assert "low_confidence" in data

    @pytest.mark.anyio
    async def test_status_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/v1/workspaces/{WS_ID}/compiler/{uuid7()}/status")
        assert resp.status_code == 404


class TestBulkDecisions:
    @pytest.mark.anyio
    async def test_bulk_accept(self, client: AsyncClient) -> None:
        li_id = str(uuid7())
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "Decision Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2028,
            "line_items": [
                {"line_item_id": li_id, "raw_text": "concrete works", "total_value": 1000000.0},
            ],
            "phasing": {"2026": 1.0},
        })
        comp_id = create_resp.json()["compilation_id"]
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/{comp_id}/decisions", json={
            "decisions": [{"line_item_id": li_id, "action": "accept"}],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] >= 1

    @pytest.mark.anyio
    async def test_bulk_reject(self, client: AsyncClient) -> None:
        li_id = str(uuid7())
        create_resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/compile", json={
            "scenario_name": "Reject Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2020,
            "start_year": 2026,
            "end_year": 2028,
            "line_items": [
                {"line_item_id": li_id, "raw_text": "concrete works", "total_value": 1000000.0},
            ],
            "phasing": {"2026": 1.0},
        })
        comp_id = create_resp.json()["compilation_id"]
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/{comp_id}/decisions", json={
            "decisions": [
                {"line_item_id": li_id, "action": "reject", "override_sector_code": "H", "note": "Should be transport"},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rejected"] >= 1

    @pytest.mark.anyio
    async def test_decisions_not_found(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/compiler/{uuid7()}/decisions", json={
            "decisions": [],
        })
        assert resp.status_code == 404
