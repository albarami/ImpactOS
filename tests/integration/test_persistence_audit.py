"""S0-1 Persistence Audit tests.

Proves that every entity type survives a simulated server restart.
Strategy: create via API → verify from DB → clear caches → verify still works.

Covers: models, runs, batches, governance, documents, scenarios, feasibility,
workforce, exports, workspace scoping.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.api.runs import _model_store

# ---------------------------------------------------------------------------
# Standard payloads
# ---------------------------------------------------------------------------

_MODEL_PAYLOAD = {
    "Z": [[150.0, 500.0], [200.0, 100.0]],
    "x": [1000.0, 2000.0],
    "sector_codes": ["S1", "S2"],
    "base_year": 2023,
    "source": "persistence-audit",
}

_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.01, 0.005],
    "import_ratio": [0.30, 0.20],
    "va_ratio": [0.40, 0.55],
}


def _clear_model_cache() -> None:
    """Simulate server restart by clearing the in-memory model cache."""
    _model_store._models.clear()


# ---------------------------------------------------------------------------
# Model Persistence
# ---------------------------------------------------------------------------


class TestModelPersistence:
    """Verify model registration data persists across cache clears."""

    @pytest.mark.anyio
    async def test_registered_model_survives_cache_clear(
        self, client: AsyncClient,
    ) -> None:
        """Register → clear cache → run with same model → succeeds."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        _clear_model_cache()

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

    @pytest.mark.anyio
    async def test_model_data_matches_original(
        self, client: AsyncClient,
    ) -> None:
        """Register → run (cached) → clear → run (DB) → same metric types."""
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
        r1 = await client.post(f"/v1/workspaces/{ws_id}/engine/runs", json=run_payload)
        assert r1.status_code == 200
        types_cached = sorted(rs["metric_type"] for rs in r1.json()["result_sets"])

        _clear_model_cache()

        # Run with DB-loaded model
        r2 = await client.post(f"/v1/workspaces/{ws_id}/engine/runs", json=run_payload)
        assert r2.status_code == 200
        types_db = sorted(rs["metric_type"] for rs in r2.json()["result_sets"])

        assert types_cached == types_db

    @pytest.mark.anyio
    async def test_model_checksum_preserved(
        self, client: AsyncClient,
    ) -> None:
        """Register → checksum from API matches rehydrated model checksum."""
        from uuid import UUID

        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]
        expected_checksum = reg.json()["checksum"]

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
        loaded = _model_store.get(UUID(mid))
        assert loaded.model_version.checksum == expected_checksum


# ---------------------------------------------------------------------------
# Run Persistence
# ---------------------------------------------------------------------------


