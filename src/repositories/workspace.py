"""Workspace repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import WorkspaceRow
from src.models.common import utc_now


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, workspace_id: UUID, client_name: str,
                     engagement_code: str, classification: str,
                     description: str, created_by: UUID) -> WorkspaceRow:
        now = utc_now()
        row = WorkspaceRow(
            workspace_id=workspace_id, client_name=client_name,
            engagement_code=engagement_code, classification=classification,
            description=description, created_by=created_by,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, workspace_id: UUID) -> WorkspaceRow | None:
        return await self._session.get(WorkspaceRow, workspace_id)

    async def list_all(self) -> list[WorkspaceRow]:
        result = await self._session.execute(select(WorkspaceRow))
        return list(result.scalars().all())
