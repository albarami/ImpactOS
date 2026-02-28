"""Scenario Pattern Library — reusable scenario templates for the Knowledge Flywheel.

Provides:
- ``ScenarioPattern``: a reusable scenario template with lineage tracking
  (Amendment 7) and scope controls (Amendment 1)
- ``ScenarioPatternLibrary``: manages scenario patterns with similarity-based
  merging, filtering, and template suggestion

Unlike the mapping and assumption libraries, the scenario pattern library does
NOT use ``VersionedLibraryManager`` because patterns have a different lifecycle:
they are continuously merged via rolling averages rather than versioned
publish/release snapshots.

Per MVP-12 design doc, Amendments 1 and 7.
"""

from __future__ import annotations

import math
from uuid import UUID

from pydantic import Field

from src.flywheel.models import ReuseScopeLevel
from src.models.common import (
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ScenarioPattern(ImpactOSBase):
    """A reusable scenario template capturing recurring structures.

    Tracks which engagements contributed to the pattern (lineage) and
    enforces scope rules for cross-workspace reuse.
    """

    pattern_id: UUIDv7 = Field(default_factory=new_uuid7)
    name: str
    description: str

    # Sector structure
    typical_sector_shares: dict[str, float]  # sector_code -> share of total spend
    sector_share_ranges: dict[str, tuple[float, float]] | None = None

    # Phasing
    typical_phasing: dict[int, float] | None = None  # year_offset -> share
    typical_duration_years: int | None = None

    # Key assumptions
    typical_import_share: float | None = None
    typical_local_content: float | None = None

    # Metadata
    project_type: str  # "logistics_zone", "giga_project", "housing", etc.
    sector_focus: str | None = None
    engagement_count: int = 0
    last_used_at: UTCTimestamp | None = None
    confidence: str  # "high", "medium", "low"

    # Lineage (Amendment 7)
    contributing_engagement_ids: list[UUID] = Field(default_factory=list)
    contributing_scenario_ids: list[UUID] = Field(default_factory=list)
    merge_history: list[dict] | None = None

    # Scope (Amendment 1)
    workspace_id: UUID | None = None
    source_engagement_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.WORKSPACE_ONLY
    sanitized_for_promotion: bool = False


# ---------------------------------------------------------------------------
# Library (NOT versioned — different lifecycle)
# ---------------------------------------------------------------------------

# Similarity threshold for merging patterns
_MERGE_SIMILARITY_THRESHOLD = 0.8


class ScenarioPatternLibrary:
    """Manages reusable scenario patterns.

    Patterns are created from completed engagements and merged when
    sufficiently similar (cosine similarity on sector shares > 0.8).
    """

    def __init__(self) -> None:
        self._patterns: list[ScenarioPattern] = []

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def find_patterns(
        self,
        project_type: str | None = None,
        sector_focus: str | None = None,
    ) -> list[ScenarioPattern]:
        """Find patterns matching criteria. Both filters are optional.

        Parameters
        ----------
        project_type:
            Filter to patterns with this project type.
        sector_focus:
            Filter to patterns with this sector focus.

        Returns
        -------
        list[ScenarioPattern]
            All matching patterns. If no filters, returns all patterns.
        """
        results: list[ScenarioPattern] = []
        for pattern in self._patterns:
            if project_type is not None and pattern.project_type != project_type:
                continue
            if sector_focus is not None and pattern.sector_focus != sector_focus:
                continue
            results.append(pattern)
        return results

    # ------------------------------------------------------------------
    # Record / Merge
    # ------------------------------------------------------------------

    def record_engagement_pattern(
        self,
        engagement_id: UUID,
        scenario_spec_id: UUID,
        project_type: str,
        sector_shares: dict[str, float],
        name: str | None = None,
        import_share: float | None = None,
        local_content: float | None = None,
        duration_years: int | None = None,
    ) -> ScenarioPattern:
        """Extract a pattern from a completed engagement.

        If a similar pattern exists (cosine similarity on sector shares > 0.8):
          - Merge: rolling average on sector shares
          - Increment engagement_count
          - Add to contributing_engagement_ids
          - Record merge_history entry
        If no similar pattern exists:
          - Create new pattern

        Parameters
        ----------
        engagement_id:
            The engagement this pattern was extracted from.
        scenario_spec_id:
            The scenario spec that produced this pattern.
        project_type:
            Classification of the project (e.g. "logistics_zone").
        sector_shares:
            Sector code to share mapping from the engagement.
        name:
            Optional human-readable name. Auto-generated if not provided.
        import_share:
            Optional typical import share ratio.
        local_content:
            Optional typical local content ratio.
        duration_years:
            Optional typical project duration in years.

        Returns
        -------
        ScenarioPattern
            The created or updated pattern.
        """
        # Find the best matching existing pattern
        best_match: ScenarioPattern | None = None
        best_similarity: float = 0.0

        for pattern in self._patterns:
            if pattern.project_type != project_type:
                continue
            sim = self._cosine_similarity(
                pattern.typical_sector_shares, sector_shares
            )
            if sim > best_similarity:
                best_similarity = sim
                best_match = pattern

        if best_match is not None and best_similarity > _MERGE_SIMILARITY_THRESHOLD:
            # Merge into existing pattern
            return self._merge_pattern(
                existing=best_match,
                engagement_id=engagement_id,
                scenario_spec_id=scenario_spec_id,
                new_shares=sector_shares,
                similarity_score=best_similarity,
                import_share=import_share,
                local_content=local_content,
                duration_years=duration_years,
            )

        # Create new pattern
        auto_name = name if name else f"{project_type} pattern"
        new_pattern = ScenarioPattern(
            name=auto_name,
            description=f"Pattern extracted from engagement {engagement_id}",
            typical_sector_shares=dict(sector_shares),
            project_type=project_type,
            engagement_count=1,
            confidence="low",
            typical_import_share=import_share,
            typical_local_content=local_content,
            typical_duration_years=duration_years,
            contributing_engagement_ids=[engagement_id],
            contributing_scenario_ids=[scenario_spec_id],
        )
        self._patterns.append(new_pattern)
        return new_pattern

    # ------------------------------------------------------------------
    # Suggest
    # ------------------------------------------------------------------

    def suggest_template(
        self,
        project_type: str,
    ) -> ScenarioPattern | None:
        """Suggest a starting template for a new engagement.

        Returns the pattern with highest engagement_count for the
        project_type. Returns ``None`` if no patterns exist for the type.

        Parameters
        ----------
        project_type:
            The project type to find a template for.

        Returns
        -------
        ScenarioPattern | None
            Best template or None.
        """
        candidates = [
            p for p in self._patterns if p.project_type == project_type
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.engagement_count)

    # ------------------------------------------------------------------
    # Similarity
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
        """Compute cosine similarity between two sector share vectors.

        Treats the dicts as sparse vectors. For shared keys, multiply
        values; for non-shared keys, contribution is 0.

        Parameters
        ----------
        a:
            First sector share vector.
        b:
            Second sector share vector.

        Returns
        -------
        float
            Cosine similarity in [0, 1]. Returns 0.0 for empty vectors.
        """
        if not a or not b:
            return 0.0

        # Compute dot product (only shared keys contribute)
        all_keys = set(a) | set(b)
        dot_product = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in all_keys)

        # Compute magnitudes
        mag_a = math.sqrt(sum(v * v for v in a.values()))
        mag_b = math.sqrt(sum(v * v for v in b.values()))

        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        return dot_product / (mag_a * mag_b)

    # ------------------------------------------------------------------
    # Internal merge logic
    # ------------------------------------------------------------------

    def _merge_pattern(
        self,
        existing: ScenarioPattern,
        engagement_id: UUID,
        scenario_spec_id: UUID,
        new_shares: dict[str, float],
        similarity_score: float,
        import_share: float | None = None,
        local_content: float | None = None,
        duration_years: int | None = None,
    ) -> ScenarioPattern:
        """Merge new engagement data into an existing pattern.

        Uses rolling average: ``(old * count + new) / (count + 1)``
        for sector shares and optional numeric fields.

        Parameters
        ----------
        existing:
            The pattern to merge into.
        engagement_id:
            The engagement being merged.
        scenario_spec_id:
            The scenario spec being merged.
        new_shares:
            Sector shares from the new engagement.
        similarity_score:
            Cosine similarity that triggered the merge.
        import_share:
            Optional import share from the new engagement.
        local_content:
            Optional local content from the new engagement.
        duration_years:
            Optional duration from the new engagement.

        Returns
        -------
        ScenarioPattern
            The updated existing pattern (mutated in-place).
        """
        count = existing.engagement_count

        # Rolling average on sector shares
        all_sectors = set(existing.typical_sector_shares) | set(new_shares)
        merged_shares: dict[str, float] = {}
        for sector in all_sectors:
            old_val = existing.typical_sector_shares.get(sector, 0.0)
            new_val = new_shares.get(sector, 0.0)
            merged_shares[sector] = (old_val * count + new_val) / (count + 1)
        existing.typical_sector_shares = merged_shares

        # Rolling average on optional numeric fields
        if import_share is not None:
            if existing.typical_import_share is not None:
                existing.typical_import_share = (
                    existing.typical_import_share * count + import_share
                ) / (count + 1)
            else:
                existing.typical_import_share = import_share

        if local_content is not None:
            if existing.typical_local_content is not None:
                existing.typical_local_content = (
                    existing.typical_local_content * count + local_content
                ) / (count + 1)
            else:
                existing.typical_local_content = local_content

        if duration_years is not None:
            if existing.typical_duration_years is not None:
                existing.typical_duration_years = round(
                    (existing.typical_duration_years * count + duration_years)
                    / (count + 1)
                )
            else:
                existing.typical_duration_years = duration_years

        # Update lineage
        existing.engagement_count = count + 1
        existing.contributing_engagement_ids.append(engagement_id)
        existing.contributing_scenario_ids.append(scenario_spec_id)
        existing.last_used_at = utc_now()

        # Record merge history
        merge_entry = {
            "merged_from": str(engagement_id),
            "similarity_score": similarity_score,
            "date": utc_now().isoformat(),
        }
        if existing.merge_history is None:
            existing.merge_history = []
        existing.merge_history.append(merge_entry)

        # Update confidence based on engagement count
        if existing.engagement_count >= 5:
            existing.confidence = "high"
        elif existing.engagement_count >= 3:
            existing.confidence = "medium"

        return existing
