"""Tests for B-6: Taxonomy browsing API."""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


class TestListSectors:
    async def test_list_all_sectors(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 21
        assert data["total"] >= 21

    async def test_list_sections_only(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors",
            params={"level": "section"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["level"] == "section" for i in items)
        codes = [i["sector_code"] for i in items]
        assert "A" in codes
        assert "C" in codes

    async def test_list_divisions_only(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors",
            params={"level": "division"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(i["level"] == "division" for i in items)
        assert len(items) >= 80  # 84 active divisions

    async def test_list_returns_expected_fields(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors",
            params={"level": "section"},
        )
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "sector_code" in item
        assert "name_en" in item
        assert "name_ar" in item
        assert "level" in item
        assert "parent_code" in item
        assert "description" in item


class TestSearchSectors:
    async def test_search_by_code(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/search",
            params={"q": "C"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        codes = [i["sector_code"] for i in items]
        assert "C" in codes

    async def test_search_by_name_case_insensitive(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/search",
            params={"q": "manufacturing"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1

    async def test_search_no_results(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/search",
            params={"q": "zzzznonexistent"},
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    async def test_search_requires_query(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/search",
        )
        assert resp.status_code == 422  # missing required q param


class TestGetSector:
    async def test_get_existing_section(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/A",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sector_code"] == "A"
        assert "Agriculture" in data["name_en"]
        assert data["level"] == "section"

    async def test_get_existing_division(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/01",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sector_code"] == "01"
        assert data["level"] == "division"
        assert data["parent_code"] == "A"

    async def test_get_missing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/taxonomy/sectors/ZZZ",
        )
        assert resp.status_code == 404
