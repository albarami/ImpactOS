"""Tests for S10-3: All protected endpoints reject unauthenticated requests.

Representative sample across every workspace-scoped router to verify
auth is wired. Uses unauthed_client (no auth override).
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.session import get_async_session


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    """Client WITHOUT auth override — tests real auth enforcement."""
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


WS = str(uuid7())


class TestDocumentsAuthCoverage:
    @pytest.mark.anyio
    async def test_list_documents_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get(f"/v1/workspaces/{WS}/documents")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_upload_document_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(f"/v1/workspaces/{WS}/documents")
        assert resp.status_code == 401


class TestCompilerAuthCoverage:
    @pytest.mark.anyio
    async def test_compile_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/compiler/compile", json={},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_compilation_status_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS}/compiler/{uuid7()}/status",
        )
        assert resp.status_code == 401


class TestScenariosAuthCoverage:
    @pytest.mark.anyio
    async def test_list_scenarios_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get(f"/v1/workspaces/{WS}/scenarios")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_create_scenario_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/scenarios", json={},
        )
        assert resp.status_code == 401


class TestRunsAuthCoverage:
    @pytest.mark.anyio
    async def test_create_run_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/engine/runs", json={},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_create_batch_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/engine/batch", json={},
        )
        assert resp.status_code == 401


class TestExportsAuthCoverage:
    @pytest.mark.anyio
    async def test_create_export_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/exports", json={},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_export_status_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS}/exports/{uuid7()}",
        )
        assert resp.status_code == 401


class TestGovernanceAuthCoverage:
    @pytest.mark.anyio
    async def test_nff_check_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/governance/nff/check", json={},
        )
        assert resp.status_code == 401


class TestLibrariesAuthCoverage:
    @pytest.mark.anyio
    async def test_list_mapping_entries_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS}/libraries/mapping/entries",
        )
        assert resp.status_code == 401


class TestDepthAuthCoverage:
    @pytest.mark.anyio
    async def test_trigger_depth_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS}/depth/plans", json={},
        )
        assert resp.status_code == 401


class TestModelsAuthCoverage:
    @pytest.mark.anyio
    async def test_list_models_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS}/models/versions",
        )
        assert resp.status_code == 401


class TestGlobalModelRegistration:
    @pytest.mark.anyio
    async def test_register_model_401(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.post("/v1/engine/models", json={})
        assert resp.status_code == 401
