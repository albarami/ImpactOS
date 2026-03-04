"""Workshop session repository — CRUD, workspace scoping, idempotency, pagination."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import WorkshopSessionRow
from src.models.common import utc_now


class WorkshopSessionRepository:
    """Workspace-scoped workshop session persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        session_id: UUID,
        workspace_id: UUID,
        baseline_run_id: UUID,
        base_shocks_json: dict,
        slider_config_json: list,
        transformed_shocks_json: dict,
        config_hash: str,
        created_by: UUID | None = None,
    ) -> WorkshopSessionRow:
        """Create a new draft workshop session."""
        now = utc_now()
        row = WorkshopSessionRow(
            session_id=session_id,
            workspace_id=workspace_id,
            baseline_run_id=baseline_run_id,
            base_shocks_json=base_shocks_json,
            slider_config_json=slider_config_json,
            transformed_shocks_json=transformed_shocks_json,
            config_hash=config_hash,
            status="draft",
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, session_id: UUID) -> WorkshopSessionRow | None:
        result = await self._session.execute(
            select(WorkshopSessionRow).where(
                WorkshopSessionRow.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_workspace(
        self,
        session_id: UUID,
        workspace_id: UUID,
    ) -> WorkshopSessionRow | None:
        result = await self._session.execute(
            select(WorkshopSessionRow).where(
                WorkshopSessionRow.session_id == session_id,
                WorkshopSessionRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_config_for_workspace(
        self,
        workspace_id: UUID,
        config_hash: str,
    ) -> WorkshopSessionRow | None:
        result = await self._session.execute(
            select(WorkshopSessionRow).where(
                WorkshopSessionRow.workspace_id == workspace_id,
                WorkshopSessionRow.config_hash == config_hash,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        session_id: UUID,
        *,
        status: str,
        committed_run_id: UUID | None = None,
    ) -> WorkshopSessionRow | None:
        """Update session status and optionally set committed_run_id."""
        row = await self.get(session_id)
        if row is None:
            return None
        row.status = status
        if committed_run_id is not None:
            row.committed_run_id = committed_run_id
        row.updated_at = utc_now()
        await self._session.flush()
        return row

    async def update_preview_summary(
        self,
        session_id: UUID,
        preview_summary_json: dict,
    ) -> WorkshopSessionRow | None:
        """Update the latest preview summary metadata."""
        row = await self.get(session_id)
        if row is None:
            return None
        row.preview_summary_json = preview_summary_json
        row.updated_at = utc_now()
        await self._session.flush()
        return row

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[WorkshopSessionRow], int]:
        base = select(WorkshopSessionRow).where(
            WorkshopSessionRow.workspace_id == workspace_id,
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()
        rows_result = await self._session.execute(
            base.order_by(
                WorkshopSessionRow.updated_at.desc(),
                WorkshopSessionRow.session_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(rows_result.scalars().all()), total
