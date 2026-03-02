"""Tests for B-14 + B-15: Model version list/detail + coefficient retrieval."""

import numpy as np
import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


async def _register_model(client: AsyncClient) -> str:
    """Register a model via the existing global endpoint."""
    n = 3
    Z = np.array([
        [0.1, 0.2, 0.05],
        [0.15, 0.1, 0.1],
        [0.05, 0.1, 0.15],
    ])
    x = np.array([10.0, 15.0, 12.0])
    resp = await client.post("/v1/engine/models", json={
        "Z": Z.tolist(),
        "x": x.tolist(),
        "sector_codes": ["A", "B", "C"],
        "base_year": 2023,
        "source": "test-model",
    })
    assert resp.status_code == 201
    return resp.json()["model_version_id"]


class TestListModelVersions:
    @pytest.mark.anyio
    async def test_list_empty(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.anyio
    async def test_list_populated(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert "model_version_id" in item
        assert item["base_year"] == 2023
        assert item["sector_count"] == 3


class TestGetModelVersion:
    @pytest.mark.anyio
    async def test_get_existing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_version_id"] == mv_id
        assert data["source"] == "test-model"
        assert data["checksum"].startswith("sha256:")

    @pytest.mark.anyio
    async def test_get_missing(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{uuid7()}",
        )
        assert resp.status_code == 404


class TestGetCoefficients:
    @pytest.mark.anyio
    async def test_get_coefficients_for_valid_model(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sector_coefficients" in data
        assert len(data["sector_coefficients"]) >= 1
        first = data["sector_coefficients"][0]
        assert "sector_code" in first
        assert "jobs_coeff" in first
        assert "import_ratio" in first
        assert "va_ratio" in first

    @pytest.mark.anyio
    async def test_get_coefficients_missing_model(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{uuid7()}/coefficients",
        )
        assert resp.status_code == 404
