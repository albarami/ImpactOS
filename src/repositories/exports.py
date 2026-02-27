"""Export repository — stores export metadata in the database."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ExportRow
from src.models.common import utc_now


class ExportRepository:
    """DB-backed export store. Replaces in-memory _export_store dict."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        export_id: UUID,
        run_id: UUID,
        mode: str,
        status: str,
        template_version: str = "v1.0",
        disclosure_tier: str = "TIER0",
        checksums_json: dict | None = None,
        blocked_reasons: list[str] | None = None,
    ) -> ExportRow:
        row = ExportRow(
            export_id=export_id,
            run_id=run_id,
            template_version=template_version,
            mode=mode,
            disclosure_tier=disclosure_tier,
            status=status,
            checksums_json=checksums_json,
            blocked_reasons=blocked_reasons or [],
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, export_id: UUID) -> ExportRow | None:
        return await self._session.get(ExportRow, export_id)

    async def list_all(self) -> list[ExportRow]:
        result = await self._session.execute(select(ExportRow))
        return list(result.scalars().all())

    async def update_status(self, export_id: UUID, status: str) -> ExportRow | None:
        row = await self.get(export_id)
        if row is not None:
            row.status = status
            await self._session.flush()
        return row
