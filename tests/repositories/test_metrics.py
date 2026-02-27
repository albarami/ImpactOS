"""Tests for MetricEventRepository — TDD for metrics rewiring."""

import pytest
from uuid_extensions import uuid7

from src.repositories.metrics import MetricEventRepository


@pytest.fixture
def repo(db_session):
    return MetricEventRepository(db_session)


class TestMetricEventRepository:

    @pytest.mark.anyio
    async def test_create_and_list(self, repo: MetricEventRepository) -> None:
        eid = uuid7()
        row = await repo.create(
            event_id=uuid7(),
            engagement_id=eid,
            metric_type="SCENARIO_REQUEST_TO_RESULTS",
            value=48.0,
            unit="hours",
        )
        assert row.engagement_id == eid
        assert row.metric_type == "SCENARIO_REQUEST_TO_RESULTS"

        all_rows = await repo.list_all()
        assert len(all_rows) == 1

    @pytest.mark.anyio
    async def test_get_by_engagement(self, repo: MetricEventRepository) -> None:
        eid = uuid7()
        other_eid = uuid7()
        await repo.create(event_id=uuid7(), engagement_id=eid,
                          metric_type="DATA_PREP_TIME", value=10.0, unit="hours")
        await repo.create(event_id=uuid7(), engagement_id=eid,
                          metric_type="CHARTING_TIME", value=5.0, unit="hours")
        await repo.create(event_id=uuid7(), engagement_id=other_eid,
                          metric_type="DATA_PREP_TIME", value=20.0, unit="hours")

        rows = await repo.get_by_engagement(eid)
        assert len(rows) == 2

    @pytest.mark.anyio
    async def test_get_by_type(self, repo: MetricEventRepository) -> None:
        eid = uuid7()
        await repo.create(event_id=uuid7(), engagement_id=eid,
                          metric_type="DATA_PREP_TIME", value=10.0, unit="hours")
        await repo.create(event_id=uuid7(), engagement_id=eid,
                          metric_type="CHARTING_TIME", value=5.0, unit="hours")

        rows = await repo.get_by_type("DATA_PREP_TIME")
        assert len(rows) == 1
        assert rows[0].value == 10.0
