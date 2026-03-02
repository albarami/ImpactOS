"""Tests for B-17: GET compilation detail.

GET /v1/workspaces/{ws}/compiler/{compilation_id}  — B-17
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.repositories.compiler import CompilationRepository


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


@pytest.fixture
def other_workspace_id() -> str:
    return str(uuid7())


async def _trigger_compilation(
    client: AsyncClient,
    workspace_id: str,
) -> str:
    """Trigger a compilation via POST and return compilation_id."""
    resp = await client.post(
        f"/v1/workspaces/{workspace_id}/compiler/compile",
        json={
            "scenario_name": "Test Scenario",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2028,
            "line_items": [
                {
                    "line_item_id": str(uuid7()),
                    "raw_text": "concrete works for building foundation",
                    "total_value": 500000.0,
                },
                {
                    "line_item_id": str(uuid7()),
                    "raw_text": "transport services for materials",
                    "total_value": 100000.0,
                },
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["compilation_id"]


# =========================================================================
# B-17: GET compilation detail
# =========================================================================


class TestCompilationDetail:
    @pytest.mark.anyio
    async def test_get_compilation_detail(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compilation_id"] == comp_id
        assert "suggestions" in data
        assert "high_confidence" in data
        assert "medium_confidence" in data
        assert "low_confidence" in data
        assert "metadata" in data

    @pytest.mark.anyio
    async def test_compilation_detail_suggestions_structure(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Each suggestion should have line_item_id, sector_code, confidence, explanation."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["suggestions"]) >= 1
        suggestion = data["suggestions"][0]
        assert "line_item_id" in suggestion
        assert "sector_code" in suggestion
        assert "confidence" in suggestion
        assert "explanation" in suggestion

    @pytest.mark.anyio
    async def test_compilation_detail_404(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{uuid7()}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compilation_detail_wrong_workspace_404(
        self, client: AsyncClient, workspace_id: str, other_workspace_id: str,
    ) -> None:
        """Compilation exists but queried from wrong workspace -> 404."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{other_workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_compilation_detail_metadata(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include metadata about the compilation input."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "metadata" in data
        # metadata should include the input information
        assert isinstance(data["metadata"], dict)

    @pytest.mark.anyio
    async def test_compilation_detail_confidence_counts(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Confidence counts should be non-negative integers."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["high_confidence"], int)
        assert isinstance(data["medium_confidence"], int)
        assert isinstance(data["low_confidence"], int)
        assert data["high_confidence"] >= 0
        assert data["medium_confidence"] >= 0
        assert data["low_confidence"] >= 0

    @pytest.mark.anyio
    async def test_compilation_detail_has_assumption_drafts(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include assumption_drafts list."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "assumption_drafts" in data
        assert isinstance(data["assumption_drafts"], list)

    @pytest.mark.anyio
    async def test_compilation_detail_has_split_proposals(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Detail should include split_proposals list."""
        comp_id = await _trigger_compilation(client, workspace_id)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "split_proposals" in data
        assert isinstance(data["split_proposals"], list)

    @pytest.mark.anyio
    async def test_compilation_missing_workspace_metadata_404(
        self, client: AsyncClient, workspace_id: str,
        db_session: AsyncSession,
    ) -> None:
        """Legacy compilation with no workspace_id in metadata -> 404."""
        comp_repo = CompilationRepository(db_session)
        comp_id = uuid7()
        await comp_repo.create(
            compilation_id=comp_id,
            result_json={"mapping_suggestions": []},
            metadata_json={"document_id": None},  # no workspace_id
        )

        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/compiler/{comp_id}",
        )
        assert resp.status_code == 404
