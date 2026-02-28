"""Full pipeline integration tests — MVP-14.

End-to-end: register → run → feasibility → workforce → quality → export.
Tests all moat modules chaining together via real API calls.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

# ---------------------------------------------------------------------------
# Register → Run
# ---------------------------------------------------------------------------


class TestRegisterToRun:
    """Model registration and run execution via API."""

    @pytest.mark.anyio
    async def test_register_model_and_run(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Model + single run → 7 result sets."""
        result_sets = seeded_run["result_sets"]
        metric_types = {rs["metric_type"] for rs in result_sets}
        assert len(result_sets) == 7
        assert "total_output" in metric_types
        assert "direct_effect" in metric_types
        assert "indirect_effect" in metric_types

    @pytest.mark.anyio
    async def test_batch_run_two_scenarios(
        self,
        client: AsyncClient,
        seeded_batch: dict,
    ) -> None:
        """Batch → 2 runs × 7 result sets each."""
        assert len(seeded_batch["run_ids"]) == 2

    @pytest.mark.anyio
    async def test_run_results_retrievable(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """GET runs/{run_id} → returns results."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        resp = await client.get(
            f"/v1/workspaces/{ws_id}/engine/runs/{run_id}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == run_id
        assert len(data["result_sets"]) == 7


# ---------------------------------------------------------------------------
# Run → Feasibility
# ---------------------------------------------------------------------------


class TestRunToFeasibility:
    """Feasibility solver on unconstrained runs."""

    @pytest.mark.anyio
    async def test_feasibility_on_unconstrained_run(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Create CAPACITY_CAP constraint → solve → feasible ≤ bound for S1."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

        # Create constraint set with tight cap on S1
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "S1 cap",
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
            json={
                "constraint_set_id": cs_id,
                "unconstrained_run_id": run_id,
            },
        )
        assert solve_resp.status_code == 200
        data = solve_resp.json()
        assert data["feasible_delta_x"]["S1"] <= 40.0 + 1e-6

    @pytest.mark.anyio
    async def test_feasibility_gap_sign_convention(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """gap = unconstrained - feasible ≥ 0."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Gap test",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 30.0,
                        "unit": "SAR",
                        "confidence": "ESTIMATED",
                    },
                ],
            },
        )
        assert cs_resp.status_code == 201
        cs_id = cs_resp.json()["constraint_set_id"]

        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert solve_resp.status_code == 200
        data = solve_resp.json()

        # Gap = unconstrained - feasible >= 0 for all sectors
        for sc in ["S1", "S2"]:
            assert data["gap_vs_unconstrained"][sc] >= -1e-6

    @pytest.mark.anyio
    async def test_feasibility_binding_constraints(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Binding mask correct for tight CAPACITY_CAP."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Binding test",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 10.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = solve_resp.json()
        # Very tight cap should bind
        assert len(data["binding_constraints"]) >= 1


# ---------------------------------------------------------------------------
# Run → Workforce
# ---------------------------------------------------------------------------


class TestRunToWorkforce:
    """Workforce computation on runs."""

    @pytest.mark.anyio
    async def test_workforce_on_unconstrained_run(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Create emp coefficients → compute workforce → sector_employment populated."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

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
                        "source_description": "Test",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Test",
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
        assert "sector_employment" in data
        assert data["delta_x_source"] == "unconstrained"

    @pytest.mark.anyio
    async def test_workforce_on_feasible_run(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Run + feasibility → workforce with feasibility_result_id → delta_x_source=feasible."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

        # Create constraint set
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "WF Feasibility",
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
        cs_id = cs_resp.json()["constraint_set_id"]

        # Solve feasibility
        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        feas_id = solve_resp.json()["feasibility_result_id"]

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
                        "source_description": "Test",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Test",
                    },
                ],
            },
        )
        ec_id = ec_resp.json()["employment_coefficients_id"]

        # Compute workforce on feasible delta_x
        wf_resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/workforce",
            json={
                "employment_coefficients_id": ec_id,
                "feasibility_result_id": feas_id,
            },
        )
        assert wf_resp.status_code == 200
        data = wf_resp.json()
        assert data["delta_x_source"] == "feasible"
        assert data["feasibility_result_id"] == feas_id


# ---------------------------------------------------------------------------
# Run → Quality
# ---------------------------------------------------------------------------


