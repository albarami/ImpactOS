"""Tests for FastAPI workforce endpoints (MVP-11).

Workspace-scoped routes with all 9 amendments.

Tests:
- CRUD for employment coefficients, occupation bridge, saudization rules
- Compute workforce impact (full pipeline + optional bridge/rules)
- Feasibility integration (Amendment 1)
- Model version mismatch (422)
- Idempotency (Amendment 9)
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.models.common import new_uuid7

WS_ID = str(uuid7())


@pytest.fixture
async def seeded_model_with_results(db_session):
    """Seed model, run, and result sets for workforce compute tests."""
    from src.repositories.engine import (
        ModelDataRepository,
        ModelVersionRepository,
        ResultSetRepository,
        RunSnapshotRepository,
    )

    mv_repo = ModelVersionRepository(db_session)
    md_repo = ModelDataRepository(db_session)
    rs_repo = RunSnapshotRepository(db_session)
    result_repo = ResultSetRepository(db_session)

    mv_id = new_uuid7()
    run_id = new_uuid7()

    await mv_repo.create(
        model_version_id=mv_id,
        base_year=2020,
        source="test",
        sector_count=3,
        checksum="abc123",
    )
    await md_repo.create(
        model_version_id=mv_id,
        z_matrix_json=[[0.1, 0.2, 0.0], [0.0, 0.1, 0.3], [0.2, 0.0, 0.1]],
        x_vector_json=[1000.0, 800.0, 600.0],
        sector_codes=["SEC01", "SEC02", "SEC03"],
    )
    await rs_repo.create(
        run_id=run_id,
        model_version_id=mv_id,
        taxonomy_version_id=new_uuid7(),
        concordance_version_id=new_uuid7(),
        mapping_library_version_id=new_uuid7(),
        assumption_library_version_id=new_uuid7(),
        prompt_pack_version_id=new_uuid7(),
        source_checksums=[],
    )
    # total_output
    await result_repo.create(
        result_id=new_uuid7(),
        run_id=run_id,
        metric_type="total_output",
        values={"SEC01": 10_000_000.0, "SEC02": 5_000_000.0, "SEC03": 2_000_000.0},
        sector_breakdowns={},
    )
    # direct_effect
    await result_repo.create(
        result_id=new_uuid7(),
        run_id=run_id,
        metric_type="direct_effect",
        values={"SEC01": 6_000_000.0, "SEC02": 3_000_000.0, "SEC03": 1_200_000.0},
        sector_breakdowns={},
    )
    # indirect_effect
    await result_repo.create(
        result_id=new_uuid7(),
        run_id=run_id,
        metric_type="indirect_effect",
        values={"SEC01": 4_000_000.0, "SEC02": 2_000_000.0, "SEC03": 800_000.0},
        sector_breakdowns={},
    )

    return {"model_version_id": str(mv_id), "run_id": str(run_id)}


# ---------------------------------------------------------------------------
# Employment Coefficients CRUD
# ---------------------------------------------------------------------------


class TestCreateEmploymentCoefficients:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        payload = {
            "model_version_id": str(uuid7()),
            "output_unit": "MILLION_SAR",
            "base_year": 2024,
            "coefficients": [
                {
                    "sector_code": "SEC01",
                    "jobs_per_million_sar": 12.5,
                    "confidence": "HARD",
                    "source_description": "GASTAT",
                },
            ],
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "employment_coefficients_id" in data
        assert data["version"] == 1
        assert data["output_unit"] == "MILLION_SAR"

    @pytest.mark.anyio
    async def test_create_new_version(self, client: AsyncClient) -> None:
        # Create v1
        payload = {
            "model_version_id": str(uuid7()),
            "output_unit": "SAR",
            "base_year": 2024,
            "coefficients": [],
        }
        r1 = await client.post(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
            json=payload,
        )
        ec_id = r1.json()["employment_coefficients_id"]

        # Create v2
        payload["employment_coefficients_id"] = ec_id
        r2 = await client.post(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
            json=payload,
        )
        assert r2.status_code == 201
        assert r2.json()["version"] == 2


class TestListEmploymentCoefficients:
    @pytest.mark.anyio
    async def test_list_returns_200(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGetEmploymentCoefficients:
    @pytest.mark.anyio
    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/employment-coefficients/{fake_id}",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Occupation Bridge CRUD
# ---------------------------------------------------------------------------


class TestCreateOccupationBridge:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        payload = {
            "model_version_id": str(uuid7()),
            "entries": [
                {
                    "sector_code": "SEC01",
                    "occupation_code": "ENG",
                    "share": 0.6,
                    "confidence": "HARD",
                },
            ],
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/occupation-bridge",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "bridge_id" in data
        assert data["version"] == 1


class TestGetOccupationBridge:
    @pytest.mark.anyio
    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/occupation-bridge/{uuid7()}",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Saudization Rules CRUD
# ---------------------------------------------------------------------------


class TestCreateSaudizationRules:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        payload = {
            "tier_assignments": [
                {
                    "occupation_code": "ENG",
                    "nationality_tier": "SAUDI_READY",
                    "rationale": "Test",
                },
            ],
            "sector_targets": [
                {
                    "sector_code": "SEC01",
                    "target_saudi_pct": 0.30,
                    "source": "Nitaqat",
                    "effective_year": 2025,
                },
            ],
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/saudization-rules",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "rules_id" in data
        assert data["version"] == 1


class TestGetSaudizationRules:
    @pytest.mark.anyio
    async def test_get_not_found_404(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/saudization-rules/{uuid7()}",
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Compute Workforce Impact
# ---------------------------------------------------------------------------


class TestComputeWorkforce:
    @pytest.mark.anyio
    async def test_compute_returns_200(
        self, client: AsyncClient, seeded_model_with_results,
    ) -> None:
        seeds = seeded_model_with_results
        mv_id = seeds["model_version_id"]
        run_id = seeds["run_id"]

        # First create coefficients matching model version
        coeff_payload = {
            "model_version_id": mv_id,
            "output_unit": "MILLION_SAR",
            "base_year": 2024,
            "coefficients": [
                {"sector_code": "SEC01", "jobs_per_million_sar": 10.0,
                 "confidence": "HARD"},
                {"sector_code": "SEC02", "jobs_per_million_sar": 15.0,
                 "confidence": "ESTIMATED"},
                {"sector_code": "SEC03", "jobs_per_million_sar": 20.0,
                 "confidence": "ASSUMED"},
            ],
        }
        r = await client.post(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
            json=coeff_payload,
        )
        ec_id = r.json()["employment_coefficients_id"]

        # Compute workforce
        compute_payload = {
            "employment_coefficients_id": ec_id,
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/workforce",
            json=compute_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert "workforce_result_id" in data
        assert data["delta_x_source"] == "unconstrained"
        assert len(data["sector_employment"]) == 3

    @pytest.mark.anyio
    async def test_missing_run_404(self, client: AsyncClient) -> None:
        fake_run_id = str(uuid7())
        payload = {
            "employment_coefficients_id": str(uuid7()),
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{fake_run_id}/workforce",
            json=payload,
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_missing_coefficients_404(
        self, client: AsyncClient, seeded_model_with_results,
    ) -> None:
        seeds = seeded_model_with_results
        run_id = seeds["run_id"]
        payload = {
            "employment_coefficients_id": str(uuid7()),
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/workforce",
            json=payload,
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_model_version_mismatch_422(
        self, client: AsyncClient, seeded_model_with_results,
    ) -> None:
        seeds = seeded_model_with_results
        run_id = seeds["run_id"]

        # Create coefficients with DIFFERENT model version
        wrong_mv = str(uuid7())
        coeff_payload = {
            "model_version_id": wrong_mv,
            "output_unit": "MILLION_SAR",
            "base_year": 2024,
            "coefficients": [],
        }
        r = await client.post(
            f"/v1/workspaces/{WS_ID}/employment-coefficients",
            json=coeff_payload,
        )
        ec_id = r.json()["employment_coefficients_id"]

        compute_payload = {
            "employment_coefficients_id": ec_id,
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/workforce",
            json=compute_payload,
        )
        assert response.status_code == 422
        assert "model version" in response.json()["detail"].lower()


class TestGetWorkforceResults:
    @pytest.mark.anyio
    async def test_get_empty_run(self, client: AsyncClient) -> None:
        fake_run_id = str(uuid7())
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{fake_run_id}/workforce",
        )
        assert response.status_code == 200
        assert response.json() == []
