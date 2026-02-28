"""Metrics and engagement repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import MetricEventRow, EngagementRow
from src.models.common import utc_now


class MetricEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, event_id: UUID, engagement_id: UUID,
                     metric_type: str, value: float, unit: str,
                     actor: UUID | None = None, metadata: dict | None = None) -> MetricEventRow:
        row = MetricEventRow(
            event_id=event_id,
            engagement_id=engagement_id,
            metric_type=metric_type,
            value=value,
            unit=unit,
            actor=actor,
            timestamp=utc_now(),
            metadata_json=metadata or {},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_engagement(self, engagement_id: UUID) -> list[MetricEventRow]:
        result = await self._session.execute(
            select(MetricEventRow).where(MetricEventRow.engagement_id == engagement_id)
        )
        return list(result.scalars().all())

    async def get_by_type(self, metric_type: str) -> list[MetricEventRow]:
        result = await self._session.execute(
            select(MetricEventRow).where(MetricEventRow.metric_type == metric_type)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[MetricEventRow]:
        result = await self._session.execute(select(MetricEventRow))
        return list(result.scalars().all())


class EngagementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, engagement_id: UUID, workspace_id: UUID,
                     name: str, current_phase: str) -> EngagementRow:
        row = EngagementRow(
            engagement_id=engagement_id,
            workspace_id=workspace_id,
            name=name,
            current_phase=current_phase,
            phase_transitions=[],
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, engagement_id: UUID) -> EngagementRow | None:
        return await self._session.get(EngagementRow, engagement_id)

    async def update_phase(self, engagement_id: UUID, new_phase: str,
                           transition: dict) -> EngagementRow | None:
        row = await self.get(engagement_id)
        if row is not None:
            transitions = list(row.phase_transitions or [])
            transitions.append(transition)
            row.phase_transitions = transitions
            row.current_phase = new_phase
            await self._session.flush()
        return row
