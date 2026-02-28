"""Engagement context — captures the business setting for depth analysis.

The Al-Muhasabi structured reasoning methodology and framework are the
intellectual property of Salim Al-Barami, licensed to Strategic Gears
for use within ImpactOS. The software implementation, prompt engineering,
and system integration are part of the ImpactOS platform.

EngagementContext feeds Step 1 (Khawatir) with structured context about
the engagement, so generated directions are relevant to the client's
sector, geography, and analytical questions.
"""

from uuid import UUID

from pydantic import Field

from src.models.common import (
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)


class EngagementContext(ImpactOSBase):
    """Structured business context for depth engine analysis.

    Captures the engagement parameters that inform scenario direction
    generation. Passed to the orchestrator as part of the initial context.

    All fields are optional because the depth engine can run with
    minimal context (just workspace_id) and use heuristic fallback.
    """

    context_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID | None = None
    engagement_name: str | None = None
    client_sector: str | None = Field(
        default=None,
        description="Primary ISIC section code (e.g., 'F' for Construction).",
    )
    target_sectors: list[str] = Field(
        default_factory=list,
        description="ISIC section codes relevant to this analysis.",
    )
    geography: str = Field(
        default="SAU",
        description="ISO 3166-1 alpha-3 country code (default Saudi Arabia).",
    )
    base_year: int | None = None
    key_questions: list[str] = Field(
        default_factory=list,
        description="Analytical questions the engagement needs to answer.",
    )
    existing_assumptions: list[str] = Field(
        default_factory=list,
        description="Known assumptions to challenge during Mujahada.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Hard constraints (e.g., data availability, sector coverage).",
    )
    notes: str | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    def to_context_dict(self) -> dict:
        """Convert to a dict suitable for the orchestrator context parameter.

        Returns only non-None fields to keep the context clean.
        """
        result: dict = {}
        if self.engagement_name:
            result["engagement_name"] = self.engagement_name
        if self.client_sector:
            result["client_sector"] = self.client_sector
        if self.target_sectors:
            result["target_sectors"] = self.target_sectors
        if self.geography:
            result["geography"] = self.geography
        if self.base_year is not None:
            result["base_year"] = self.base_year
        if self.key_questions:
            result["key_questions"] = self.key_questions
        if self.existing_assumptions:
            result["existing_assumptions"] = self.existing_assumptions
        if self.constraints:
            result["constraints"] = self.constraints
        return result
