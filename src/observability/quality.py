"""Quality metrics — MVP-7 Section 21.

Percentage of claims supported vs rewritten in NFF, revision cycles
driven by sourcing disputes, sensitivity coverage rate (% of assumptions
with ranges), mapping confidence distribution per engagement.

Deterministic — no LLM calls.
"""

from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from src.models.common import ClaimStatus, MappingConfidenceBand
from src.models.governance import Claim


@dataclass
class QualitySnapshot:
    """Snapshot of claim quality metrics."""

    total_claims: int
    supported_count: int
    rewritten_count: int
    supported_pct: float
    rewritten_pct: float


@dataclass
class RevisionRecord:
    """Record of a revision cycle."""

    engagement_id: UUID
    reason: str


class QualityMetrics:
    """Compute quality metrics for governance and pilot assessment."""

    def __init__(self) -> None:
        self._revisions: list[RevisionRecord] = []

    # ----- Claim quality -----

    @staticmethod
    def compute_claim_quality(claims: list[Claim]) -> QualitySnapshot:
        """Compute supported vs rewritten percentages."""
        total = len(claims)
        if total == 0:
            return QualitySnapshot(
                total_claims=0,
                supported_count=0,
                rewritten_count=0,
                supported_pct=0.0,
                rewritten_pct=0.0,
            )
        supported = sum(1 for c in claims if c.status == ClaimStatus.SUPPORTED)
        rewritten = sum(1 for c in claims if c.status == ClaimStatus.REWRITTEN_AS_ASSUMPTION)
        return QualitySnapshot(
            total_claims=total,
            supported_count=supported,
            rewritten_count=rewritten,
            supported_pct=supported / total,
            rewritten_pct=rewritten / total,
        )

    # ----- Revision cycles -----

    def record_revision_cycle(self, *, engagement_id: UUID, reason: str) -> None:
        """Record a revision cycle."""
        self._revisions.append(RevisionRecord(engagement_id=engagement_id, reason=reason))

    def total_revision_cycles(self) -> int:
        return len(self._revisions)

    def revision_cycles_for(self, engagement_id: UUID) -> int:
        return sum(1 for r in self._revisions if r.engagement_id == engagement_id)

    def sourcing_dispute_count(self) -> int:
        """Count revision cycles specifically from sourcing disputes."""
        return sum(1 for r in self._revisions if "sourcing dispute" in r.reason.lower())

    # ----- Sensitivity coverage -----

    @staticmethod
    def sensitivity_coverage(assumptions: list[dict]) -> float:
        """Percentage of assumptions that have sensitivity ranges."""
        if not assumptions:
            return 0.0
        with_range = sum(
            1 for a in assumptions
            if a.get("range_min") is not None and a.get("range_max") is not None
        )
        return with_range / len(assumptions)

    # ----- Mapping confidence -----

    @staticmethod
    def confidence_distribution(
        confidences: list[MappingConfidenceBand],
    ) -> dict[str, float]:
        """Compute distribution of mapping confidence bands."""
        if not confidences:
            return {"HIGH": 0.0, "MEDIUM": 0.0, "LOW": 0.0}
        counts: Counter[str] = Counter()
        for c in confidences:
            counts[c.value] += 1
        total = len(confidences)
        return {
            "HIGH": counts.get("HIGH", 0) / total,
            "MEDIUM": counts.get("MEDIUM", 0) / total,
            "LOW": counts.get("LOW", 0) / total,
        }
