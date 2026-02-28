"""Tests for observability/metrics API endpoints (MVP-7).

Covers: POST record metric event, GET engagement metrics,
GET dashboard summary, GET pilot readiness check.

S0-4: All routes workspace-scoped under /v1/workspaces/{workspace_id}/metrics/...
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

WS_ID = "01961060-0000-7000-8000-000000000001"


# ===================================================================
# POST /v1/workspaces/{workspace_id}/metrics — record metric event
# ===================================================================


class TestRecordMetric:
    """POST /v1/workspaces/{ws}/metrics — record a metric event."""

    @pytest.mark.anyio
    async def test_record_metric(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics", json={
            "engagement_id": str(uuid7()),
            "metric_type": "SCENARIO_REQUEST_TO_RESULTS",
            "value": 48.0,
            "unit": "hours",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "event_id" in data
        assert data["metric_type"] == "SCENARIO_REQUEST_TO_RESULTS"

    @pytest.mark.anyio
    async def test_record_metric_invalid_type(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics", json={
            "engagement_id": str(uuid7()),
            "metric_type": "INVALID_TYPE",
            "value": 1.0,
            "unit": "count",
        })
        assert resp.status_code == 422


# ===================================================================
# GET /v1/workspaces/{workspace_id}/metrics/engagement/{id} — engagement metrics
# ===================================================================


class TestEngagementMetrics:
    """GET /v1/workspaces/{ws}/metrics/engagement/{id} — retrieve metrics for an engagement."""

    @pytest.mark.anyio
    async def test_get_engagement_metrics(self, client: AsyncClient) -> None:
        eid = str(uuid7())
        await client.post(f"/v1/workspaces/{WS_ID}/metrics", json={
            "engagement_id": eid,
            "metric_type": "SCENARIO_REQUEST_TO_RESULTS",
            "value": 48.0,
            "unit": "hours",
        })
        await client.post(f"/v1/workspaces/{WS_ID}/metrics", json={
            "engagement_id": eid,
            "metric_type": "SCENARIOS_PER_ENGAGEMENT",
            "value": 8.0,
            "unit": "count",
        })
        resp = await client.get(f"/v1/workspaces/{WS_ID}/metrics/engagement/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engagement_id"] == eid
        assert len(data["events"]) == 2

    @pytest.mark.anyio
    async def test_empty_engagement_metrics(self, client: AsyncClient) -> None:
        eid = str(uuid7())
        resp = await client.get(f"/v1/workspaces/{WS_ID}/metrics/engagement/{eid}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 0


# ===================================================================
# GET /v1/workspaces/{workspace_id}/metrics/dashboard — dashboard summary
# ===================================================================


class TestDashboardEndpoint:
    """GET/POST /v1/workspaces/{ws}/metrics/dashboard — aggregated dashboard summary."""

    @pytest.mark.anyio
    async def test_dashboard_summary(self, client: AsyncClient) -> None:
        resp = await client.get(f"/v1/workspaces/{WS_ID}/metrics/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_engagements" in data
        assert "total_scenarios" in data
        assert "avg_cycle_time_hours" in data
        assert "nff_compliance_rate" in data

    @pytest.mark.anyio
    async def test_dashboard_with_data(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics/dashboard", json={
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
# POST /v1/workspaces/{workspace_id}/metrics/readiness — pilot readiness check
# ===================================================================


class TestReadinessEndpoint:
    """POST /v1/workspaces/{ws}/metrics/readiness — pilot readiness."""

    @pytest.mark.anyio
    async def test_readiness_healthy(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics/readiness", json={
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

    @pytest.mark.anyio
    async def test_readiness_unhealthy(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics/readiness", json={
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

    @pytest.mark.anyio
    async def test_readiness_has_checks(self, client: AsyncClient) -> None:
        resp = await client.post(f"/v1/workspaces/{WS_ID}/metrics/readiness", json={
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
