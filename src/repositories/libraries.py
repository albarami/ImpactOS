"""Knowledge Flywheel repositories — MVP-12.

MappingLibraryRepository, AssumptionLibraryRepository, ScenarioPatternRepository.

Amendment 1: Version UniqueConstraint = (workspace_id, version)
Amendment 2: Only usage_count, last_used_at, status mutable on entries
Amendment 4: list_for_agent converts enhanced → legacy MappingLibraryEntry
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import (
    AssumptionLibraryEntryRow,
    AssumptionLibraryVersionRow,
    MappingLibraryEntryRow,
    MappingLibraryVersionRow,
    ScenarioPatternRow,
)
from src.models.common import utc_now

# ---------------------------------------------------------------------------
# Mapping Library
# ---------------------------------------------------------------------------


class MappingLibraryRepository:
    """Repository for mapping library entries and versions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Entries ---

    async def create_entry(
        self,
        *,
        entry_id: UUID,
        workspace_id: UUID,
        pattern: str,
        sector_code: str,
        confidence: float,
        usage_count: int = 0,
        source_engagement_id: UUID | None = None,
        last_used_at: datetime | None = None,
        tags: list[str] | None = None,
        created_by: UUID | None = None,
        status: str = "DRAFT",
    ) -> MappingLibraryEntryRow:
        row = MappingLibraryEntryRow(
            entry_id=entry_id,
            workspace_id=workspace_id,
            pattern=pattern,
            sector_code=sector_code,
            confidence=confidence,
            usage_count=usage_count,
            source_engagement_id=source_engagement_id,
            last_used_at=last_used_at,
            tags=tags or [],
            created_by=created_by,
            created_at=utc_now(),
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_entry(
        self, entry_id: UUID,
    ) -> MappingLibraryEntryRow | None:
        result = await self._session.execute(
            select(MappingLibraryEntryRow).where(
                MappingLibraryEntryRow.entry_id == entry_id,
            ),
        )
        return result.scalar_one_or_none()

    async def get_entries_by_workspace(
        self,
        workspace_id: UUID,
        *,
        sector_code: str | None = None,
    ) -> list[MappingLibraryEntryRow]:
        stmt = select(MappingLibraryEntryRow).where(
            MappingLibraryEntryRow.workspace_id == workspace_id,
        )
        if sector_code:
            stmt = stmt.where(
                MappingLibraryEntryRow.sector_code == sector_code,
            )
        stmt = stmt.order_by(MappingLibraryEntryRow.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_usage(
        self,
        entry_id: UUID,
        *,
        usage_count: int,
        last_used_at: datetime,
    ) -> MappingLibraryEntryRow | None:
        """Amendment 2: Only mutable fields."""
        row = await self.get_entry(entry_id)
        if row is None:
            return None
        row.usage_count = usage_count
        row.last_used_at = last_used_at
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def update_status(
        self,
        entry_id: UUID,
        *,
        status: str,
    ) -> MappingLibraryEntryRow | None:
        """Amendment 7: Status update for steward-gated promotion."""
        row = await self.get_entry(entry_id)
        if row is None:
            return None
        row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return row

    # --- Versions ---

    async def create_version(
        self,
        *,
        library_version_id: UUID,
        workspace_id: UUID,
        version: int,
        entry_ids: list,
        entry_count: int,
        published_by: UUID | None = None,
    ) -> MappingLibraryVersionRow:
        row = MappingLibraryVersionRow(
            library_version_id=library_version_id,
            workspace_id=workspace_id,
            version=version,
            entry_ids=entry_ids,
            entry_count=entry_count,
            published_by=published_by,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_latest_version(
        self, workspace_id: UUID,
    ) -> MappingLibraryVersionRow | None:
        """Amendment 1: Latest version by workspace."""
        result = await self._session.execute(
            select(MappingLibraryVersionRow)
            .where(MappingLibraryVersionRow.workspace_id == workspace_id)
            .order_by(MappingLibraryVersionRow.version.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def get_versions_by_workspace(
        self, workspace_id: UUID,
    ) -> list[MappingLibraryVersionRow]:
        result = await self._session.execute(
            select(MappingLibraryVersionRow)
            .where(MappingLibraryVersionRow.workspace_id == workspace_id)
            .order_by(MappingLibraryVersionRow.version.desc()),
        )
        return list(result.scalars().all())

    # --- Agent Adapter (Amendment 4) ---

    async def list_for_agent(
        self, workspace_id: UUID,
    ) -> list:
        """Convert enhanced entries to legacy MappingLibraryEntry shape.

        Used by MappingSuggestionAgent which expects src.models.mapping.MappingLibraryEntry.
        Returns DRAFT + PUBLISHED entries (broader pool for suggestions).
        """
        from src.models.mapping import (
            MappingLibraryEntry as LegacyMappingLibraryEntry,
        )

        rows = await self.get_entries_by_workspace(workspace_id)
        return [
            LegacyMappingLibraryEntry(
                entry_id=r.entry_id,
                pattern=r.pattern,
                sector_code=r.sector_code,
                confidence=r.confidence,
                usage_count=r.usage_count,
            )
            for r in rows
            if r.status in ("DRAFT", "PUBLISHED")
        ]


# ---------------------------------------------------------------------------
# Assumption Library
# ---------------------------------------------------------------------------


class AssumptionLibraryRepository:
    """Repository for assumption library entries and versions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_entry(
        self,
        *,
        entry_id: UUID,
        workspace_id: UUID,
        assumption_type: str,
        sector_code: str,
        default_value: float,
        range_low: float,
        range_high: float,
        unit: str,
        justification: str = "",
        source: str = "",
        source_engagement_id: UUID | None = None,
        usage_count: int = 0,
        last_used_at: datetime | None = None,
        confidence: str = "ASSUMED",
        created_by: UUID | None = None,
        evidence_refs: list | None = None,
        status: str = "DRAFT",
    ) -> AssumptionLibraryEntryRow:
        row = AssumptionLibraryEntryRow(
            entry_id=entry_id,
            workspace_id=workspace_id,
            assumption_type=assumption_type,
            sector_code=sector_code,
            default_value=default_value,
            range_low=range_low,
            range_high=range_high,
            unit=unit,
            justification=justification,
            source=source,
            source_engagement_id=source_engagement_id,
            usage_count=usage_count,
            last_used_at=last_used_at,
            confidence=confidence,
            created_by=created_by,
            created_at=utc_now(),
            evidence_refs=evidence_refs or [],
            status=status,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_entry(
        self, entry_id: UUID,
    ) -> AssumptionLibraryEntryRow | None:
        result = await self._session.execute(
            select(AssumptionLibraryEntryRow).where(
                AssumptionLibraryEntryRow.entry_id == entry_id,
            ),
        )
        return result.scalar_one_or_none()

    async def get_entries_by_workspace(
        self,
        workspace_id: UUID,
        *,
        assumption_type: str | None = None,
        sector_code: str | None = None,
    ) -> list[AssumptionLibraryEntryRow]:
        stmt = select(AssumptionLibraryEntryRow).where(
            AssumptionLibraryEntryRow.workspace_id == workspace_id,
        )
        if assumption_type:
            stmt = stmt.where(
                AssumptionLibraryEntryRow.assumption_type == assumption_type,
            )
        if sector_code:
            stmt = stmt.where(
                AssumptionLibraryEntryRow.sector_code == sector_code,
            )
        stmt = stmt.order_by(AssumptionLibraryEntryRow.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_usage(
        self,
        entry_id: UUID,
        *,
        usage_count: int,
        last_used_at: datetime,
    ) -> AssumptionLibraryEntryRow | None:
        row = await self.get_entry(entry_id)
        if row is None:
            return None
        row.usage_count = usage_count
        row.last_used_at = last_used_at
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def update_status(
        self,
        entry_id: UUID,
        *,
        status: str,
    ) -> AssumptionLibraryEntryRow | None:
        """Amendment 7: Status update for steward-gated promotion."""
        row = await self.get_entry(entry_id)
        if row is None:
            return None
        row.status = status
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def create_version(
        self,
        *,
        library_version_id: UUID,
        workspace_id: UUID,
        version: int,
        entry_ids: list,
        entry_count: int,
        published_by: UUID | None = None,
    ) -> AssumptionLibraryVersionRow:
        row = AssumptionLibraryVersionRow(
            library_version_id=library_version_id,
            workspace_id=workspace_id,
            version=version,
            entry_ids=entry_ids,
            entry_count=entry_count,
            published_by=published_by,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_latest_version(
        self, workspace_id: UUID,
    ) -> AssumptionLibraryVersionRow | None:
        result = await self._session.execute(
            select(AssumptionLibraryVersionRow)
            .where(
                AssumptionLibraryVersionRow.workspace_id == workspace_id,
            )
            .order_by(AssumptionLibraryVersionRow.version.desc())
            .limit(1),
        )
        return result.scalar_one_or_none()

    async def get_versions_by_workspace(
        self, workspace_id: UUID,
    ) -> list[AssumptionLibraryVersionRow]:
        result = await self._session.execute(
            select(AssumptionLibraryVersionRow)
            .where(
                AssumptionLibraryVersionRow.workspace_id == workspace_id,
            )
            .order_by(AssumptionLibraryVersionRow.version.desc()),
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Scenario Pattern
# ---------------------------------------------------------------------------


class ScenarioPatternRepository:
    """Repository for scenario patterns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        pattern_id: UUID,
        workspace_id: UUID,
        name: str,
        description: str = "",
        sector_focus: list | None = None,
        typical_shock_types: list | None = None,
        typical_assumptions: list | None = None,
        recommended_sensitivities: list | None = None,
        recommended_contrarian_angles: list | None = None,
        source_engagement_ids: list | None = None,
        usage_count: int = 0,
        tags: list | None = None,
        created_by: UUID | None = None,
    ) -> ScenarioPatternRow:
        row = ScenarioPatternRow(
            pattern_id=pattern_id,
            workspace_id=workspace_id,
            name=name,
            description=description,
            sector_focus=sector_focus or [],
            typical_shock_types=typical_shock_types or [],
            typical_assumptions=typical_assumptions or [],
            recommended_sensitivities=recommended_sensitivities or [],
            recommended_contrarian_angles=recommended_contrarian_angles or [],
            source_engagement_ids=source_engagement_ids or [],
            usage_count=usage_count,
            tags=tags or [],
            created_by=created_by,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(
        self, pattern_id: UUID,
    ) -> ScenarioPatternRow | None:
        result = await self._session.execute(
            select(ScenarioPatternRow).where(
                ScenarioPatternRow.pattern_id == pattern_id,
            ),
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(
        self, workspace_id: UUID,
    ) -> list[ScenarioPatternRow]:
        result = await self._session.execute(
            select(ScenarioPatternRow)
            .where(ScenarioPatternRow.workspace_id == workspace_id)
            .order_by(ScenarioPatternRow.created_at.desc()),
        )
        return list(result.scalars().all())

    async def update_usage(
        self,
        pattern_id: UUID,
        *,
        usage_count: int,
    ) -> ScenarioPatternRow | None:
        row = await self.get(pattern_id)
        if row is None:
            return None
        row.usage_count = usage_count
        await self._session.flush()
        await self._session.refresh(row)
        return row
