"""Feasibility repositories — ConstraintSetRepository + FeasibilityResultRepository.

Repos take AsyncSession, call add()/flush() only — never commit().
The session dependency handles commit/rollback (Unit-of-Work).
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ConstraintSetRow, FeasibilityResultRow
from src.models.common import utc_now


class ConstraintSetRepository:
    """Repository for versioned constraint sets (append-only, same pattern as ScenarioSpec)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        constraint_set_id: UUID,
        version: int,
        workspace_id: UUID,
        model_version_id: UUID,
        name: str,
        constraints: list,
        created_by: UUID | None = None,
    ) -> ConstraintSetRow:
        row = ConstraintSetRow(
            constraint_set_id=constraint_set_id,
            version=version,
            workspace_id=workspace_id,
            model_version_id=model_version_id,
            name=name,
            constraints=constraints,
            created_at=utc_now(),
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, constraint_set_id: UUID, version: int) -> ConstraintSetRow | None:
        result = await self._session.execute(
            select(ConstraintSetRow).where(
                ConstraintSetRow.constraint_set_id == constraint_set_id,
                ConstraintSetRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(self, constraint_set_id: UUID) -> ConstraintSetRow | None:
        result = await self._session.execute(
            select(ConstraintSetRow)
            .where(ConstraintSetRow.constraint_set_id == constraint_set_id)
            .order_by(ConstraintSetRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(self, workspace_id: UUID) -> list[ConstraintSetRow]:
        result = await self._session.execute(
            select(ConstraintSetRow)
            .where(ConstraintSetRow.workspace_id == workspace_id)
            .order_by(ConstraintSetRow.created_at.desc())
        )
        return list(result.scalars().all())


class FeasibilityResultRepository:
    """Repository for immutable feasibility solve results."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        feasibility_result_id: UUID,
        workspace_id: UUID,
        unconstrained_run_id: UUID,
        constraint_set_id: UUID,
        constraint_set_version: int,
        feasible_delta_x: dict,
        unconstrained_delta_x: dict,
        gap_vs_unconstrained: dict,
        total_feasible_output: float,
        total_unconstrained_output: float,
        total_gap: float,
        binding_constraints: list,
        slack_constraint_ids: list,
        enabler_recommendations: list,
        confidence_summary: dict,
        satellite_coefficients_hash: str,
        satellite_coefficients_snapshot: dict,
        solver_type: str,
        solver_version: str,
        lp_status: str | None = None,
        fallback_used: bool = False,
    ) -> FeasibilityResultRow:
        row = FeasibilityResultRow(
            feasibility_result_id=feasibility_result_id,
            workspace_id=workspace_id,
            unconstrained_run_id=unconstrained_run_id,
            constraint_set_id=constraint_set_id,
            constraint_set_version=constraint_set_version,
            feasible_delta_x=feasible_delta_x,
            unconstrained_delta_x=unconstrained_delta_x,
            gap_vs_unconstrained=gap_vs_unconstrained,
            total_feasible_output=total_feasible_output,
            total_unconstrained_output=total_unconstrained_output,
            total_gap=total_gap,
            binding_constraints=binding_constraints,
            slack_constraint_ids=slack_constraint_ids,
            enabler_recommendations=enabler_recommendations,
            confidence_summary=confidence_summary,
            satellite_coefficients_hash=satellite_coefficients_hash,
            satellite_coefficients_snapshot=satellite_coefficients_snapshot,
            solver_type=solver_type,
            solver_version=solver_version,
            lp_status=lp_status,
            fallback_used=fallback_used,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, feasibility_result_id: UUID) -> FeasibilityResultRow | None:
        return await self._session.get(FeasibilityResultRow, feasibility_result_id)

    async def get_by_run(self, unconstrained_run_id: UUID) -> list[FeasibilityResultRow]:
        result = await self._session.execute(
            select(FeasibilityResultRow)
            .where(FeasibilityResultRow.unconstrained_run_id == unconstrained_run_id)
            .order_by(FeasibilityResultRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_workspace(self, workspace_id: UUID) -> list[FeasibilityResultRow]:
        result = await self._session.execute(
            select(FeasibilityResultRow)
            .where(FeasibilityResultRow.workspace_id == workspace_id)
            .order_by(FeasibilityResultRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_comparison(
        self,
        unconstrained_run_id: UUID,
        constraint_set_id: UUID,
    ) -> FeasibilityResultRow | None:
        result = await self._session.execute(
            select(FeasibilityResultRow).where(
                FeasibilityResultRow.unconstrained_run_id == unconstrained_run_id,
                FeasibilityResultRow.constraint_set_id == constraint_set_id,
            )
        )
        return result.scalar_one_or_none()
