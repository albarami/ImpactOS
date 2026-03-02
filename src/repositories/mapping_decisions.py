"""Mapping decision repository — append-only audit trail for HITL decisions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import MappingDecisionRow
from src.models.common import utc_now


class MappingDecisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        mapping_decision_id: UUID,
        line_item_id: UUID,
        scenario_spec_id: UUID,
        state: str,
        suggested_sector_code: str | None = None,
        suggested_confidence: float | None = None,
        final_sector_code: str | None = None,
        decision_type: str | None = None,
        decision_note: str | None = None,
        decided_by: UUID,
    ) -> MappingDecisionRow:
        now = utc_now()
        row = MappingDecisionRow(
            mapping_decision_id=mapping_decision_id,
            line_item_id=line_item_id,
            scenario_spec_id=scenario_spec_id,
            state=state,
            suggested_sector_code=suggested_sector_code,
            suggested_confidence=suggested_confidence,
            final_sector_code=final_sector_code,
            decision_type=decision_type,
            decision_note=decision_note,
            decided_by=decided_by,
            decided_at=now,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_latest(
        self, scenario_spec_id: UUID, line_item_id: UUID,
    ) -> MappingDecisionRow | None:
        """Get the most recent decision for a (scenario, line_item) pair."""
        result = await self._session.execute(
            select(MappingDecisionRow)
            .where(
                MappingDecisionRow.scenario_spec_id == scenario_spec_id,
                MappingDecisionRow.line_item_id == line_item_id,
            )
            .order_by(MappingDecisionRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_history(
        self, scenario_spec_id: UUID, line_item_id: UUID,
    ) -> list[MappingDecisionRow]:
        """Get all decision entries for a (scenario, line_item) pair, oldest first."""
        result = await self._session.execute(
            select(MappingDecisionRow)
            .where(
                MappingDecisionRow.scenario_spec_id == scenario_spec_id,
                MappingDecisionRow.line_item_id == line_item_id,
            )
            .order_by(MappingDecisionRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_by_scenario(
        self, scenario_spec_id: UUID,
    ) -> list[MappingDecisionRow]:
        """Get all decisions for a scenario (all line items)."""
        result = await self._session.execute(
            select(MappingDecisionRow)
            .where(MappingDecisionRow.scenario_spec_id == scenario_spec_id)
            .order_by(MappingDecisionRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_latest_by_scenario_and_state(
        self,
        scenario_spec_id: UUID,
        state: str,
        *,
        min_confidence: float | None = None,
    ) -> list[MappingDecisionRow]:
        """Get latest decision per line_item for a scenario, filtered by state.

        Uses a subquery to find the max created_at per line_item_id,
        then filters by state (and optionally by min confidence).
        """
        from sqlalchemy import func

        # Subquery: max created_at per line_item_id for this scenario
        max_ts_sq = (
            select(
                MappingDecisionRow.line_item_id,
                func.max(MappingDecisionRow.created_at).label("max_ts"),
            )
            .where(MappingDecisionRow.scenario_spec_id == scenario_spec_id)
            .group_by(MappingDecisionRow.line_item_id)
            .subquery()
        )

        query = (
            select(MappingDecisionRow)
            .join(
                max_ts_sq,
                (MappingDecisionRow.line_item_id == max_ts_sq.c.line_item_id)
                & (MappingDecisionRow.created_at == max_ts_sq.c.max_ts),
            )
            .where(
                MappingDecisionRow.scenario_spec_id == scenario_spec_id,
                MappingDecisionRow.state == state,
            )
        )

        if min_confidence is not None:
            query = query.where(
                MappingDecisionRow.suggested_confidence >= min_confidence,
            )

        result = await self._session.execute(query)
        return list(result.scalars().all())