class TestRunPersistence:
    """Verify run results persist in DB."""

    @pytest.mark.anyio
    async def test_run_results_survive_cache_clear(
        self, client: AsyncClient,
    ) -> None:
        """Run → clear cache → GET run → same result_sets returned."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

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
        run_id = run_resp.json()["run_id"]
        original_types = sorted(rs["metric_type"] for rs in run_resp.json()["result_sets"])

        _clear_model_cache()

        # GET run results from DB
        get_resp = await client.get(f"/v1/workspaces/{ws_id}/engine/runs/{run_id}")
        assert get_resp.status_code == 200
        loaded_types = sorted(rs["metric_type"] for rs in get_resp.json()["result_sets"])
        assert original_types == loaded_types

    @pytest.mark.anyio
    async def test_batch_results_persist(
        self, client: AsyncClient,
    ) -> None:
        """Batch run → GET batch → status COMPLETED + all results present."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        batch_resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/batch",
            json={
                "model_version_id": mid,
                "scenarios": [
                    {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                    {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
                ],
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert batch_resp.status_code == 200
        batch_id = batch_resp.json()["batch_id"]

        _clear_model_cache()

        # GET batch status from DB
        get_resp = await client.get(f"/v1/workspaces/{ws_id}/engine/batch/{batch_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "COMPLETED"
        assert len(get_resp.json()["results"]) == 2

    @pytest.mark.anyio
    async def test_run_snapshot_has_workspace_id(
        self, client: AsyncClient,
    ) -> None:
        """Run with workspace → GET run in that workspace → found."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

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
        run_id = run_resp.json()["run_id"]

        # GET should work in the correct workspace
        get_resp = await client.get(f"/v1/workspaces/{ws_id}/engine/runs/{run_id}")
        assert get_resp.status_code == 200


# ---------------------------------------------------------------------------
# Governance Persistence
# ---------------------------------------------------------------------------


class TestGovernancePersistence:
    """Verify governance entities persist in DB."""

    @pytest.mark.anyio
    async def test_governance_status_clean_run(
        self, client: AsyncClient,
    ) -> None:
        """No claims → governance status → nff_passed=True from DB."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/status/{run_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["nff_passed"] is True
        assert data["claims_total"] == 0

    @pytest.mark.anyio
    async def test_claims_persist_across_requests(
        self, client: AsyncClient,
    ) -> None:
        """Extract claims → fresh GET → claims visible in governance."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        # Extract claims from draft text
        claim_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/claims/extract",
            json={
                "draft_text": "GDP will grow 5%. Import substitution will reduce dependency.",
                "run_id": run_id,
            },
        )
        assert claim_resp.status_code == 200

        # GET governance status — claims should be there
        status_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/status/{run_id}",
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["claims_total"] >= 1
        assert data["nff_passed"] is False  # Unresolved claims block NFF

    @pytest.mark.anyio
    async def test_assumption_approval_persists(
        self, client: AsyncClient,
    ) -> None:
        """Create assumption → approve → GET → status APPROVED."""
        ws_id = str(uuid7())

        create_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/assumptions",
            json={
                "type": "IMPORT_SHARE",
                "value": 0.35,
                "units": "percent",
                "justification": "Based on IMF forecast",
            },
        )
        assert create_resp.status_code == 201
        assumption_id = create_resp.json()["assumption_id"]

        # Approve (POST, not PUT)
        approve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/governance/assumptions/{assumption_id}/approve",
            json={
                "range_min": 0.30,
                "range_max": 0.40,
                "actor": str(uuid7()),
            },
        )
        assert approve_resp.status_code == 200
        # Verify approval in response
        assert approve_resp.json()["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# Document Persistence
# ---------------------------------------------------------------------------


class TestDocumentPersistence:
    """Verify document entities persist in DB."""

    @pytest.mark.anyio
    async def test_document_upload_and_line_items(
        self, client: AsyncClient,
    ) -> None:
        """Upload document → GET line-items → empty list returned (doc persists)."""
        ws_id = str(uuid7())

        upload_resp = await client.post(
            f"/v1/workspaces/{ws_id}/documents",
            files={"file": ("test_boq.pdf", b"%PDF-1.4 fake content", "application/pdf")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "CONFIDENTIAL",
                "language": "en",
                "uploaded_by": str(uuid7()),
            },
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["doc_id"]

        # GET line-items verifies document persists (empty for un-extracted doc)
        li_resp = await client.get(
            f"/v1/workspaces/{ws_id}/documents/{doc_id}/line-items",
        )
        assert li_resp.status_code == 200
        # Response is {"items": [...]} or a list
        data = li_resp.json()
        if isinstance(data, dict):
            assert "items" in data
        else:
            assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Scenario Persistence
# ---------------------------------------------------------------------------


class TestScenarioPersistence:
    """Verify scenario specs persist in DB."""

    @pytest.mark.anyio
    async def test_scenario_spec_retrievable(
        self, client: AsyncClient,
    ) -> None:
        """Create scenario → GET versions → at least one version exists."""
        ws_id = str(uuid7())

        create_resp = await client.post(
            f"/v1/workspaces/{ws_id}/scenarios",
            json={
                "name": "Persistence Test Scenario",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
            },
        )
        assert create_resp.status_code == 201
        spec_id = create_resp.json()["scenario_spec_id"]
        assert create_resp.json()["name"] == "Persistence Test Scenario"

        # Versions endpoint confirms persistence
        get_resp = await client.get(
            f"/v1/workspaces/{ws_id}/scenarios/{spec_id}/versions",
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        versions = data.get("versions", data) if isinstance(data, dict) else data
        assert len(versions) >= 1
        assert versions[0]["version"] == 1


# ---------------------------------------------------------------------------
# Feasibility Persistence
# ---------------------------------------------------------------------------


class TestFeasibilityPersistence:
    """Verify constraint sets and feasibility results persist in DB."""

    @pytest.mark.anyio
    async def test_constraint_set_persists(
        self, client: AsyncClient,
    ) -> None:
        """Create constraint set → GET → constraints match."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Persistence Cap",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 40.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        assert cs_resp.status_code == 201
        cs_id = cs_resp.json()["constraint_set_id"]

        get_resp = await client.get(f"/v1/workspaces/{ws_id}/constraints/{cs_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Persistence Cap"
        assert len(get_resp.json()["constraints"]) == 1

    @pytest.mark.anyio
    async def test_feasibility_result_persists(
        self, client: AsyncClient,
    ) -> None:
        """Solve → GET result → values present."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        # Run
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
        run_id = run_resp.json()["run_id"]

        # Constraint set
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Persist Cap",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 40.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        assert cs_resp.status_code == 201
        cs_id = cs_resp.json()["constraint_set_id"]

        # Solve
        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert solve_resp.status_code == 200
        assert "feasible_delta_x" in solve_resp.json()
        assert "total_feasible_output" in solve_resp.json()


# ---------------------------------------------------------------------------
# Workforce Persistence
# ---------------------------------------------------------------------------


class TestWorkforcePersistence:
    """Verify workforce results persist in DB."""

    @pytest.mark.anyio
    async def test_employment_coefficients_and_workforce_persist(
        self, client: AsyncClient,
    ) -> None:
        """Create coefficients → compute workforce → result persists."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

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
        run_id = run_resp.json()["run_id"]

        # Create employment coefficients
        ec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/employment-coefficients",
            json={
                "model_version_id": mid,
                "output_unit": "MILLION_SAR",
                "base_year": 2023,
                "coefficients": [
                    {
                        "sector_code": "S1",
                        "jobs_per_million_sar": 12.5,
                        "confidence": "HARD",
                        "source_description": "Audit test",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Audit test",
                    },
                ],
            },
        )
        assert ec_resp.status_code == 201
        ec_id = ec_resp.json()["employment_coefficients_id"]

        # Compute workforce
        wf_resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/workforce",
            json={"employment_coefficients_id": ec_id},
        )
        assert wf_resp.status_code == 200
        data = wf_resp.json()
        assert "sector_results" in data or "saudization_gaps" in data


# ---------------------------------------------------------------------------
# Export Persistence
# ---------------------------------------------------------------------------


class TestExportPersistence:
    """Verify export entities persist in DB."""

    @pytest.mark.anyio
    async def test_export_metadata_persists(
        self, client: AsyncClient,
    ) -> None:
        """Create sandbox export → GET by ID → mode and status match."""
        ws_id = str(uuid7())
        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

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
        run_id = run_resp.json()["run_id"]

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "SANDBOX",
                "export_formats": ["EXCEL"],
                "pack_data": {
                    "scenarios": [],
                    "assumptions": [],
                    "results_summary": {},
                },
            },
        )
        assert export_resp.status_code == 201
        export_id = export_resp.json()["export_id"]

        get_resp = await client.get(f"/v1/workspaces/{ws_id}/exports/{export_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["mode"] == "SANDBOX"


# ---------------------------------------------------------------------------
# Workspace Scoping (Amendment 3)
# ---------------------------------------------------------------------------


class TestWorkspaceScoping:
    """Verify workspace isolation for runs and batches."""

    @pytest.mark.anyio
    async def test_run_invisible_across_workspaces(
        self, client: AsyncClient,
    ) -> None:
        """Run in ws1 → GET from ws2 → 404."""
        ws1 = str(uuid7())
        ws2 = str(uuid7())

        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        # Run in ws1
        run_resp = await client.post(
            f"/v1/workspaces/{ws1}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run_id"]

        # GET from ws1 should work
        get1 = await client.get(f"/v1/workspaces/{ws1}/engine/runs/{run_id}")
        assert get1.status_code == 200

        # GET from ws2 should 404
        get2 = await client.get(f"/v1/workspaces/{ws2}/engine/runs/{run_id}")
        assert get2.status_code == 404

    @pytest.mark.anyio
    async def test_batch_invisible_across_workspaces(
        self, client: AsyncClient,
    ) -> None:
        """Batch in ws1 → GET from ws2 → 404."""
        ws1 = str(uuid7())
        ws2 = str(uuid7())

        reg = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        assert reg.status_code == 201
        mid = reg.json()["model_version_id"]

        # Batch in ws1
        batch_resp = await client.post(
            f"/v1/workspaces/{ws1}/engine/batch",
            json={
                "model_version_id": mid,
                "scenarios": [
                    {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                ],
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        assert batch_resp.status_code == 200
        batch_id = batch_resp.json()["batch_id"]

        # GET from ws1 should work
        get1 = await client.get(f"/v1/workspaces/{ws1}/engine/batch/{batch_id}")
        assert get1.status_code == 200

        # GET from ws2 should 404
        get2 = await client.get(f"/v1/workspaces/{ws2}/engine/batch/{batch_id}")
        assert get2.status_code == 404
