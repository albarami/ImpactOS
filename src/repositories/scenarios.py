"""Scenario version repository — append-only versioning with surrogate PK."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ScenarioSpecRow
from src.models.common import utc_now


class ScenarioVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, scenario_spec_id: UUID, version: int, name: str,
                     workspace_id: UUID, base_model_version_id: UUID,
                     base_year: int, time_horizon: dict,
                     disclosure_tier: str = "TIER0", currency: str = "SAR",
                     shock_items: list | None = None,
                     assumption_ids: list | None = None,
                     data_quality_summary: dict | None = None,
                     is_locked: bool = False) -> ScenarioSpecRow:
        now = utc_now()
        row = ScenarioSpecRow(
            scenario_spec_id=scenario_spec_id, version=version, name=name,
            workspace_id=workspace_id, disclosure_tier=disclosure_tier,
            base_model_version_id=base_model_version_id,
            currency=currency, base_year=base_year,
            time_horizon=time_horizon,
            shock_items=shock_items or [],
            assumption_ids=assumption_ids or [],
            data_quality_summary=data_quality_summary,
            is_locked=is_locked,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_latest(self, scenario_spec_id: UUID) -> ScenarioSpecRow | None:
        result = await self._session.execute(
            select(ScenarioSpecRow)
            .where(ScenarioSpecRow.scenario_spec_id == scenario_spec_id)
            .order_by(ScenarioSpecRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_versions(self, scenario_spec_id: UUID) -> list[ScenarioSpecRow]:
        result = await self._session.execute(
            select(ScenarioSpecRow)
            .where(ScenarioSpecRow.scenario_spec_id == scenario_spec_id)
            .order_by(ScenarioSpecRow.version.asc())
        )
        return list(result.scalars().all())

    async def get_by_id_and_version(self, scenario_spec_id: UUID,
                                     version: int) -> ScenarioSpecRow | None:
        result = await self._session.execute(
            select(ScenarioSpecRow).where(
                ScenarioSpecRow.scenario_spec_id == scenario_spec_id,
                ScenarioSpecRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_by_workspace(
        self, scenario_spec_id: UUID, workspace_id: UUID,
    ) -> ScenarioSpecRow | None:
        """Get latest version of a scenario, scoped to workspace."""
        result = await self._session.execute(
            select(ScenarioSpecRow)
            .where(
                ScenarioSpecRow.scenario_spec_id == scenario_spec_id,
                ScenarioSpecRow.workspace_id == workspace_id,
            )
            .order_by(ScenarioSpecRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_latest_by_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        cursor_created_at: str | None = None,
        cursor_scenario_spec_id: str | None = None,
    ) -> tuple[list[ScenarioSpecRow], int]:
        """List latest version of each scenario in a workspace (paginated).

        Returns (rows, total_distinct_scenarios).
        Uses a subquery to find max version per scenario_spec_id,
        then joins back to get full rows.
        """
        # Subquery: max version per scenario_spec_id in this workspace
        max_version_sq = (
            select(
                ScenarioSpecRow.scenario_spec_id,
                func.max(ScenarioSpecRow.version).label("max_ver"),
            )
            .where(ScenarioSpecRow.workspace_id == workspace_id)
            .group_by(ScenarioSpecRow.scenario_spec_id)
            .subquery()
        )

        # Total distinct scenarios
        count_result = await self._session.execute(
            select(func.count()).select_from(max_version_sq)
        )
        total = count_result.scalar_one()

        # Main query: join to get full rows for latest versions
        query = (
            select(ScenarioSpecRow)
            .join(
                max_version_sq,
                (ScenarioSpecRow.scenario_spec_id == max_version_sq.c.scenario_spec_id)
                & (ScenarioSpecRow.version == max_version_sq.c.max_ver),
            )
            .order_by(
                ScenarioSpecRow.created_at.asc(),
                ScenarioSpecRow.scenario_spec_id.asc(),
            )
        )

        # Apply cursor
        if cursor_created_at is not None and cursor_scenario_spec_id is not None:
            from datetime import datetime
            ts = datetime.fromisoformat(cursor_created_at)
            cid = UUID(cursor_scenario_spec_id)
            query = query.where(
                (ScenarioSpecRow.created_at > ts)
                | (
                    (ScenarioSpecRow.created_at == ts)
                    & (ScenarioSpecRow.scenario_spec_id > cid)
                ),
            )

        query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all()), total
