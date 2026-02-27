"""Scenario version repository — append-only versioning with surrogate PK."""

from uuid import UUID

from sqlalchemy import select
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
                     data_quality_summary: dict | None = None) -> ScenarioSpecRow:
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