class TestRunToQuality:
    """Data quality computation for runs."""

    @pytest.mark.anyio
    async def test_quality_summary_for_run(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """POST quality → returns score, grade, gate mode."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/quality",
            json={
                "base_table_year": 2020,
                "current_year": 2026,
                "coverage_pct": 0.9,
                "base_table_vintage": "Test IO Table",
                "inputs": [
                    {
                        "input_type": "mapping",
                        "input_data": {
                            "available_sectors": ["S1", "S2"],
                            "required_sectors": ["S1", "S2"],
                            "confidence_distribution": {"hard": 0.8, "estimated": 0.2},
                            "has_evidence_refs": True,
                            "source_description": "Integration test",
                        },
                    },
                ],
                "freshness_sources": [
                    {
                        "name": "IO Table",
                        "type": "io_table",
                        "last_updated": "2023-01-01T00:00:00Z",
                    },
                ],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "overall_run_score" in data
        assert "overall_run_grade" in data
        assert "publication_gate_mode" in data


# ---------------------------------------------------------------------------
# Full Chain
# ---------------------------------------------------------------------------


class TestFullChain:
    """Register → Run → Feasibility → Workforce → Quality → Export."""

    @pytest.mark.anyio
    async def test_register_run_feasibility_workforce_quality(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Single test: all modules chained → all IDs connected."""
        ws_id = seeded_run["ws_id"]
        mid = seeded_run["model_version_id"]
        run_id = seeded_run["run_id"]

        # Feasibility
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Full chain",
                "model_version_id": mid,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "S1",
                        "value": 50.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert solve_resp.status_code == 200
        feas_data = solve_resp.json()

        # Workforce
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
                        "source_description": "Test",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Test",
                    },
                ],
            },
        )
        ec_id = ec_resp.json()["employment_coefficients_id"]

        wf_resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/workforce",
            json={"employment_coefficients_id": ec_id},
        )
        assert wf_resp.status_code == 200

        # Quality
        q_resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/quality",
            json={
                "base_table_year": 2020,
                "current_year": 2026,
                "coverage_pct": 0.9,
                "base_table_vintage": "Test",
                "inputs": [
                    {
                        "input_type": "mapping",
                        "input_data": {
                            "available_sectors": ["S1", "S2"],
                            "required_sectors": ["S1", "S2"],
                            "confidence_distribution": {"hard": 0.8, "estimated": 0.2},
                            "has_evidence_refs": True,
                            "source_description": "Test",
                        },
                    },
                ],
                "freshness_sources": [
                    {
                        "name": "IO Table",
                        "type": "io_table",
                        "last_updated": "2023-01-01T00:00:00Z",
                    },
                ],
            },
        )
        assert q_resp.status_code == 201

        # Verify chain: all IDs present
        assert feas_data["unconstrained_run_id"] == run_id
        assert wf_resp.json()["run_id"] == run_id
        assert q_resp.json()["run_id"] == run_id

    @pytest.mark.anyio
    async def test_full_chain_with_sandbox_export(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Full chain + SANDBOX export → COMPLETED."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "SANDBOX",
                "export_formats": ["excel"],
                "pack_data": {"title": "Integration Test Export"},
            },
        )
        assert export_resp.status_code == 201
        assert export_resp.json()["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_full_chain_governed_export_passes(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """No claims → governed export → COMPLETED."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        export_resp = await client.post(
            f"/v1/workspaces/{ws_id}/exports",
            json={
                "run_id": run_id,
                "mode": "GOVERNED",
                "export_formats": ["excel"],
                "pack_data": {"title": "Governed Export"},
            },
        )
        assert export_resp.status_code == 201
        assert export_resp.json()["status"] == "COMPLETED"


# ---------------------------------------------------------------------------
# Cross-Module Data Flow
# ---------------------------------------------------------------------------


class TestCrossModuleDataFlow:
    """Verify cross-module data consistency."""

    @pytest.mark.anyio
    async def test_feasibility_uses_run_model_version(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Constraint set model_version must match run (422 on mismatch)."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        # Create constraint set with DIFFERENT model_version_id
        wrong_mid = str(uuid7())
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Wrong model",
                "model_version_id": wrong_mid,
                "constraints": [],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        # Solve should fail with 422
        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert solve_resp.status_code == 422

    @pytest.mark.anyio
    async def test_workforce_uses_run_model_version(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Emp coefficients model_version must match run (422 on mismatch)."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        # Create emp coefficients with wrong model_version
        wrong_mid = str(uuid7())
        ec_resp = await client.post(
            f"/v1/workspaces/{ws_id}/employment-coefficients",
            json={
                "model_version_id": wrong_mid,
                "output_unit": "MILLION_SAR",
                "base_year": 2023,
                "coefficients": [],
            },
        )
        ec_id = ec_resp.json()["employment_coefficients_id"]

        wf_resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/workforce",
            json={"employment_coefficients_id": ec_id},
        )
        assert wf_resp.status_code == 422

    @pytest.mark.anyio
    async def test_quality_independent_of_model(
        self,
        client: AsyncClient,
        seeded_run: dict,
    ) -> None:
        """Quality is run-scoped, not model-scoped — no model_version needed."""
        ws_id = seeded_run["ws_id"]
        run_id = seeded_run["run_id"]

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/quality",
            json={
                "base_table_year": 2020,
                "current_year": 2026,
                "coverage_pct": 0.8,
                "base_table_vintage": "Test",
                "inputs": [],
                "freshness_sources": [],
            },
        )
        assert resp.status_code == 201
        # Quality doesn't need model_version — it's run-scoped
        assert resp.json()["run_id"] == run_id
