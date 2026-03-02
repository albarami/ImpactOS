"""Tests for B-1: Workspace CRUD endpoints."""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


class TestCreateWorkspace:
    @pytest.mark.anyio
    async def test_create_workspace(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/workspaces", json={
            "client_name": "Test Client",
            "engagement_code": "ENG-001",
            "classification": "CONFIDENTIAL",
            "description": "Test workspace",
            "created_by": str(uuid7()),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["client_name"] == "Test Client"
        assert data["engagement_code"] == "ENG-001"
        assert "workspace_id" in data

    @pytest.mark.anyio
    async def test_create_workspace_minimal(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/workspaces", json={
            "client_name": "Minimal",
            "engagement_code": "ENG-002",
            "created_by": str(uuid7()),
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["classification"] == "CONFIDENTIAL"


class TestListWorkspaces:
    @pytest.mark.anyio
    async def test_list_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/v1/workspaces")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_populated(self, client: AsyncClient) -> None:
        created_by = str(uuid7())
        await client.post("/v1/workspaces", json={
            "client_name": "A", "engagement_code": "E1", "created_by": created_by,
        })
        await client.post("/v1/workspaces", json={
            "client_name": "B", "engagement_code": "E2", "created_by": created_by,
        })
        resp = await client.get("/v1/workspaces")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2


class TestGetWorkspace:
    @pytest.mark.anyio
    async def test_get_existing(self, client: AsyncClient) -> None:
        create_resp = await client.post("/v1/workspaces", json={
            "client_name": "Get Test",
            "engagement_code": "ENG-GET",
            "created_by": str(uuid7()),
        })
        ws_id = create_resp.json()["workspace_id"]
        resp = await client.get(f"/v1/workspaces/{ws_id}")
        assert resp.status_code == 200
        assert resp.json()["client_name"] == "Get Test"

    @pytest.mark.anyio
    async def test_get_missing(self, client: AsyncClient) -> None:
        resp = await client.get(f"/v1/workspaces/{uuid7()}")
        assert resp.status_code == 404


class TestUpdateWorkspace:
    @pytest.mark.anyio
    async def test_update_existing(self, client: AsyncClient) -> None:
        create_resp = await client.post("/v1/workspaces", json={
            "client_name": "Before",
            "engagement_code": "ENG-UPD",
            "created_by": str(uuid7()),
        })
        ws_id = create_resp.json()["workspace_id"]
        resp = await client.put(f"/v1/workspaces/{ws_id}", json={
            "client_name": "After",
            "description": "Updated description",
        })
        assert resp.status_code == 200
        assert resp.json()["client_name"] == "After"
        assert resp.json()["description"] == "Updated description"

    @pytest.mark.anyio
    async def test_update_missing(self, client: AsyncClient) -> None:
        resp = await client.put(f"/v1/workspaces/{uuid7()}", json={
            "client_name": "No such workspace",
        })
        assert resp.status_code == 404
