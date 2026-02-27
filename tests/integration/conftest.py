"""Shared fixtures for MVP-14 integration tests.

Provides:
- registered_model: 2-sector IO model registered via API
- seeded_run: Single run with results for a known shock
- seeded_batch: Batch run with 2 scenarios
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())

# ---------------------------------------------------------------------------
# Standard 2-sector IO model
# ---------------------------------------------------------------------------

_MODEL_PAYLOAD = {
    "Z": [[150.0, 500.0], [200.0, 100.0]],
    "x": [1000.0, 2000.0],
    "sector_codes": ["S1", "S2"],
    "base_year": 2023,
    "source": "integration-test",
}

_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.01, 0.005],
    "import_ratio": [0.30, 0.20],
    "va_ratio": [0.40, 0.55],
}


@pytest.fixture
async def registered_model(client: AsyncClient) -> dict:
    """Register a 2-sector IO model via POST /v1/engine/models.

    Returns dict with: model_version_id, ws_id, sector_codes.
    """
    resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
    assert resp.status_code == 201, f"Model registration failed: {resp.text}"
    data = resp.json()
    return {
        "model_version_id": data["model_version_id"],
        "ws_id": WS_ID,
        "sector_codes": ["S1", "S2"],
    }


@pytest.fixture
async def seeded_run(
    client: AsyncClient,
    registered_model: dict,
) -> dict:
    """Execute a single run with shock [50.0, 0.0] on the registered model.

    Returns dict with: run_id, model_version_id, ws_id, result_sets.
    """
    ws_id = registered_model["ws_id"]
    mid = registered_model["model_version_id"]

    resp = await client.post(
        f"/v1/workspaces/{ws_id}/engine/runs",
        json={
            "model_version_id": mid,
            "annual_shocks": {"2026": [50.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _SATELLITE_COEFFICIENTS,
        },
    )
    assert resp.status_code == 200, f"Run failed: {resp.text}"
    data = resp.json()
    return {
        "run_id": data["run_id"],
        "model_version_id": mid,
        "ws_id": ws_id,
        "result_sets": data["result_sets"],
    }


@pytest.fixture
async def seeded_batch(
    client: AsyncClient,
    registered_model: dict,
) -> dict:
    """Execute a batch run with Low + High scenarios.

    Returns dict with: batch_id, run_ids, ws_id, model_version_id.
    """
    ws_id = registered_model["ws_id"]
    mid = registered_model["model_version_id"]

    resp = await client.post(
        f"/v1/workspaces/{ws_id}/engine/batch",
        json={
            "model_version_id": mid,
            "scenarios": [
                {
                    "name": "Low",
                    "annual_shocks": {"2026": [50.0, 0.0]},
                    "base_year": 2023,
                },
                {
                    "name": "High",
                    "annual_shocks": {"2026": [200.0, 0.0]},
                    "base_year": 2023,
                },
            ],
            "satellite_coefficients": _SATELLITE_COEFFICIENTS,
        },
    )
    assert resp.status_code == 200, f"Batch failed: {resp.text}"
    data = resp.json()
    run_ids = [r["run_id"] for r in data["results"]]
    return {
        "batch_id": data["batch_id"],
        "run_ids": run_ids,
        "ws_id": ws_id,
        "model_version_id": mid,
    }
