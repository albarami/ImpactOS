"""Portfolio optimization repository — CRUD, workspace scoping, idempotency, pagination."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import PortfolioOptimizationRow
from src.models.common import utc_now


class PortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        portfolio_id: UUID,
        workspace_id: UUID,
        model_version_id: UUID,
        optimization_version: str,
        config_json: dict,
        config_hash: str,
        objective_metric: str,
        cost_metric: str,
        budget: float,
        min_selected: int,
        max_selected: int | None,
        candidate_run_ids_json: list,
        selected_run_ids_json: list,
        result_json: dict,
        result_checksum: str,
    ) -> PortfolioOptimizationRow:
        row = PortfolioOptimizationRow(
            portfolio_id=portfolio_id,
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            optimization_version=optimization_version,
            config_json=config_json,
            config_hash=config_hash,
            objective_metric=objective_metric,
            cost_metric=cost_metric,
            budget=budget,
            min_selected=min_selected,
            max_selected=max_selected,
            candidate_run_ids_json=candidate_run_ids_json,
            selected_run_ids_json=selected_run_ids_json,
            result_json=result_json,
            result_checksum=result_checksum,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, portfolio_id: UUID) -> PortfolioOptimizationRow | None:
        result = await self._session.execute(
            select(PortfolioOptimizationRow).where(
                PortfolioOptimizationRow.portfolio_id == portfolio_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_workspace(
        self,
        portfolio_id: UUID,
        workspace_id: UUID,
    ) -> PortfolioOptimizationRow | None:
        result = await self._session.execute(
            select(PortfolioOptimizationRow).where(
                PortfolioOptimizationRow.portfolio_id == portfolio_id,
                PortfolioOptimizationRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_config_for_workspace(
        self,
        workspace_id: UUID,
        config_hash: str,
    ) -> PortfolioOptimizationRow | None:
        result = await self._session.execute(
            select(PortfolioOptimizationRow).where(
                PortfolioOptimizationRow.workspace_id == workspace_id,
                PortfolioOptimizationRow.config_hash == config_hash,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[PortfolioOptimizationRow], int]:
        base = select(PortfolioOptimizationRow).where(
            PortfolioOptimizationRow.workspace_id == workspace_id,
        )
        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()
        rows_result = await self._session.execute(
            base.order_by(
                PortfolioOptimizationRow.created_at.desc(),
                PortfolioOptimizationRow.portfolio_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(rows_result.scalars().all()), total
