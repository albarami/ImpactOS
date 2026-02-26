"""Tests for FastAPI run endpoints (MVP-3 Section 6.2.9/6.2.10).

Covers: POST create run, GET run results, POST batch runs, GET batch status.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.api.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _register_model_payload() -> dict:
    """Payload to register a simple 2-sector model via API."""
    return {
        "Z": [[150.0, 500.0], [200.0, 100.0]],
        "x": [1000.0, 2000.0],
        "sector_codes": ["S1", "S2"],
        "base_year": 2023,
        "source": "test",
    }


def _satellite_payload() -> dict:
    return {
        "jobs_coeff": [0.01, 0.005],
        "import_ratio": [0.30, 0.20],
        "va_ratio": [0.40, 0.55],
    }


# ===================================================================
# POST /v1/engine/models — register a model
# ===================================================================


class TestRegisterModelEndpoint:
    """Register model for use in runs."""

    @pytest.mark.anyio
    async def test_register_returns_201(self, client: AsyncClient) -> None:
        response = await client.post("/v1/engine/models", json=_register_model_payload())
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_register_returns_model_version_id(self, client: AsyncClient) -> None:
        response = await client.post("/v1/engine/models", json=_register_model_payload())
        data = response.json()
        assert "model_version_id" in data
        assert "checksum" in data
        assert data["sector_count"] == 2


# ===================================================================
# POST /v1/engine/runs — single run
# ===================================================================


class TestCreateRunEndpoint:
    """POST single run executes and returns results."""

    @pytest.mark.anyio
    async def test_run_returns_200(self, client: AsyncClient) -> None:
        # Register model first
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/runs", json=run_payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_run_returns_result_sets(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/runs", json=run_payload)
        data = response.json()
        assert "run_id" in data
        assert "result_sets" in data
        assert len(data["result_sets"]) >= 3

    @pytest.mark.anyio
    async def test_run_returns_snapshot(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/runs", json=run_payload)
        data = response.json()
        assert "snapshot" in data
        assert data["snapshot"]["model_version_id"] == model_version_id

    @pytest.mark.anyio
    async def test_run_nonexistent_model_returns_404(self, client: AsyncClient) -> None:
        run_payload = {
            "model_version_id": str(uuid7()),
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/runs", json=run_payload)
        assert response.status_code == 404


# ===================================================================
# GET /v1/engine/runs/{run_id} — get run results
# ===================================================================


class TestGetRunResultsEndpoint:
    """GET run results by run_id."""

    @pytest.mark.anyio
    async def test_get_run_returns_200(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        run_resp = await client.post("/v1/engine/runs", json={
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        })
        run_id = run_resp.json()["run_id"]

        response = await client.get(f"/v1/engine/runs/{run_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_get_nonexistent_run_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/engine/runs/{uuid7()}")
        assert response.status_code == 404


# ===================================================================
# POST /v1/engine/batch — batch runs
# ===================================================================


class TestBatchRunEndpoint:
    """POST batch runs multiple scenarios."""

    @pytest.mark.anyio
    async def test_batch_returns_200(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                {"name": "Base", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
                {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/batch", json=batch_payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_batch_returns_multiple_results(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post("/v1/engine/batch", json=batch_payload)
        data = response.json()
        assert "batch_id" in data
        assert len(data["results"]) == 2

    @pytest.mark.anyio
    async def test_batch_status_returns_200(self, client: AsyncClient) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Base", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        batch_resp = await client.post("/v1/engine/batch", json=batch_payload)
        batch_id = batch_resp.json()["batch_id"]

        response = await client.get(f"/v1/engine/batch/{batch_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_batch_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/engine/batch/{uuid7()}")
        assert response.status_code == 404
