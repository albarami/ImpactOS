"""Publication gate — MVP-5 Section 12 / 11.3.

Check all claims for a run — block export if ANY claim is unresolved
(EXTRACTED or NEEDS_EVIDENCE). Pass only when all claims are
SUPPORTED / APPROVED_FOR_EXPORT / REWRITTEN_AS_ASSUMPTION / DELETED.

P4-3: Also check assumptions — DRAFT assumptions block publication.
Only APPROVED or REJECTED assumptions may pass.

This is the non-negotiable enforcement point for NFF governance.
Deterministic — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from src.models.common import AssumptionStatus, ClaimStatus
from src.models.governance import Assumption, Claim

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

# P4-3: Assumption states that block publication
_ASSUMPTION_BLOCKING_STATES = frozenset({
    AssumptionStatus.DRAFT,
})


@dataclass(frozen=True)
class BlockingReason:
    """Why a specific claim or assumption blocks publication."""

    claim_id: UUID
    current_status: ClaimStatus | AssumptionStatus
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

    P4-3: No DRAFT assumption may pass — all assumptions must be
    APPROVED (with sensitivity range) or REJECTED before governed export.
    """

    def check(
        self,
        claims: list[Claim],
        *,
        assumptions: list[Assumption] | None = None,
    ) -> GateResult:
        """Check all claims and assumptions — block if any are unresolved.

        Args:
            claims: List of claims to check.
            assumptions: Optional list of assumptions to check (P4-3).

        Returns:
            GateResult with passed=True if all claims and assumptions
            are resolved, or passed=False with blocking reasons.
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

        # P4-3: Check assumptions
        if assumptions:
            for assumption in assumptions:
                if assumption.status in _ASSUMPTION_BLOCKING_STATES:
                    blocking.append(
                        BlockingReason(
                            claim_id=assumption.assumption_id,
                            current_status=assumption.status,
                            reason=(
                                f"Assumption '{assumption.type.value}' "
                                f"(value={assumption.value}) is {assumption.status.value} "
                                f"— must be APPROVED or REJECTED before export."
                            ),
                        )
                    )

        total = len(claims) + (len(assumptions) if assumptions else 0)

        return GateResult(
            passed=len(blocking) == 0,
            total_claims=total,
            blocking_reasons=blocking,
        )
