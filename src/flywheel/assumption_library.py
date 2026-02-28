"""Assumption Library — versioned assumption defaults for the Knowledge Flywheel.

Provides:
- ``AssumptionDefault``: sector-level default assumption (numeric or categorical)
- ``AssumptionLibraryDraft``: mutable draft being assembled
- ``AssumptionLibraryVersion``: frozen, immutable, referenced by engagements
- ``AssumptionLibraryManager``: manages publish/release workflow with
  sector-based querying
- ``build_seed_defaults``: initial D-3/D-4 seed data

Per tech spec Section 9.6, MVP-12 design doc, and Amendments 1/3.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from src.flywheel.base import VersionedLibraryManager
from src.flywheel.models import AssumptionValueType, DraftStatus, ReuseScopeLevel
from src.flywheel.stores import VersionedLibraryStore
from src.models.common import (
    AssumptionType,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Entry model
# ---------------------------------------------------------------------------


class AssumptionDefault(ImpactOSBase):
    """A sector-level default assumption value.

    Pre-populates assumption registers for new engagements.
    Supports both numeric values (with ranges) and categorical values
    (with allowed-value lists) per Amendment 3.
    """

    assumption_default_id: UUIDv7 = Field(default_factory=new_uuid7)
    assumption_type: AssumptionType
    sector_code: str | None = None  # None = economy-wide default
    name: str
    value_type: AssumptionValueType  # NUMERIC or CATEGORICAL
    default_numeric_value: float | None = None
    default_text_value: str | None = None
    default_numeric_range: tuple[float, float] | None = None
    allowed_values: list[str] | None = None  # For CATEGORICAL: ["front", "even", "back"]
    unit: str
    rationale: str
    source: str  # "benchmark_initial", "engagement_calibrated", "expert"
    usage_count: int = 0
    last_validated_at: UTCTimestamp | None = None
    confidence: str  # "high", "medium", "low", "assumed"

    # Scope fields (Amendment 1)
    workspace_id: UUID | None = None
    source_engagement_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.GLOBAL_INTERNAL
    sanitized_for_promotion: bool = False


# ---------------------------------------------------------------------------
# Draft model (mutable, being assembled)
# ---------------------------------------------------------------------------


class AssumptionLibraryDraft(ImpactOSBase):
    """Mutable draft of an assumption library version.

    Tracks changes relative to a parent version for audit purposes.
    """

    draft_id: UUIDv7 = Field(default_factory=new_uuid7)
    parent_version_id: UUID | None = None
    defaults: list[AssumptionDefault] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.DRAFT
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Version model (frozen, immutable)
# ---------------------------------------------------------------------------


class AssumptionLibraryVersion(ImpactOSBase, frozen=True):
    """Immutable published assumption library version.

    Referenced by engagements to ensure reproducibility of default
    assumption sets.
    """

    version_id: UUIDv7 = Field(default_factory=new_uuid7)
    version_number: int
    published_at: UTCTimestamp = Field(default_factory=utc_now)
    published_by: UUID
    defaults: list[AssumptionDefault] = Field(default_factory=list)
    default_count: int = 0
    parent_version_id: UUID | None = None
    changes_from_parent: list[str] = Field(default_factory=list)
    added_entry_ids: list[UUID] = Field(default_factory=list)
    removed_entry_ids: list[UUID] = Field(default_factory=list)
    changed_entries: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class AssumptionLibraryManager(
    VersionedLibraryManager[
        AssumptionDefault,
        AssumptionLibraryDraft,
        AssumptionLibraryVersion,
    ]
):
    """Manages assumption library versions with publish/release workflow.

    Provides sector-based querying and draft-building for calibration
    updates.
    """

    def get_defaults_for_sector(
        self,
        sector_code: str,
        assumption_type: AssumptionType | None = None,
    ) -> list[AssumptionDefault]:
        """Get defaults applicable to a sector (sector-specific + economy-wide).

        Returns sector-specific defaults PLUS economy-wide defaults
        (``sector_code=None``). If *assumption_type* is given, filter by
        type too.

        Parameters
        ----------
        sector_code:
            The ISIC sector code to look up (e.g. ``"F"`` for Construction).
        assumption_type:
            Optional filter to restrict results to a single assumption type.

        Returns
        -------
        list[AssumptionDefault]
            Matching defaults from the active version, or empty list if
            no active version exists.
        """
        active = self.get_active_version()
        if active is None:
            return []

        results: list[AssumptionDefault] = []
        for d in active.defaults:
            # Include if sector matches or is economy-wide (None)
            if d.sector_code == sector_code or d.sector_code is None:
                if assumption_type is None or d.assumption_type == assumption_type:
                    results.append(d)
        return results

    def build_draft(
        self,
        base_version_id: UUID | None = None,
        calibration_updates: list[dict] | None = None,
    ) -> AssumptionLibraryDraft:
        """Build draft from base version, optionally with calibration updates.

        Parameters
        ----------
        base_version_id:
            If provided, copy defaults from this published version.
        calibration_updates:
            Optional list of calibration dicts (reserved for future use).

        Returns
        -------
        AssumptionLibraryDraft
            A new mutable draft ready for review/publication.
        """
        defaults: list[AssumptionDefault] = []
        parent_version_id: UUID | None = None

        # Start with defaults from base version if provided
        if base_version_id is not None:
            base_version = self.get_version(base_version_id)
            if base_version is not None:
                defaults = list(base_version.defaults)
                parent_version_id = base_version_id

        return AssumptionLibraryDraft(
            parent_version_id=parent_version_id,
            defaults=defaults,
            status=DraftStatus.DRAFT,
        )

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def _make_version(
        self,
        draft: AssumptionLibraryDraft,
        version_number: int,
        published_by: UUID,
    ) -> AssumptionLibraryVersion:
        """Build a frozen AssumptionLibraryVersion from a draft."""
        return AssumptionLibraryVersion(
            version_number=version_number,
            published_by=published_by,
            defaults=draft.defaults,
            default_count=len(draft.defaults),
            parent_version_id=draft.parent_version_id,
            changes_from_parent=draft.changes_from_parent,
            added_entry_ids=draft.added_entry_ids,
            removed_entry_ids=draft.removed_entry_ids,
            changed_entries=draft.changed_entries,
        )

    def _get_draft_status(self, draft: AssumptionLibraryDraft) -> DraftStatus:
        """Extract the DraftStatus from an AssumptionLibraryDraft."""
        return draft.status


# ---------------------------------------------------------------------------
# Seed defaults (Task 8)
# ---------------------------------------------------------------------------


def build_seed_defaults() -> list[AssumptionDefault]:
    """Build initial assumption defaults from D-3/D-4 data.

    Returns 7 seed defaults covering import shares, employment coefficients,
    phasing profiles, and GDP deflators. These provide sensible starting
    points for new engagements.

    Returns
    -------
    list[AssumptionDefault]
        Seven validated default assumptions.
    """
    return [
        # --- IMPORT_SHARE defaults ---
        AssumptionDefault(
            assumption_type=AssumptionType.IMPORT_SHARE,
            sector_code="F",
            name="Construction import share",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=0.35,
            default_numeric_range=(0.25, 0.50),
            unit="ratio",
            rationale="KAPSARC IO table import ratios for ISIC Section F",
            source="KAPSARC IO import ratios",
            confidence="medium",
        ),
        AssumptionDefault(
            assumption_type=AssumptionType.IMPORT_SHARE,
            sector_code="C",
            name="Manufacturing import share",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=0.45,
            default_numeric_range=(0.30, 0.60),
            unit="ratio",
            rationale="KAPSARC IO table import ratios for ISIC Section C",
            source="KAPSARC IO import ratios",
            confidence="medium",
        ),
        AssumptionDefault(
            assumption_type=AssumptionType.IMPORT_SHARE,
            sector_code=None,
            name="Economy-wide import share",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=0.30,
            default_numeric_range=(0.20, 0.45),
            unit="ratio",
            rationale="World Development Indicators trade data for Saudi Arabia",
            source="WDI trade data",
            confidence="medium",
        ),
        # --- JOBS_COEFF defaults ---
        AssumptionDefault(
            assumption_type=AssumptionType.JOBS_COEFF,
            sector_code="F",
            name="Construction employment coefficient",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=18.5,
            default_numeric_range=(12.0, 25.0),
            unit="jobs_per_million_SAR",
            rationale="D-4 employment coefficients for ISIC Section F",
            source="D-4 employment coefficients",
            confidence="medium",
        ),
        AssumptionDefault(
            assumption_type=AssumptionType.JOBS_COEFF,
            sector_code="K",
            name="Finance employment coefficient",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=5.2,
            default_numeric_range=(3.0, 8.0),
            unit="jobs_per_million_SAR",
            rationale="D-4 employment coefficients for ISIC Section K",
            source="D-4 employment coefficients",
            confidence="medium",
        ),
        # --- PHASING default (categorical) ---
        AssumptionDefault(
            assumption_type=AssumptionType.PHASING,
            sector_code=None,
            name="Default phasing profile",
            value_type=AssumptionValueType.CATEGORICAL,
            default_text_value="even",
            allowed_values=["front", "even", "back"],
            unit="profile",
            rationale="Expert default: even distribution across project phases",
            source="Expert",
            confidence="medium",
        ),
        # --- DEFLATOR default ---
        AssumptionDefault(
            assumption_type=AssumptionType.DEFLATOR,
            sector_code=None,
            name="Default GDP deflator",
            value_type=AssumptionValueType.NUMERIC,
            default_numeric_value=0.02,
            default_numeric_range=(0.01, 0.04),
            unit="annual_rate",
            rationale="SAMA inflation data for Saudi Arabia",
            source="SAMA inflation data",
            confidence="medium",
        ),
    ]
