"""Phase 2 Gate verification tests — MVP-14.

Section 15.5.2 gate checks: compiler, feasibility, workforce, governance, quality.
Each test verifies a Phase 2 module's integration contract.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

_MODEL_PAYLOAD = {
    "Z": [[150.0, 500.0], [200.0, 100.0]],
    "x": [1000.0, 2000.0],
    "sector_codes": ["S1", "S2"],
    "base_year": 2023,
    "source": "phase2-gate",
}

_SATELLITE_COEFFICIENTS = {
    "jobs_coeff": [0.01, 0.005],
    "import_ratio": [0.30, 0.20],
    "va_ratio": [0.40, 0.55],
}


class TestPhase2Gate:
    """Phase 2 Gate verification from spec Section 15.5.2."""

    @pytest.mark.anyio
    async def test_compiler_produces_suggestions(
        self,
        client: AsyncClient,
    ) -> None:
        """Compile returns mapping suggestions with confidence breakdown."""
        ws_id = str(uuid7())
        li_id = str(uuid7())

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/compiler/compile",
            json={
                "scenario_name": "Gate Test",
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
        assert resp.status_code == 201
        data = resp.json()
        assert "compilation_id" in data
        assert len(data["suggestions"]) >= 1
        # Confidence breakdown fields exist
        assert "high_confidence" in data
        assert "medium_confidence" in data
        assert "low_confidence" in data

    @pytest.mark.anyio
    async def test_feasibility_consistent_with_without(
        self,
        client: AsyncClient,
    ) -> None:
        """Feasible delta_x ≤ unconstrained delta_x per sector."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        # Unconstrained run
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

        # Constraint set — tight cap on S1
        cs_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints",
            json={
                "name": "Gate Cap",
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

        # Feasibility solve
        solve_resp = await client.post(
            f"/v1/workspaces/{ws_id}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert solve_resp.status_code == 200
        feasible = solve_resp.json()

        # Per-sector: feasible ≤ unconstrained (dict: sector_code → float)
        feasible_dx = feasible["feasible_delta_x"]
        unconstrained_dx = feasible["unconstrained_delta_x"]
        for sector in feasible_dx:
            f_val = feasible_dx[sector]
            u_val = unconstrained_dx[sector]
            assert f_val <= u_val + 1e-6, (
                f"Feasible {f_val} > unconstrained {u_val} for {sector}"
            )

        # Total feasible ≤ total unconstrained
        assert feasible["total_feasible_output"] <= feasible["total_unconstrained_output"] + 1e-6

    @pytest.mark.anyio
    async def test_workforce_produces_saudization_metrics(
        self,
        client: AsyncClient,
    ) -> None:
        """Workforce result has saudization_gaps dict."""
        reg_resp = await client.post("/v1/engine/models", json=_MODEL_PAYLOAD)
        mid = reg_resp.json()["model_version_id"]
        ws_id = str(uuid7())

        run_resp = await client.post(
            f"/v1/workspaces/{ws_id}/engine/runs",
            json={
                "model_version_id": mid,
                "annual_shocks": {"2026": [50.0, 0.0]},
                "base_year": 2023,
                "satellite_coefficients": _SATELLITE_COEFFICIENTS,
            },
        )
        run_id = run_resp.json()["run_id"]

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
                        "source_description": "Gate test",
                    },
                    {
                        "sector_code": "S2",
                        "jobs_per_million_sar": 8.0,
                        "confidence": "ESTIMATED",
                        "source_description": "Gate test",
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
        data = wf_resp.json()

        # saudization_gaps dict present in response
        assert "saudization_gaps" in data
        assert isinstance(data["saudization_gaps"], dict)

    @pytest.mark.anyio
    async def test_governance_checks_pass_clean_run(
        self,
        client: AsyncClient,
    ) -> None:
        """No claims → governance status → nff_passed=True."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        status_resp = await client.get(
            f"/v1/workspaces/{ws_id}/governance/status/{run_id}",
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["nff_passed"] is True
        assert data["claims_total"] == 0
        assert data["claims_unresolved"] == 0

    @pytest.mark.anyio
    async def test_quality_gate_identifies_failing_run(
        self,
        client: AsyncClient,
    ) -> None:
        """Low quality (no inputs) → FAIL_REQUIRES_WAIVER."""
        ws_id = str(uuid7())
        run_id = str(uuid7())

        resp = await client.post(
            f"/v1/workspaces/{ws_id}/runs/{run_id}/quality",
            json={
                "base_table_year": 2020,
                "current_year": 2026,
                "coverage_pct": 0.1,  # Very low coverage → FAIL
                "base_table_vintage": "Gate test",
                "inputs": [],  # No inputs → score 0.0 → grade F
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
        assert data["publication_gate_pass"] is False
        assert data["publication_gate_mode"] == "FAIL_REQUIRES_WAIVER"
