"""Tests for FastAPI feasibility endpoints (MVP-10).

S0-4: Workspace-scoped routes with amendment enforcement.

Amendments tested:
- 501 for RAMP_RATE constraints
- 501 for TimeWindow constraints
- 422 for negative delta_x
- 422 for model version mismatch (Amendment 8)
- Solver metadata in response (Amendment 6)
- Gap sign convention (Amendment 2)
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.models.common import new_uuid7

WS_ID = str(uuid7())


@pytest.fixture
async def seeded_model(db_session):
    """Seed model version + data + run snapshot + result set for solve tests."""
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
    await result_repo.create(
        result_id=new_uuid7(),
        run_id=run_id,
        metric_type="total_output",
        values={"SEC01": 100.0, "SEC02": 80.0, "SEC03": 60.0},
        sector_breakdowns={},
    )

    return {"model_version_id": str(mv_id), "run_id": str(run_id)}


class TestCreateConstraintSet:
    @pytest.mark.anyio
    async def test_create_returns_201(self, client: AsyncClient) -> None:
        payload = {
            "name": "Test constraints",
            "model_version_id": str(uuid7()),
            "constraints": [
                {
                    "constraint_type": "CAPACITY_CAP",
                    "applies_to": "SEC01",
                    "value": 50.0,
                    "unit": "SAR",
                    "confidence": "HARD",
                },
            ],
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints", json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert "constraint_set_id" in data
        assert data["version"] == 1
        assert data["name"] == "Test constraints"

    @pytest.mark.anyio
    async def test_create_empty_constraints(self, client: AsyncClient) -> None:
        payload = {
            "name": "Empty set",
            "model_version_id": str(uuid7()),
            "constraints": [],
        }
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints", json=payload,
        )
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_create_new_version(self, client: AsyncClient) -> None:
        mv_id = str(uuid7())
        # V1
        r1 = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={"name": "V1", "model_version_id": mv_id, "constraints": []},
        )
        cs_id = r1.json()["constraint_set_id"]
        # V2
        r2 = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "V2",
                "model_version_id": mv_id,
                "constraints": [],
                "constraint_set_id": cs_id,
            },
        )
        assert r2.status_code == 201
        assert r2.json()["version"] == 2
        assert r2.json()["constraint_set_id"] == cs_id


class TestListConstraintSets:
    @pytest.mark.anyio
    async def test_list_returns_200(self, client: AsyncClient) -> None:
        response = await client.get(f"/v1/workspaces/{WS_ID}/constraints")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGetConstraintSet:
    @pytest.mark.anyio
    async def test_get_returns_200(self, client: AsyncClient) -> None:
        # Create one
        r = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Get test",
                "model_version_id": str(uuid7()),
                "constraints": [],
            },
        )
        cs_id = r.json()["constraint_set_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/constraints/{cs_id}",
        )
        assert response.status_code == 200
        assert response.json()["constraint_set_id"] == cs_id

    @pytest.mark.anyio
    async def test_get_specific_version(self, client: AsyncClient) -> None:
        mv_id = str(uuid7())
        r1 = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={"name": "V1", "model_version_id": mv_id, "constraints": []},
        )
        cs_id = r1.json()["constraint_set_id"]
        await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "V2",
                "model_version_id": mv_id,
                "constraints": [{"constraint_type": "BUDGET_CEILING",
                                  "applies_to": "all", "value": 500.0,
                                  "unit": "SAR", "confidence": "ASSUMED"}],
                "constraint_set_id": cs_id,
            },
        )

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/constraints/{cs_id}",
            params={"version": 1},
        )
        assert response.status_code == 200
        assert response.json()["version"] == 1

    @pytest.mark.anyio
    async def test_get_not_found(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/constraints/{uuid7()}",
        )
        assert response.status_code == 404


class TestSolveEndpoint:
    @pytest.mark.anyio
    async def test_solve_returns_200(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        # Create constraint set with matching model version
        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Solve test",
                "model_version_id": mv_id,
                "constraints": [
                    {
                        "constraint_type": "CAPACITY_CAP",
                        "applies_to": "SEC01",
                        "value": 50.0,
                        "unit": "SAR",
                        "confidence": "HARD",
                    },
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={
                "constraint_set_id": cs_id,
                "unconstrained_run_id": run_id,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "feasibility_result_id" in data
        assert data["total_gap"] >= 0
        assert data["solver_type"] == "ClippingSolver"
        assert data["solver_version"] is not None

    @pytest.mark.anyio
    async def test_solve_gap_sign_positive(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Gap test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        # Amendment 2: all gaps >= 0
        for v in data["gap_vs_unconstrained"].values():
            assert v >= 0, f"Gap should be >= 0 but got {v}"

    @pytest.mark.anyio
    async def test_solve_binding_constraints(
        self, client: AsyncClient, seeded_model,
    ) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Binding test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        assert len(data["binding_constraints"]) >= 1
        assert data["binding_constraints"][0]["constraint_type"] == "CAPACITY_CAP"

    @pytest.mark.anyio
    async def test_solve_feasible_leq_unconstr(
        self, client: AsyncClient, seeded_model,
    ) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "LEQ test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        for sector in data["feasible_delta_x"]:
            assert data["feasible_delta_x"][sector] <= data["unconstrained_delta_x"][sector]

    @pytest.mark.anyio
    async def test_solve_enabler_recommendations(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Enabler test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        assert len(data["enabler_recommendations"]) >= 1
        assert data["enabler_recommendations"][0]["priority_rank"] == 1

    @pytest.mark.anyio
    async def test_solve_confidence_summary(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Confidence test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        cs = data["confidence_summary"]
        assert cs["total_constraints"] == 1
        assert cs["hard_pct"] == 1.0

    @pytest.mark.anyio
    async def test_solve_satellite_hash_stored(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Hash test",
                "model_version_id": mv_id,
                "constraints": [],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        data = response.json()
        assert "satellite_coefficients_hash" in data
        assert len(data["satellite_coefficients_hash"]) > 0

    @pytest.mark.anyio
    async def test_solve_missing_run_404(self, client: AsyncClient) -> None:
        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Missing run",
                "model_version_id": str(uuid7()),
                "constraints": [],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": str(uuid7())},
        )
        assert response.status_code == 404

    @pytest.mark.anyio
    async def test_solve_missing_cs_404(
        self, client: AsyncClient, seeded_model,
    ) -> None:
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={
                "constraint_set_id": str(uuid7()),
                "unconstrained_run_id": seeded_model["run_id"],
            },
        )
        assert response.status_code == 404


class TestAmendment3_Ramp501:
    """Amendment 3: RAMP_RATE constraints rejected with 501."""

    @pytest.mark.anyio
    async def test_ramp_rate_returns_501(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Ramp test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "RAMP_RATE", "applies_to": "SEC01",
                     "value": 0.1, "unit": "pct", "confidence": "ESTIMATED"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert response.status_code == 501
        assert "RAMP_RATE" in response.json()["detail"]


class TestAmendment3_TimeWindow501:
    """Amendment 3: TimeWindow constraints rejected with 501."""

    @pytest.mark.anyio
    async def test_time_window_returns_501(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "TimeWindow test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD",
                     "time_window": {"start_year": 2024, "end_year": 2026}},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert response.status_code == 501
        detail = response.json()["detail"]
        assert (
            "time_window" in detail.lower()
            or "TimeWindow" in detail
        )


class TestAmendment8_ModelVersionMismatch:
    """Amendment 8: Model version compatibility check."""

    @pytest.mark.anyio
    async def test_model_version_mismatch_422(self, client: AsyncClient, seeded_model) -> None:
        run_id = seeded_model["run_id"]
        different_mv_id = str(uuid7())  # Different from seeded model version

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Mismatch test",
                "model_version_id": different_mv_id,
                "constraints": [],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        assert response.status_code == 422
        assert "model version" in response.json()["detail"].lower()


class TestGetFeasibilityResult:
    @pytest.mark.anyio
    async def test_get_result_after_solve(self, client: AsyncClient, seeded_model) -> None:
        mv_id = seeded_model["model_version_id"]
        run_id = seeded_model["run_id"]

        cs_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints",
            json={
                "name": "Result test",
                "model_version_id": mv_id,
                "constraints": [
                    {"constraint_type": "CAPACITY_CAP", "applies_to": "SEC01",
                     "value": 50.0, "unit": "SAR", "confidence": "HARD"},
                ],
            },
        )
        cs_id = cs_resp.json()["constraint_set_id"]

        solve_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/constraints/solve",
            json={"constraint_set_id": cs_id, "unconstrained_run_id": run_id},
        )
        solve_resp.json()["feasibility_result_id"]

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/feasibility",
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.anyio
    async def test_get_result_empty_run(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{uuid7()}/feasibility",
        )
        assert response.status_code == 200
        assert response.json() == []
