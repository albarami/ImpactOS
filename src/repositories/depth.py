"""Depth engine repositories — DepthPlanRepository + DepthArtifactRepository.

Repos take AsyncSession, call add()/flush() only — never commit().
The session dependency handles commit/rollback (Unit-of-Work).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import DepthArtifactRow, DepthPlanRow
from src.models.common import utc_now


class DepthPlanRepository:
    """Repository for depth engine plan metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        plan_id: UUID,
        workspace_id: UUID,
        scenario_spec_id: UUID | None = None,
        status: str = "PENDING",
    ) -> DepthPlanRow:
        now = utc_now()
        row = DepthPlanRow(
            plan_id=plan_id,
            workspace_id=workspace_id,
            scenario_spec_id=scenario_spec_id,
            status=status,
            current_step=None,
            degraded_steps=[],
            step_errors={},
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, plan_id: UUID) -> DepthPlanRow | None:
        return await self._session.get(DepthPlanRow, plan_id)

    async def get_by_workspace(self, workspace_id: UUID) -> list[DepthPlanRow]:
        result = await self._session.execute(
            select(DepthPlanRow)
            .where(DepthPlanRow.workspace_id == workspace_id)
            .order_by(DepthPlanRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        plan_id: UUID,
        status: str,
        *,
        current_step: str | None = None,
        error_message: str | None = None,
        degraded_steps: list[str] | None = None,
        step_errors: dict | None = None,
    ) -> DepthPlanRow | None:
        row = await self.get(plan_id)
        if row is not None:
            row.status = status
            row.current_step = current_step
            row.updated_at = utc_now()
            if error_message is not None:
                row.error_message = error_message
            if degraded_steps is not None:
                row.degraded_steps = degraded_steps
            if step_errors is not None:
                row.step_errors = step_errors
            await self._session.flush()
        return row

    async def list_all(self) -> list[DepthPlanRow]:
        result = await self._session.execute(select(DepthPlanRow))
        return list(result.scalars().all())


class DepthArtifactRepository:
    """Repository for per-step depth engine artifacts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        artifact_id: UUID,
        plan_id: UUID,
        step: str,
        payload: dict,
        disclosure_tier: str = "TIER0",
        metadata_json: dict | None = None,
    ) -> DepthArtifactRow:
        now = utc_now()
        row = DepthArtifactRow(
            artifact_id=artifact_id,
            plan_id=plan_id,
            step=step,
            payload=payload,
            disclosure_tier=disclosure_tier,
            metadata_json=metadata_json or {},
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, artifact_id: UUID) -> DepthArtifactRow | None:
        return await self._session.get(DepthArtifactRow, artifact_id)

    async def get_by_plan(self, plan_id: UUID) -> list[DepthArtifactRow]:
        result = await self._session.execute(
            select(DepthArtifactRow)
            .where(DepthArtifactRow.plan_id == plan_id)
            .order_by(DepthArtifactRow.created_at)
        )
        return list(result.scalars().all())

    async def get_by_plan_and_step(
        self, plan_id: UUID, step: str,
    ) -> DepthArtifactRow | None:
        result = await self._session.execute(
            select(DepthArtifactRow).where(
                DepthArtifactRow.plan_id == plan_id,
                DepthArtifactRow.step == step,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[DepthArtifactRow]:
        result = await self._session.execute(select(DepthArtifactRow))
        return list(result.scalars().all())
