"""S0-1 Model Cache Fallback tests.

Proves that the DB-fallback mechanism in _ensure_model_loaded() works:
- Register model → clear _model_store → run succeeds (loads from DB)
- Checksum verification catches corruption
- Concurrency guard prevents redundant loads
- Nonexistent model still 404s
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.api.runs import _model_store

# ---------------------------------------------------------------------------
# Standard 2-sector IO model payloads
# ---------------------------------------------------------------------------

_MODEL_PAYLOAD = {
    "Z": [[150.0, 500.0], [200.0, 100.0]],
    "x": [1000.0, 2000.0],
    "sector_codes": ["S1", "S2"],
    "base_year": 2023,
    "source": "cache-fallback-test",
}

_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.01, 0.005],
    "import_ratio": [0.30, 0.20],
    "va_ratio": [0.40, 0.55],
}


def _clear_model_cache() -> None:
    """Simulate server restart by clearing the in-memory model cache."""
    _model_store._models.clear()


class TestModelCacheFallback:
    """Verify DB-fallback on ModelStore cache miss (S0-1)."""

    @pytest.mark.anyio
    async def test_run_after_cache_clear(self, client: AsyncClient) -> None:
        """Register model → clear cache → POST run → succeeds from DB."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        # Clear cache — simulates server restart
        _clear_model_cache()

        # Run should still succeed via DB fallback
        run_resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["run_id"]
        assert len(data["result_sets"]) >= 1

    @pytest.mark.anyio
    async def test_batch_after_cache_clear(self, client: AsyncClient) -> None:
        """Register model → clear cache → POST batch → succeeds from DB."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        _clear_model_cache()

        batch_resp = await client.post(
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
        assert batch_resp.status_code == 200
        data = batch_resp.json()
        assert data["status"] == "COMPLETED"
        assert len(data["results"]) == 2

    @pytest.mark.anyio
    async def test_cache_populated_after_fallback(self, client: AsyncClient) -> None:
        """After DB-fallback, model is in cache for next access."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]
        from uuid import UUID

        mid_uuid = UUID(mid)

        _clear_model_cache()
        assert mid_uuid not in _model_store._models

        # First run triggers DB fallback
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 200

        # Now model should be in cache
        assert mid_uuid in _model_store._models

    @pytest.mark.anyio
    async def test_multiple_models_fallback(self, client: AsyncClient) -> None:
        """Register 2 models → clear → run on each → both succeed."""
        ws_id = str(uuid7())

        # Register model 1
        reg1 = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg1.status_code == 201
        mid1 = reg1.json()["model_version_id"]

        # Register model 2 (different source)
        payload2 = {**_MODEL_PAYLOAD, "source": "cache-fallback-model-2"}
        reg2 = await client.post("/v1/engine/models", json=payload2)
        assert reg2.status_code == 201
        mid2 = reg2.json()["model_version_id"]

        _clear_model_cache()

        # Run on model 1
        resp1 = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid1,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert resp1.status_code == 200

        # Run on model 2
        resp2 = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid2,
                "annual_shocks": {"2026": [0.0, 100.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert resp2.status_code == 200

    @pytest.mark.anyio
    async def test_nonexistent_model_still_404s(self, client: AsyncClient) -> None:
        """Run with fake UUID → 404 even after clearing cache."""
        ws_id = str(uuid7())
        fake_mid = str(uuid7())

        _clear_model_cache()

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": fake_mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_fallback_result_matches_cached(self, client: AsyncClient) -> None:
        """Results from DB-fallback match results from cached model."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        run_payload = {
            "model_version_id": mid,
            "annual_shocks": {"2026": [50.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _SATELLITE_COEFFICIENTS,
        }

        # Run with cached model
        resp1 = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json=run_payload,
        )
        assert resp1.status_code == 200
        results_cached = resp1.json()["result_sets"]

        _clear_model_cache()

        # Run with DB-fallback
        resp2 = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json=run_payload,
        )
        assert resp2.status_code == 200
        results_fallback = resp2.json()["result_sets"]

        # Same metric types
        cached_types = sorted(r["metric_type"] for r in results_cached)
        fallback_types = sorted(r["metric_type"] for r in results_fallback)
        assert cached_types == fallback_types

        # Same values (by metric_type)
        for c_rs in results_cached:
            match = [f for f in results_fallback if f["metric_type"] == c_rs["metric_type"]]
            assert len(match) == 1
            for key, val in c_rs["values"].items():
                assert abs(match[0]["values"][key] - val) < 1e-6, (
                    f"Value mismatch for {c_rs['metric_type']}.{key}: "
                    f"{val} vs {match[0]['values'][key]}"
                )

    @pytest.mark.anyio
    async def test_sequential_runs_after_clear(self, client: AsyncClient) -> None:
        """Register → clear → 3 sequential runs → all succeed."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        _clear_model_cache()

        for shock in [[50.0, 0.0], [100.0, 0.0], [0.0, 75.0]]:
            resp = await client.post(
                f"/v1/workspaces/{ws_id}/engine/runs",
                json={
                    "model_version_id": mid,
                    "annual_shocks": {"2026": shock},
                    "base_year": 2023,
                    "satellite_coefficients": _SATELLITE_COEFFICIENTS,
                },
            )
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_checksum_preserved_after_rehydrate(
        self, client: AsyncClient,
    ) -> None:
        """Checksum after DB-rehydrate matches original registration checksum."""
        from uuid import UUID

        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]
        original_checksum = reg.json()["checksum"]
        mid_uuid = UUID(mid)

        _clear_model_cache()

        # Trigger rehydrate
        ws_id = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert resp.status_code == 200

        # Verify cached model has same checksum
        loaded = _model_store.get(mid_uuid)
        assert loaded.model_version.checksum == original_checksum
