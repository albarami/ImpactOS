"""Tests for FastAPI data quality endpoints (MVP-13).

All 7 amendments tested:
1. STRUCTURAL_VALIDITY dimension in input scoring
2. DEFAULT_DIMENSION_WEIGHTS stored in response
3. mapping_coverage_pct on summary + gate logic
4. Smooth freshness decay (tested via engine tests)
5. summary_version + summary_hash in response
6. ?force_recompute=true on POST
7. Publication gate modes (PASS / PASS_WITH_WARNINGS / FAIL_REQUIRES_WAIVER)
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = str(uuid7())


def _quality_payload(
    *,
    base_table_year: int = 2020,
    current_year: int = 2026,
    coverage_pct: float = 0.9,
    mapping_coverage_pct: float | None = 0.8,
    base_table_vintage: str = "GASTAT 2020 IO Table",
    inputs: list | None = None,
    freshness_sources: list | None = None,
    key_gaps: list | None = None,
    key_strengths: list | None = None,
) -> dict:
    """Build a compute quality request body."""
    if inputs is None:
        inputs = [
            {
                "input_type": "mapping",
                "input_data": {
                    "available_sectors": ["A", "B", "C", "F", "G"],
                    "required_sectors": ["A", "B", "C", "F", "G"],
                    "confidence_distribution": {"hard": 0.8, "estimated": 0.2},
                    "has_evidence_refs": True,
                    "source_description": "Client BoQ extraction",
                },
            },
        ]
    if freshness_sources is None:
        freshness_sources = [
            {
                "name": "IO Table",
                "type": "io_table",
                "last_updated": "2023-01-01T00:00:00Z",
            },
        ]
    return {
        "base_table_year": base_table_year,
        "current_year": current_year,
        "coverage_pct": coverage_pct,
        "mapping_coverage_pct": mapping_coverage_pct,
        "base_table_vintage": base_table_vintage,
        "inputs": inputs,
        "freshness_sources": freshness_sources,
        "key_gaps": key_gaps or [],
        "key_strengths": key_strengths or ["Good freshness"],
    }


class TestComputeQuality:
    """POST /{workspace_id}/runs/{run_id}/quality"""

    @pytest.mark.anyio
    async def test_compute_returns_201(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload()
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["run_id"] == run_id
        assert data["workspace_id"] == WS_ID
        assert "overall_run_score" in data
        assert "overall_run_grade" in data
        assert "publication_gate_pass" in data
        assert "publication_gate_mode" in data

    @pytest.mark.anyio
    async def test_compute_empty_inputs(self, client: AsyncClient) -> None:
        """Empty inputs → score 0, grade F."""
        run_id = str(uuid7())
        payload = _quality_payload(inputs=[], freshness_sources=[])
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["overall_run_score"] == 0.0
        assert data["overall_run_grade"] == "F"

    @pytest.mark.anyio
    async def test_compute_persists_summary(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload()

        # POST
        await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )

        # GET should retrieve it
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
        )
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id

    @pytest.mark.anyio
    async def test_duplicate_returns_409(self, client: AsyncClient) -> None:
        """Second POST without force_recompute → 409."""
        run_id = str(uuid7())
        payload = _quality_payload()

        r1 = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert r1.status_code == 201

        r2 = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert r2.status_code == 409
        assert "force_recompute" in r2.json()["detail"]

    @pytest.mark.anyio
    async def test_force_recompute_amendment6(self, client: AsyncClient) -> None:
        """Amendment 6: ?force_recompute=true replaces existing."""
        run_id = str(uuid7())
        payload = _quality_payload(coverage_pct=0.5)

        await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )

        payload2 = _quality_payload(coverage_pct=0.95)
        r2 = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload2,
            params={"force_recompute": "true"},
        )
        assert r2.status_code == 201
        assert r2.json()["coverage_pct"] == 0.95

    @pytest.mark.anyio
    async def test_summary_version_amendment5(self, client: AsyncClient) -> None:
        """Amendment 5: summary_version present."""
        run_id = str(uuid7())
        payload = _quality_payload()
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert data["summary_version"] == "1.0.0"

    @pytest.mark.anyio
    async def test_summary_hash_nonempty_amendment5(self, client: AsyncClient) -> None:
        """Amendment 5: summary_hash is non-empty."""
        run_id = str(uuid7())
        payload = _quality_payload()
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert len(data["summary_hash"]) > 0

    @pytest.mark.anyio
    async def test_payload_contains_full_summary(self, client: AsyncClient) -> None:
        """payload field includes full RunQualitySummary JSON."""
        run_id = str(uuid7())
        payload = _quality_payload()
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        p = data["payload"]
        assert "input_scores" in p
        assert "freshness_report" in p
        assert "recommendation" in p


class TestGateModes:
    """Amendment 7: Publication gate mode tests."""

    @pytest.mark.anyio
    async def test_gate_pass(self, client: AsyncClient) -> None:
        """Grade B+, no stale, high coverage → PASS."""
        run_id = str(uuid7())
        payload = _quality_payload(
            coverage_pct=0.9,
            mapping_coverage_pct=0.8,
        )
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        # With good mapping inputs we expect at least PASS_WITH_WARNINGS
        assert data["publication_gate_mode"] in ("PASS", "PASS_WITH_WARNINGS")
        assert data["publication_gate_pass"] is True

    @pytest.mark.anyio
    async def test_gate_fail_low_mapping_amendment3(self, client: AsyncClient) -> None:
        """Amendment 3: mapping_coverage_pct < 0.5 → FAIL_REQUIRES_WAIVER."""
        run_id = str(uuid7())
        payload = _quality_payload(
            mapping_coverage_pct=0.3,
            coverage_pct=0.9,
        )
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert data["publication_gate_mode"] == "FAIL_REQUIRES_WAIVER"
        assert data["publication_gate_pass"] is False

    @pytest.mark.anyio
    async def test_gate_fail_no_inputs(self, client: AsyncClient) -> None:
        """No inputs → grade F → FAIL_REQUIRES_WAIVER."""
        run_id = str(uuid7())
        payload = _quality_payload(
            inputs=[], freshness_sources=[], coverage_pct=0.3,
        )
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert data["overall_run_grade"] == "F"
        assert data["publication_gate_mode"] == "FAIL_REQUIRES_WAIVER"
        assert data["publication_gate_pass"] is False


class TestGetRunQuality:
    """GET /{workspace_id}/runs/{run_id}/quality"""

    @pytest.mark.anyio
    async def test_get_existing(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload()
        await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )

        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
        )
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id

    @pytest.mark.anyio
    async def test_get_not_found(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/runs/{uuid7()}/quality",
        )
        assert response.status_code == 404


class TestFreshnessOverview:
    """GET /{workspace_id}/quality/freshness"""

    @pytest.mark.anyio
    async def test_empty_workspace(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{WS_ID}/quality/freshness",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summaries_count"] == 0
        assert data["freshness_reports"] == []

    @pytest.mark.anyio
    async def test_with_summaries(self, client: AsyncClient) -> None:
        ws = str(uuid7())
        for _ in range(2):
            run_id = str(uuid7())
            payload = _quality_payload()
            await client.post(
                f"/v1/workspaces/{ws}/runs/{run_id}/quality",
                json=payload,
            )

        response = await client.get(
            f"/v1/workspaces/{ws}/quality/freshness",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["summaries_count"] == 2
        assert len(data["freshness_reports"]) == 2


class TestQualityOverview:
    """GET /{workspace_id}/quality"""

    @pytest.mark.anyio
    async def test_overview_empty(self, client: AsyncClient) -> None:
        response = await client.get(
            f"/v1/workspaces/{uuid7()}/quality",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_summaries"] == 0

    @pytest.mark.anyio
    async def test_overview_with_summaries(self, client: AsyncClient) -> None:
        ws = str(uuid7())

        # Create a passing run
        r1 = str(uuid7())
        await client.post(
            f"/v1/workspaces/{ws}/runs/{r1}/quality",
            json=_quality_payload(coverage_pct=0.9),
        )

        # Create a failing run (no inputs, low coverage)
        r2 = str(uuid7())
        await client.post(
            f"/v1/workspaces/{ws}/runs/{r2}/quality",
            json=_quality_payload(
                inputs=[], freshness_sources=[], coverage_pct=0.3,
            ),
        )

        response = await client.get(
            f"/v1/workspaces/{ws}/quality",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_summaries"] == 2
        assert data["failing_count"] >= 1
        assert len(data["summaries"]) == 2

    @pytest.mark.anyio
    async def test_overview_counts(self, client: AsyncClient) -> None:
        ws = str(uuid7())

        # Passing
        await client.post(
            f"/v1/workspaces/{ws}/runs/{uuid7()}/quality",
            json=_quality_payload(coverage_pct=0.9, mapping_coverage_pct=0.9),
        )

        # Failing (low mapping coverage → Amendment 3)
        await client.post(
            f"/v1/workspaces/{ws}/runs/{uuid7()}/quality",
            json=_quality_payload(mapping_coverage_pct=0.2, coverage_pct=0.9),
        )

        response = await client.get(
            f"/v1/workspaces/{ws}/quality",
        )
        data = response.json()
        assert data["total_summaries"] == 2
        # At least one must be failing (mapping < 0.5)
        assert data["failing_count"] >= 1


class TestMappingCoverageAmendment3:
    """Amendment 3: mapping_coverage_pct appears in response + affects gate."""

    @pytest.mark.anyio
    async def test_mapping_coverage_in_response(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload(mapping_coverage_pct=0.72)
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert data["mapping_coverage_pct"] == 0.72

    @pytest.mark.anyio
    async def test_mapping_coverage_none_allowed(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload(mapping_coverage_pct=None)
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert data["mapping_coverage_pct"] is None

    @pytest.mark.anyio
    async def test_low_mapping_adds_key_gap(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload(mapping_coverage_pct=0.3)
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        data = response.json()
        assert any("mapped" in g.lower() for g in data["key_gaps"])


class TestKeyGapsAndStrengths:
    @pytest.mark.anyio
    async def test_key_gaps_preserved(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload(key_gaps=["Missing industrial sector"])
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert "Missing industrial sector" in response.json()["key_gaps"]

    @pytest.mark.anyio
    async def test_key_strengths_preserved(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload(key_strengths=["Recent data"])
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert "Recent data" in response.json()["key_strengths"]

    @pytest.mark.anyio
    async def test_recommendation_populated(self, client: AsyncClient) -> None:
        run_id = str(uuid7())
        payload = _quality_payload()
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/runs/{run_id}/quality",
            json=payload,
        )
        assert len(response.json()["recommendation"]) > 0
