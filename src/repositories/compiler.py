"""Compilation and learning loop (override pair) repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import CompilationRow, OverridePairRow
from src.models.common import utc_now


class CompilationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, compilation_id: UUID, result_json: dict,
                     metadata_json: dict) -> CompilationRow:
        row = CompilationRow(
            compilation_id=compilation_id,
            result_json=result_json,
            metadata_json=metadata_json,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, compilation_id: UUID) -> CompilationRow | None:
        return await self._session.get(CompilationRow, compilation_id)


class OverridePairRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, override_id: UUID, engagement_id: UUID,
                     line_item_id: UUID, line_item_text: str,
                     suggested_sector_code: str, final_sector_code: str,
                     project_type: str = "", actor: UUID | None = None) -> OverridePairRow:
        row = OverridePairRow(
            override_id=override_id, engagement_id=engagement_id,
            line_item_id=line_item_id, line_item_text=line_item_text,
            suggested_sector_code=suggested_sector_code,
            final_sector_code=final_sector_code,
            project_type=project_type, actor=actor,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_all(self) -> list[OverridePairRow]:
        result = await self._session.execute(select(OverridePairRow))
        return list(result.scalars().all())

    async def get_by_engagement(self, engagement_id: UUID) -> list[OverridePairRow]:
        result = await self._session.execute(
            select(OverridePairRow).where(
                OverridePairRow.engagement_id == engagement_id
            )
        )
        return list(result.scalars().all())
