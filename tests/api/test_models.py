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
        assert data["model_version_id"] == mv_id
        assert isinstance(data["source"], str)
        assert len(data["source"]) > 0
        coeffs = data["sector_coefficients"]
        assert isinstance(coeffs, list)
        assert len(coeffs) >= 1
        for coeff in coeffs:
            assert isinstance(coeff["sector_code"], str)
            assert len(coeff["sector_code"]) > 0
            assert isinstance(coeff["jobs_coeff"], (int, float))
            assert isinstance(coeff["import_ratio"], (int, float))
            assert isinstance(coeff["va_ratio"], (int, float))
            # Coefficients must be non-negative
            assert coeff["jobs_coeff"] >= 0.0
            assert coeff["import_ratio"] >= 0.0
            assert coeff["va_ratio"] >= 0.0

    @pytest.mark.anyio
    async def test_get_coefficients_sector_codes_unique(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        mv_id = await _register_model(client)
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{mv_id}/coefficients",
        )
        assert resp.status_code == 200
        codes = [c["sector_code"] for c in resp.json()["sector_coefficients"]]
        assert len(codes) == len(set(codes)), "Duplicate sector codes in coefficients"

    @pytest.mark.anyio
    async def test_get_coefficients_missing_model(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        resp = await client.get(
            f"/v1/workspaces/{workspace_id}/models/versions/{uuid7()}/coefficients",
        )
        assert resp.status_code == 404
