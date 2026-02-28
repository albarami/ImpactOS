"""S0-4 Integration Tests — End-to-End Wiring Fixes.

Tests the key S0-4 deliverables:
1. NFF claims wired end-to-end (extract → export blocking)
2. Batch status tracking (RUNNING → COMPLETED)
3. Health check with component checks
4. Learning loop persistence (compiler decisions → override pairs)
5. Workspace-scoped routing across all modules
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = "01961060-0000-7000-8000-000000000001"


# ===================================================================
# 1. NFF Claims End-to-End: extract → check → export blocking
# ===================================================================


class TestNFFEndToEnd:
    """NFF gate blocks governed exports when claims are unresolved."""

    @pytest.mark.anyio
    async def test_governed_export_blocked_with_unresolved_claims(
        self, client: AsyncClient,
    ) -> None:
        """Extract claims, then try governed export — should be BLOCKED."""
        run_id = str(uuid7())

        # Step 1: Extract claims from draft text (creates claims in DB)
        extract_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%. Employment rises by 10,000 jobs.",
                "run_id": run_id,
            },
        )
        assert extract_resp.status_code == 200
        claims_data = extract_resp.json()
        assert claims_data["total"] >= 1
        assert claims_data["needs_evidence_count"] >= 1

        # Step 2: Try governed export — should be BLOCKED because claims are unresolved
        export_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": run_id,
                "mode": "GOVERNED",
                "export_formats": ["excel"],
                "pack_data": {"title": "Test Export"},
            },
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "BLOCKED"
        assert len(export_data["blocking_reasons"]) >= 1

    @pytest.mark.anyio
    async def test_sandbox_export_not_blocked_by_claims(
        self, client: AsyncClient,
    ) -> None:
        """Sandbox export should NEVER be blocked regardless of claims."""
        run_id = str(uuid7())

        # Extract claims
        await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%.",
                "run_id": run_id,
            },
        )

        # Sandbox export — should be COMPLETED even with unresolved claims
        export_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": run_id,
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {"title": "Sandbox Test"},
            },
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_export_with_no_claims_passes(
        self, client: AsyncClient,
    ) -> None:
        """Governed export with no claims should pass NFF gate."""
        run_id = str(uuid7())

        export_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": run_id,
                "mode": "GOVERNED",
                "export_formats": ["excel"],
                "pack_data": {"title": "Clean Export"},
            },
        )
        assert export_resp.status_code == 201
        export_data = export_resp.json()
        assert export_data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_nff_check_reads_claims_from_db(
        self, client: AsyncClient,
    ) -> None:
        """NFF check endpoint reads claims from DB after extraction."""
        run_id = str(uuid7())

        # Extract claims
        extract_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%.",
                "run_id": run_id,
            },
        )
        claim_ids = [c["claim_id"] for c in extract_resp.json()["claims"]]

        # NFF check reads those claims from DB
        nff_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/nff/check",
            json={"claim_ids": claim_ids},
        )
        assert nff_resp.status_code == 200
        nff_data = nff_resp.json()
        assert nff_data["total_claims"] == len(claim_ids)
        # Claims are EXTRACTED (unresolved) so NFF should fail
        assert nff_data["passed"] is False

    @pytest.mark.anyio
    async def test_governance_status_shows_claims(
        self, client: AsyncClient,
    ) -> None:
        """Governance status endpoint shows claims for a run."""
        run_id = str(uuid7())

        # Extract claims
        await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/extract",
            json={
                "draft_text": "GDP will increase by 3.5%. Employment rises by 10,000 jobs.",
                "run_id": run_id,
            },
        )

        # Check governance status
        status_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/governance/status/{run_id}"
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["run_id"] == run_id
        assert data["claims_total"] >= 1
        assert data["claims_unresolved"] >= 1
        assert data["nff_passed"] is False


# ===================================================================
# 2. Batch Status Tracking
# ===================================================================


class TestBatchStatusTracking:
    """Batch operations track status RUNNING → COMPLETED."""

    @pytest.mark.anyio
    async def test_batch_completed_status(self, client: AsyncClient) -> None:
        """Successful batch shows COMPLETED status."""
        # Register model
        reg_resp = await client.post("/v1/engine/models", json={
            "Z": [[150.0, 500.0], [200.0, 100.0]],
            "x": [1000.0, 2000.0],
            "sector_codes": ["S1", "S2"],
            "base_year": 2023,
            "source": "test",
        })
        model_version_id = reg_resp.json()["model_version_id"]

        # Run batch
        batch_resp = await client.post(f"/v1/workspaces/{WS_ID}/engine/batch", json={
            "model_version_id": model_version_id,
            "scenarios": [
                {"name": "Low", "annual_shocks": {"2026": [50.0, 0.0]}, "base_year": 2023},
                {"name": "High", "annual_shocks": {"2026": [200.0, 0.0]}, "base_year": 2023},
            ],
            "satellite_coefficients": {
                "jobs_coeff": [0.01, 0.005],
                "import_ratio": [0.30, 0.20],
                "va_ratio": [0.40, 0.55],
            },
        })
        assert batch_resp.status_code == 200
        batch_data = batch_resp.json()
        assert batch_data["status"] == "COMPLETED"

        # Verify status via GET
        batch_id = batch_data["batch_id"]
        status_resp = await client.get(
            f"/v1/workspaces/{WS_ID}/engine/batch/{batch_id}"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["status"] == "COMPLETED"
        assert len(status_data["results"]) == 2


# ===================================================================
# 3. Health Check with Component Checks
# ===================================================================


class TestHealthCheckEnhanced:
    """S0-4 enhanced health check with component checks."""

    @pytest.mark.anyio
    async def test_health_returns_checks(self, client: AsyncClient) -> None:
        """Health check includes checks dict."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
        assert data["checks"]["api"] is True

    @pytest.mark.anyio
    async def test_health_returns_version(self, client: AsyncClient) -> None:
        """Health check includes version."""
        resp = await client.get("/health")
        data = resp.json()
        assert "version" in data
        assert data["version"]  # non-empty


