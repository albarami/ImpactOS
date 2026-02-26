"""Publication gate — MVP-5 Section 12 / 11.3.

Check all claims for a run — block export if ANY claim is unresolved
(EXTRACTED or NEEDS_EVIDENCE). Pass only when all claims are
SUPPORTED / APPROVED_FOR_EXPORT / REWRITTEN_AS_ASSUMPTION / DELETED.

This is the non-negotiable enforcement point for NFF governance.
Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field
from uuid import UUID

from src.models.common import ClaimStatus
from src.models.governance import Claim


# States that count as "resolved" — eligible for publication
_RESOLVED_STATES = frozenset({
    ClaimStatus.SUPPORTED,
    ClaimStatus.APPROVED_FOR_EXPORT,
    ClaimStatus.REWRITTEN_AS_ASSUMPTION,
    ClaimStatus.DELETED,
})

# States that block publication
_BLOCKING_STATES = frozenset({
    ClaimStatus.EXTRACTED,
    ClaimStatus.NEEDS_EVIDENCE,
})


@dataclass(frozen=True)
class BlockingReason:
    """Why a specific claim blocks publication."""

    claim_id: UUID
    current_status: ClaimStatus
    reason: str


@dataclass
class GateResult:
    """Result of the publication gate check."""

    passed: bool
    total_claims: int
    blocking_reasons: list[BlockingReason] = field(default_factory=list)

    @property
    def resolved_count(self) -> int:
        return self.total_claims - len(self.blocking_reasons)

    @property
    def unresolved_count(self) -> int:
        return len(self.blocking_reasons)


class PublicationGate:
    """NFF publication gate — the non-negotiable enforcement point.

    No claim in EXTRACTED or NEEDS_EVIDENCE may pass. Every claim must
    be traceable. No free facts in client deliverables.
    """

    def check(self, claims: list[Claim]) -> GateResult:
        """Check all claims — block if any are unresolved.

        Returns:
            GateResult with passed=True if all claims are resolved,
            or passed=False with a list of blocking reasons.
        """
        blocking: list[BlockingReason] = []

        for claim in claims:
            if claim.status in _BLOCKING_STATES:
                blocking.append(
                    BlockingReason(
                        claim_id=claim.claim_id,
                        current_status=claim.status,
                        reason=f"Claim '{claim.text[:80]}' is {claim.status.value} — must be resolved before export.",
                    )
                )

        return GateResult(
            passed=len(blocking) == 0,
            total_claims=len(claims),
            blocking_reasons=blocking,
        )
