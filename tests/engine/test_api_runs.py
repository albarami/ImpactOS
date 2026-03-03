"""Tests for FastAPI run endpoints (MVP-3 Section 6.2.9/6.2.10).

Covers: POST create run, GET run results, POST batch runs, GET batch status.

S0-4: Model registration stays global at /v1/engine/models.
Runs/batch are workspace-scoped under /v1/workspaces/{workspace_id}/engine/...
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.tables import ModelVersionRow

WS_ID = "01961060-0000-7000-8000-000000000001"


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


async def _promote_model(db_session: AsyncSession, model_version_id: str) -> None:
    """Promote API-registered model to curated_real so run endpoints accept it."""
    await db_session.execute(
        update(ModelVersionRow)
        .where(ModelVersionRow.model_version_id == UUID(model_version_id))
        .values(provenance_class="curated_real")
    )
    await db_session.flush()


# ===================================================================
# POST /v1/engine/models — register a model (global, not workspace-scoped)
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
# POST /v1/workspaces/{workspace_id}/engine/runs — single run
# ===================================================================


class TestCreateRunEndpoint:
    """POST single run executes and returns results."""

    @pytest.mark.anyio
    async def test_run_returns_200(self, client: AsyncClient, db_session: AsyncSession) -> None:
        # Register model first (global endpoint)
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json=run_payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_run_returns_result_sets(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json=run_payload)
        data = response.json()
        assert "run_id" in data
        assert "result_sets" in data
        assert len(data["result_sets"]) >= 3

    @pytest.mark.anyio
    async def test_run_returns_snapshot(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        run_payload = {
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json=run_payload)
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
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json=run_payload)
        assert response.status_code == 404


# ===================================================================
# GET /v1/workspaces/{workspace_id}/engine/runs/{run_id} — get run results
# ===================================================================


class TestGetRunResultsEndpoint:
    """GET run results by run_id."""

    @pytest.mark.anyio
    async def test_get_run_returns_200(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        run_resp = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json={
            "model_version_id": model_version_id,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": _satellite_payload(),
        })
        run_id = run_resp.json()["run_id"]

        response = await client.get(f"/v1/workspaces/{WS_ID}/engine/runs/{run_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_get_nonexistent_run_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/engine/runs/{uuid7()}")
        assert response.status_code == 404


# ===================================================================
# POST /v1/workspaces/{workspace_id}/engine/batch — batch runs
# ===================================================================


class TestBatchRunEndpoint:
    """POST batch runs multiple scenarios."""

    @pytest.mark.anyio
    async def test_batch_returns_200(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                {"name": "Base", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
                {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/batch", json=batch_payload)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_batch_returns_multiple_results(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/batch", json=batch_payload)
        data = response.json()
        assert "batch_id" in data
        assert len(data["results"]) == 2

    @pytest.mark.anyio
    async def test_batch_returns_completed_status(self, client: AsyncClient, db_session: AsyncSession) -> None:
        """S0-4: Batch response includes status field."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Base", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        response = await client.post(f"/v1/workspaces/{WS_ID}/engine/batch", json=batch_payload)
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_batch_status_returns_200(self, client: AsyncClient, db_session: AsyncSession) -> None:
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        model_version_id = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, model_version_id)

        batch_payload = {
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Base", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": _satellite_payload(),
        }
        batch_resp = await client.post(f"/v1/workspaces/{WS_ID}/engine/batch", json=batch_payload)
        batch_id = batch_resp.json()["batch_id"]

        response = await client.get(f"/v1/workspaces/{WS_ID}/engine/batch/{batch_id}")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_batch_nonexistent_returns_404(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/engine/batch/{uuid7()}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Sprint 16: Value Measures API tests
# ---------------------------------------------------------------------------


def _register_model_with_vm_payload() -> dict:
    """Model payload with all value-measures artifacts."""
    return {
        "Z": [[100.0, 50.0, 30.0], [80.0, 200.0, 60.0], [40.0, 100.0, 150.0]],
        "x": [1000.0, 2000.0, 1500.0],
        "sector_codes": ["F", "C", "G"],
        "base_year": 2024,
        "source": "test-vm-api",
        "gross_operating_surplus": [200.0, 500.0, 300.0],
        "taxes_less_subsidies": [50.0, 80.0, 45.0],
        "final_demand_F": [[150, 60, 200, 90], [400, 120, 300, 180], [300, 80, 100, 120]],
        "imports_vector": [300.0, 500.0, 225.0],
        "deflator_series": {"2024": 1.0, "2025": 1.03},
    }


def _satellite_payload_3() -> dict:
    return {
        "jobs_coeff": [0.008, 0.004, 0.006],
        "import_ratio": [0.30, 0.25, 0.15],
        "va_ratio": [0.35, 0.45, 0.55],
    }


class TestValueMeasuresEndpoint:
    """API returns value-measures metrics when prerequisites are present."""

    @pytest.mark.anyio
    async def test_run_returns_value_measures_metrics(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        # Register model with VM artifacts
        reg_resp = await client.post(
            "/v1/engine/models", json=_register_model_with_vm_payload(),
        )
        assert reg_resp.status_code == 201
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2025": [100.0, 50.0, 25.0]},
                "base_year": 2024,
                "satellite_coefficients": _satellite_payload_3(),
                "deflators": {"2025": "1.03"},
            },
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        metric_types = {rs["metric_type"] for rs in data["result_sets"]}
        assert "gdp_basic_price" in metric_types
        assert "gdp_market_price" in metric_types
        assert "balance_of_trade" in metric_types

    @pytest.mark.anyio
    async def test_run_without_vm_returns_base_metrics_only(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        # Register model WITHOUT VM artifacts
        reg_resp = await client.post(
            "/v1/engine/models", json=_register_model_payload(),
        )
        assert reg_resp.status_code == 201
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2025": [100.0, 50.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        metric_types = {rs["metric_type"] for rs in data["result_sets"]}
        assert "gdp_basic_price" not in metric_types
        # But base metrics still present
        assert "total_output" in metric_types

    @pytest.mark.anyio
    async def test_confidence_class_in_response(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Value-measures metrics include confidence_class in response."""
        reg_resp = await client.post(
            "/v1/engine/models", json=_register_model_with_vm_payload(),
        )
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2025": [100.0, 50.0, 25.0]},
                "base_year": 2024,
                "satellite_coefficients": _satellite_payload_3(),
                "deflators": {"2025": "1.03"},
            },
        )
        data = run_resp.json()
        for rs in data["result_sets"]:
            assert "confidence_class" in rs
            if rs["metric_type"] in ("gdp_market_price", "balance_of_trade"):
                assert rs["confidence_class"] == "ESTIMATED"
            elif rs["metric_type"] in ("total_output", "employment"):
                assert rs["confidence_class"] == "COMPUTED"


# ===================================================================
# Sprint 17: RunSeries API exposure
# ===================================================================


class TestRunSeriesAPI:
    """Sprint 17 Task 6: RunSeries fields exposed via API."""

    @pytest.mark.anyio
    async def test_post_response_excludes_series_by_default(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """POST response (create_run) returns only legacy rows by default."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        # All result_sets should have series_kind=None (absent or null)
        for rs in data["result_sets"]:
            assert rs.get("series_kind") is None, (
                f"POST response should exclude series rows by default, "
                f"but found series_kind={rs.get('series_kind')} for {rs['metric_type']}"
            )

    @pytest.mark.anyio
    async def test_default_get_excludes_series_rows(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Default GET returns only legacy (series_kind=None) rows."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        run_id = run_resp.json()["run_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/runs/{run_id}",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        for rs in data["result_sets"]:
            assert rs.get("series_kind") is None, (
                f"Default GET should exclude series rows, "
                f"but found series_kind={rs.get('series_kind')}"
            )

    @pytest.mark.anyio
    async def test_include_series_returns_all_rows(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """GET with ?include_series=true returns annual + peak rows too."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        run_id = run_resp.json()["run_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/runs/{run_id}?include_series=true",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        series_kinds = {rs.get("series_kind") for rs in data["result_sets"]}
        assert "annual" in series_kinds, (
            "include_series=true should return annual rows"
        )
        assert "peak" in series_kinds, (
            "include_series=true should return peak rows"
        )

    @pytest.mark.anyio
    async def test_series_fields_in_response(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """ResultSetResponse includes year and series_kind fields."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        run_id = run_resp.json()["run_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/runs/{run_id}?include_series=true",
        )
        data = get_resp.json()
        annual_rows = [
            rs for rs in data["result_sets"]
            if rs.get("series_kind") == "annual"
        ]
        assert len(annual_rows) > 0
        for rs in annual_rows:
            assert rs["year"] is not None, "Annual rows must have year set"
            assert rs["series_kind"] == "annual"

    @pytest.mark.anyio
    async def test_baseline_not_found_returns_error(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Invalid baseline_run_id returns 404 with reason code."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        run_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
                "baseline_run_id": str(uuid7()),
            },
        )
        assert run_resp.status_code == 404
        data = run_resp.json()
        assert data["detail"]["reason_code"] == "RS_BASELINE_NOT_FOUND"

    @pytest.mark.anyio
    async def test_batch_get_default_excludes_series(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """GET batch status default excludes series rows."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        batch_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/batch",
            json={
                "model_version_id": mvid,
                "scenarios": [
                    {"name": "A", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
                ],
                "satellite_coefficients": _satellite_payload(),
            },
        )
        batch_id = batch_resp.json()["batch_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/batch/{batch_id}",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        for run in data["results"]:
            for rs in run["result_sets"]:
                assert rs.get("series_kind") is None

    @pytest.mark.anyio
    async def test_batch_get_include_series(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """GET batch status with include_series=true returns series rows."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        batch_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/batch",
            json={
                "model_version_id": mvid,
                "scenarios": [
                    {"name": "A", "annual_shocks": {"2026": [100.0, 0.0]}, "base_year": 2023},
                ],
                "satellite_coefficients": _satellite_payload(),
            },
        )
        batch_id = batch_resp.json()["batch_id"]

        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/batch/{batch_id}?include_series=true",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        all_series_kinds = set()
        for run in data["results"]:
            for rs in run["result_sets"]:
                all_series_kinds.add(rs.get("series_kind"))
        assert "annual" in all_series_kinds
        assert "peak" in all_series_kinds

    @pytest.mark.anyio
    async def test_delta_confidence_class_estimated(
        self, client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        """Delta series rows should have confidence_class=ESTIMATED."""
        reg_resp = await client.post("/v1/engine/models", json=_register_model_payload())
        mvid = reg_resp.json()["model_version_id"]
        await _promote_model(db_session, mvid)

        # Create baseline run
        baseline_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
            },
        )
        baseline_id = baseline_resp.json()["run_id"]

        # Create scenario run with baseline
        scenario_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/engine/runs",
            json={
                "model_version_id": mvid,
                "annual_shocks": {"2026": [100.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _satellite_payload(),
                "baseline_run_id": baseline_id,
            },
        )
        assert scenario_resp.status_code == 200
        run_id = scenario_resp.json()["run_id"]

        # GET with include_series to see delta rows
        get_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/runs/{run_id}?include_series=true",
        )
        data = get_resp.json()
        delta_rows = [rs for rs in data["result_sets"] if rs.get("series_kind") == "delta"]
        assert len(delta_rows) > 0, "Should have delta rows when baseline provided"
        for rs in delta_rows:
            assert rs["confidence_class"] == "ESTIMATED"
            assert rs["baseline_run_id"] == baseline_id