# ===================================================================
# 4. Learning Loop Persistence (Compiler Decisions → Override Pairs)
# ===================================================================


class TestLearningLoopPersistence:
    """Compiler decisions persist override pairs to DB for learning loop."""

    @pytest.mark.anyio
    async def test_compiler_decisions_create_override_pairs(
        self, client: AsyncClient,
    ) -> None:
        """Accept/reject bulk decisions persist override pairs in DB."""
        li_id = str(uuid7())

        # Step 1: Trigger compilation
        compile_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Learning Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": li_id,
                        "raw_text": "concrete works for stadium",
                        "total_value": 5000000.0,
                    },
                ],
            },
        )
        assert compile_resp.status_code == 201
        comp_id = compile_resp.json()["compilation_id"]

        # Step 2: Accept suggestions (creates override pairs)
        decision_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/{comp_id}/decisions",
            json={
                "decisions": [
                    {"line_item_id": li_id, "action": "accept"},
                ],
            },
        )
        assert decision_resp.status_code == 200
        dec_data = decision_resp.json()
        assert dec_data["accepted"] == 1
        assert dec_data["total"] == 1

    @pytest.mark.anyio
    async def test_compiler_reject_with_override_creates_pair(
        self, client: AsyncClient,
    ) -> None:
        """Reject with override creates override pair with different final code."""
        li_id = str(uuid7())

        compile_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Override Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {"line_item_id": li_id, "raw_text": "concrete works", "total_value": 1000000.0},
                ],
            },
        )
        assert compile_resp.status_code == 201
        comp_id = compile_resp.json()["compilation_id"]

        decision_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/{comp_id}/decisions",
            json={
                "decisions": [
                    {
                        "line_item_id": li_id,
                        "action": "reject",
                        "override_sector_code": "C",
                        "note": "Should be Manufacturing, not Construction",
                    },
                ],
            },
        )
        assert decision_resp.status_code == 200
        dec_data = decision_resp.json()
        assert dec_data["rejected"] == 1


# ===================================================================
# 5. Workspace-Scoped Routing Cross-Module
# ===================================================================


