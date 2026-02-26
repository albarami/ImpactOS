"""Tests for AI compiler API endpoints (MVP-8).

Covers: POST trigger AI-assisted compilation, GET suggestion status,
POST accept/reject suggestions in bulk.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.api.main import app


@pytest.fixture
def base_url() -> str:
    return "http://test"


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


# ===================================================================
# POST /v1/compiler/compile — trigger AI-assisted compilation
# ===================================================================


class TestTriggerCompilation:
    """POST /v1/compiler/compile — trigger AI-assisted compilation."""

    @pytest.mark.asyncio
    async def test_compile_returns_201(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "NEOM Logistics Base",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "concrete works",
                        "total_value": 2000000.0,
                    },
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "steel reinforcement",
                        "total_value": 1500000.0,
                    },
                ],
                "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
            })
        assert resp.status_code == 201
        data = resp.json()
        assert "compilation_id" in data
        assert "suggestions" in data

    @pytest.mark.asyncio
    async def test_compile_returns_suggestions(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2028,
                "line_items": [
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
                "phasing": {"2026": 1.0},
            })
        data = resp.json()
        assert len(data["suggestions"]) == 1
        assert "sector_code" in data["suggestions"][0]
        assert "confidence" in data["suggestions"][0]

    @pytest.mark.asyncio
    async def test_compile_empty_items(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "Empty",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2028,
                "line_items": [],
                "phasing": {},
            })
        assert resp.status_code == 201
        assert len(resp.json()["suggestions"]) == 0


# ===================================================================
# GET /v1/compiler/{id}/status — suggestion status
# ===================================================================


class TestSuggestionStatus:
    """GET /v1/compiler/{id}/status — retrieve suggestion status."""

    @pytest.mark.asyncio
    async def test_get_status(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            # First create a compilation
            create_resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "Status Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2028,
                "line_items": [
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
                "phasing": {"2026": 1.0},
            })
            comp_id = create_resp.json()["compilation_id"]

            resp = await client.get(f"/v1/compiler/{comp_id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["compilation_id"] == comp_id
        assert "high_confidence" in data
        assert "low_confidence" in data

    @pytest.mark.asyncio
    async def test_status_not_found(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.get(f"/v1/compiler/{uuid7()}/status")
        assert resp.status_code == 404


# ===================================================================
# POST /v1/compiler/{id}/decisions — accept/reject suggestions
# ===================================================================


class TestBulkDecisions:
    """POST /v1/compiler/{id}/decisions — accept/reject in bulk."""

    @pytest.mark.asyncio
    async def test_bulk_accept(self, transport: ASGITransport, base_url: str) -> None:
        li_id = str(uuid7())
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            create_resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "Decision Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2028,
                "line_items": [
                    {
                        "line_item_id": li_id,
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
                "phasing": {"2026": 1.0},
            })
            comp_id = create_resp.json()["compilation_id"]

            resp = await client.post(f"/v1/compiler/{comp_id}/decisions", json={
                "decisions": [
                    {
                        "line_item_id": li_id,
                        "action": "accept",
                    },
                ],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] >= 1

    @pytest.mark.asyncio
    async def test_bulk_reject(self, transport: ASGITransport, base_url: str) -> None:
        li_id = str(uuid7())
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            create_resp = await client.post("/v1/compiler/compile", json={
                "workspace_id": str(uuid7()),
                "scenario_name": "Reject Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2020,
                "start_year": 2026,
                "end_year": 2028,
                "line_items": [
                    {
                        "line_item_id": li_id,
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
                "phasing": {"2026": 1.0},
            })
            comp_id = create_resp.json()["compilation_id"]

            resp = await client.post(f"/v1/compiler/{comp_id}/decisions", json={
                "decisions": [
                    {
                        "line_item_id": li_id,
                        "action": "reject",
                        "override_sector_code": "H",
                        "note": "Should be transport",
                    },
                ],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["rejected"] >= 1

    @pytest.mark.asyncio
    async def test_decisions_not_found(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post(f"/v1/compiler/{uuid7()}/decisions", json={
                "decisions": [],
            })
        assert resp.status_code == 404
