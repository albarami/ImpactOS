"""Tests for observability/metrics API endpoints (MVP-7).

Covers: POST record metric event, GET engagement metrics,
GET dashboard summary, GET pilot readiness check.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.api.main import app


@pytest.fixture
def base_url() -> str:
    return "http://test"


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


# ===================================================================
# POST /v1/metrics — record metric event
# ===================================================================


class TestRecordMetric:
    """POST /v1/metrics — record a metric event."""

    @pytest.mark.asyncio
    async def test_record_metric(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics", json={
                "engagement_id": str(uuid7()),
                "metric_type": "SCENARIO_REQUEST_TO_RESULTS",
                "value": 48.0,
                "unit": "hours",
            })
        assert resp.status_code == 201
        data = resp.json()
        assert "event_id" in data
        assert data["metric_type"] == "SCENARIO_REQUEST_TO_RESULTS"

    @pytest.mark.asyncio
    async def test_record_metric_invalid_type(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics", json={
                "engagement_id": str(uuid7()),
                "metric_type": "INVALID_TYPE",
                "value": 1.0,
                "unit": "count",
            })
        assert resp.status_code == 422


# ===================================================================
# GET /v1/metrics/engagement/{id} — engagement metrics
# ===================================================================


class TestEngagementMetrics:
    """GET /v1/metrics/engagement/{id} — retrieve metrics for an engagement."""

    @pytest.mark.asyncio
    async def test_get_engagement_metrics(self, transport: ASGITransport, base_url: str) -> None:
        eid = str(uuid7())
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            # Record two events
            await client.post("/v1/metrics", json={
                "engagement_id": eid,
                "metric_type": "SCENARIO_REQUEST_TO_RESULTS",
                "value": 48.0,
                "unit": "hours",
            })
            await client.post("/v1/metrics", json={
                "engagement_id": eid,
                "metric_type": "SCENARIOS_PER_ENGAGEMENT",
                "value": 8.0,
                "unit": "count",
            })
            resp = await client.get(f"/v1/metrics/engagement/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engagement_id"] == eid
        assert len(data["events"]) == 2

    @pytest.mark.asyncio
    async def test_empty_engagement_metrics(self, transport: ASGITransport, base_url: str) -> None:
        eid = str(uuid7())
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.get(f"/v1/metrics/engagement/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 0


# ===================================================================
# GET /v1/metrics/dashboard — dashboard summary
# ===================================================================


class TestDashboardEndpoint:
    """GET /v1/metrics/dashboard — aggregated dashboard summary."""

    @pytest.mark.asyncio
    async def test_dashboard_summary(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.get("/v1/metrics/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_engagements" in data
        assert "total_scenarios" in data
        assert "avg_cycle_time_hours" in data
        assert "nff_compliance_rate" in data

    @pytest.mark.asyncio
    async def test_dashboard_with_data(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics/dashboard", json={
                "engagements": [
                    {
                        "scenarios_count": 8,
                        "cycle_time_hours": 48.0,
                        "nff_passed": True,
                        "claims_total": 20,
                        "claims_supported": 18,
                    },
                ],
                "library": {
                    "mappings_count": 100,
                    "assumptions_count": 30,
                    "patterns_count": 15,
                },
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_engagements"] == 1
        assert data["total_scenarios"] == 8


# ===================================================================
# GET /v1/metrics/readiness — pilot readiness check
# ===================================================================


class TestReadinessEndpoint:
    """GET /v1/metrics/readiness — pilot readiness."""

    @pytest.mark.asyncio
    async def test_readiness_healthy(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics/readiness", json={
                "database": True,
                "object_storage": True,
                "model_versions_loaded": 3,
                "mapping_library_size": 100,
                "assumption_library_size": 30,
                "pattern_library_size": 15,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
        assert len(data["blocking_reasons"]) == 0

    @pytest.mark.asyncio
    async def test_readiness_unhealthy(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics/readiness", json={
                "database": False,
                "object_storage": True,
                "model_versions_loaded": 0,
                "mapping_library_size": 5,
                "assumption_library_size": 2,
                "pattern_library_size": 0,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert len(data["blocking_reasons"]) >= 1

    @pytest.mark.asyncio
    async def test_readiness_has_checks(self, transport: ASGITransport, base_url: str) -> None:
        async with AsyncClient(transport=transport, base_url=base_url) as client:
            resp = await client.post("/v1/metrics/readiness", json={
                "database": True,
                "object_storage": True,
                "model_versions_loaded": 3,
                "mapping_library_size": 100,
                "assumption_library_size": 30,
                "pattern_library_size": 15,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "checks" in data
