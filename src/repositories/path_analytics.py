"""Path analysis repository — CRUD, workspace scoping, idempotency, pagination."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import PathAnalysisRow
from src.models.common import utc_now


class PathAnalysisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *,
        analysis_id: UUID, run_id: UUID, workspace_id: UUID,
        analysis_version: str, config_json: dict, config_hash: str,
        max_depth: int, top_k: int,
        top_paths_json: list, chokepoints_json: list,
        depth_contributions_json: dict, coverage_ratio: float,
        result_checksum: str,
    ) -> PathAnalysisRow:
        row = PathAnalysisRow(
            analysis_id=analysis_id, run_id=run_id,
            workspace_id=workspace_id,
            analysis_version=analysis_version,
            config_json=config_json, config_hash=config_hash,
            max_depth=max_depth, top_k=top_k,
            top_paths_json=top_paths_json,
            chokepoints_json=chokepoints_json,
            depth_contributions_json=depth_contributions_json,
            coverage_ratio=coverage_ratio,
            result_checksum=result_checksum,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, analysis_id: UUID) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.analysis_id == analysis_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_workspace(
        self, analysis_id: UUID, workspace_id: UUID,
    ) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.analysis_id == analysis_id,
                PathAnalysisRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_run_and_config_for_workspace(
        self, run_id: UUID, config_hash: str, workspace_id: UUID,
    ) -> PathAnalysisRow | None:
        result = await self._session.execute(
            select(PathAnalysisRow).where(
                PathAnalysisRow.run_id == run_id,
                PathAnalysisRow.config_hash == config_hash,
                PathAnalysisRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_run(
        self, run_id: UUID, workspace_id: UUID, *,
        limit: int = 20, offset: int = 0,
    ) -> tuple[list[PathAnalysisRow], int]:
        base = select(PathAnalysisRow).where(
            PathAnalysisRow.run_id == run_id,
            PathAnalysisRow.workspace_id == workspace_id,
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()
        rows_result = await self._session.execute(
            base.order_by(
                PathAnalysisRow.created_at.desc(),
                PathAnalysisRow.analysis_id.desc(),
            ).limit(limit).offset(offset)
        )
        return list(rows_result.scalars().all()), total
