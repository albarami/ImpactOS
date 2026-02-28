"""Engagement memory for the Knowledge Flywheel (Task 11).

Engagement memories capture what happened during an engagement that
future engagements should know — client challenges, evidence requests,
methodology disputes, and how they were resolved. They feed the flywheel
by turning one-off lessons into reusable organizational knowledge.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from src.flywheel.models import PromotionStatus, ReuseScopeLevel
from src.flywheel.stores import InMemoryAppendOnlyStore
from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class EngagementMemory(ImpactOSBase):
    """What happened in an engagement that future engagements should know.

    Example: "Client challenged the import share for steel fabrication.
    Required additional evidence from customs data."
    """

    memory_id: UUIDv7 = Field(default_factory=new_uuid7)
    engagement_id: UUID
    category: str  # "challenge", "acceptance", "evidence_request", "methodology_dispute"
    description: str
    sector_code: str | None = None
    resolution: str | None = None
    time_to_resolve: str | None = None  # "3 days", "immediate"
    lesson_learned: str | None = None
    created_by: UUID
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    tags: list[str] = Field(default_factory=list)
    # Promotion path (Amendment 8)
    promoted_to: UUID | None = None  # pattern_id or governance rule
    promotion_status: PromotionStatus = PromotionStatus.RAW
    # Scope (Amendment 1)
    workspace_id: UUID
    source_engagement_id: UUID | None = None
    reuse_scope: ReuseScopeLevel = ReuseScopeLevel.WORKSPACE_ONLY
    sanitized_for_promotion: bool = False


class EngagementMemoryStore(InMemoryAppendOnlyStore[EngagementMemory]):
    """In-memory store for engagement memories with search methods."""

    def __init__(self) -> None:
        super().__init__(id_field="memory_id")

    def find_by_category(self, category: str) -> list[EngagementMemory]:
        """Search by category."""
        return [m for m in self._items if m.category == category]

    def find_by_sector(self, sector_code: str) -> list[EngagementMemory]:
        """Search by sector code."""
        return [m for m in self._items if m.sector_code == sector_code]

    def find_by_engagement(self, engagement_id: UUID) -> list[EngagementMemory]:
        """Search by engagement."""
        return [m for m in self._items if m.engagement_id == engagement_id]

    def find_by_tags(self, tags: list[str]) -> list[EngagementMemory]:
        """Find memories that have ANY of the given tags."""
        tag_set = set(tags)
        return [m for m in self._items if tag_set & set(m.tags)]