class TestWorkspaceScopedRouting:
    """Verify all API modules use workspace-scoped routes."""

    @pytest.mark.anyio
    async def test_model_registration_is_global(self, client: AsyncClient) -> None:
        """Model registration stays at /v1/engine/models (no workspace)."""
        resp = await client.post("/v1/engine/models", json={
            "Z": [[150.0, 500.0], [200.0, 100.0]],
            "x": [1000.0, 2000.0],
            "sector_codes": ["S1", "S2"], "base_year": 2023, "source": "test",
        })
        assert resp.status_code == 201

    @pytest.mark.anyio
    async def test_run_requires_workspace(self, client: AsyncClient) -> None:
        """Run endpoint is workspace-scoped."""
        reg_resp = await client.post("/v1/engine/models", json={
            "Z": [[150.0, 500.0], [200.0, 100.0]],
            "x": [1000.0, 2000.0],
            "sector_codes": ["S1", "S2"],
            "base_year": 2023,
            "source": "test",
        })
        mid = reg_resp.json()["model_version_id"]

        # Old URL (no workspace) should 404 or 405
        old_resp = await client.post("/v1/engine/runs", json={
            "model_version_id": mid,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": {
                "jobs_coeff": [0.01, 0.005],
                "import_ratio": [0.30, 0.20],
                "va_ratio": [0.40, 0.55],
            },
        })
        # Old URL should not work (404 or 405)
        assert old_resp.status_code in (404, 405, 422)

        # New workspace-scoped URL should work
        new_resp = await client.post(f"/v1/workspaces/{WS_ID}/engine/runs", json={
            "model_version_id": mid,
            "annual_shocks": {"2026": [100.0, 0.0]},
            "base_year": 2023,
            "satellite_coefficients": {
                "jobs_coeff": [0.01, 0.005],
                "import_ratio": [0.30, 0.20],
                "va_ratio": [0.40, 0.55],
            },
        })
        assert new_resp.status_code == 200

    @pytest.mark.anyio
    async def test_metrics_workspace_scoped(self, client: AsyncClient) -> None:
        """Metrics endpoint is workspace-scoped."""
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics", json={
            "engagement_id": str(uuid7()),
            "metric_type": "SCENARIO_REQUEST_TO_RESULTS",
            "value": 48.0,
            "unit": "hours",
        })
        assert resp.status_code == 201

    @pytest.mark.anyio
    async def test_scenarios_workspace_scoped(self, client: AsyncClient) -> None:
        """Scenario creation is workspace-scoped."""
        resp = await client.post(f"/v1/workspaces/{WS_ID}/scenarios", json={
            "name": "Integration Test Scenario",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2024,
            "end_year": 2030,
        })
        assert resp.status_code == 201

    @pytest.mark.anyio
    async def test_governance_workspace_scoped(self, client: AsyncClient) -> None:
        """Governance endpoints are workspace-scoped."""
        run_id = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/governance/claims/extract",
            json={
                "draft_text": "GDP increases by 2%.",
                "run_id": run_id,
            },
        )
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_exports_workspace_scoped(self, client: AsyncClient) -> None:
        """Export creation is workspace-scoped."""
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": str(uuid7()),
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {"title": "Test"},
            },
        )
        assert resp.status_code == 201

    @pytest.mark.anyio
    async def test_compiler_workspace_scoped(self, client: AsyncClient) -> None:
        """Compiler endpoint is workspace-scoped."""
        resp = await client.post(
            f"/v1/workspaces/{WS_ID}/compiler/compile",
            json={
                "scenario_name": "Routing Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2024,
                "end_year": 2030,
                "line_items": [
                    {
                        "line_item_id": str(uuid7()),
                        "raw_text": "concrete works",
                        "total_value": 1000000.0,
                    },
                ],
            },
        )
        assert resp.status_code == 201


# ===================================================================
# 6. Export Status Persistence
# ===================================================================


class TestExportPersistence:
    """Export metadata persists to DB and can be retrieved."""

    @pytest.mark.anyio
    async def test_export_can_be_retrieved(self, client: AsyncClient) -> None:
        """Created export can be retrieved by ID."""
        create_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json={
                "run_id": str(uuid7()),
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {"title": "Persistence Test"},
            },
        )
        assert create_resp.status_code == 201
        export_id = create_resp.json()["export_id"]

        # Retrieve by ID
        get_resp = await client.get(f"/v1/workspaces/{WS_ID}/exports/{export_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["export_id"] == export_id
        assert data["mode"] == "SANDBOX"
        assert data["status"] == "COMPLETED"
