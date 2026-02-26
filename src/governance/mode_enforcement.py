"""Sandbox / Governed mode enforcement — MVP-5 Section 11.4.

Sandbox outputs always watermarked "DRAFT — FAILS NFF GOVERNANCE".
Governed mode requires approved assumptions + resolved claims +
locked mappings + valid RunSnapshot.
One-way promotion from sandbox to governed.

Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field

from src.models.common import AssumptionStatus, ClaimStatus, ExportMode
from src.models.governance import Assumption, Claim
from src.models.run import RunSnapshot


DRAFT_WATERMARK = "DRAFT \u2014 FAILS NFF GOVERNANCE"

# Claim states that count as resolved for governed mode
_RESOLVED_CLAIM_STATES = frozenset({
    ClaimStatus.SUPPORTED,
    ClaimStatus.APPROVED_FOR_EXPORT,
    ClaimStatus.REWRITTEN_AS_ASSUMPTION,
    ClaimStatus.DELETED,
})


@dataclass
class SandboxResult:
    """Result of sandbox mode check."""

    allowed: bool = True
    watermark: str = DRAFT_WATERMARK


@dataclass
class GovernedCheck:
    """Result of governed mode prerequisite check."""

    allowed: bool
    blocking_reasons: list[str] = field(default_factory=list)


@dataclass
class PromotionResult:
    """Result of attempting to promote from sandbox to governed."""

    promoted: bool
    new_mode: ExportMode
    blocking_reasons: list[str] = field(default_factory=list)


class ModeEnforcer:
    """Enforce sandbox vs governed mode rules.

    Sandbox is always allowed but watermarked.
    Governed requires all four prerequisites.
    Promotion is one-way: sandbox → governed (never back).
    """

    def check_sandbox(self) -> SandboxResult:
        """Sandbox is always allowed — but outputs are watermarked."""
        return SandboxResult()

    def check_governed(
        self,
        *,
        assumptions: list[Assumption],
        claims: list[Claim],
        mappings_locked: bool,
        run_snapshot: RunSnapshot | None,
    ) -> GovernedCheck:
        """Check all prerequisites for governed mode.

        Requirements:
        1. All assumptions must be APPROVED
        2. All claims must be resolved (SUPPORTED/APPROVED_FOR_EXPORT/REWRITTEN/DELETED)
        3. Mappings must be locked
        4. A valid RunSnapshot must exist
        """
        reasons: list[str] = []

        # 1. Approved assumptions
        unapproved = [a for a in assumptions if a.status != AssumptionStatus.APPROVED]
        if unapproved:
            reasons.append(
                f"{len(unapproved)} assumption(s) not approved — all must be APPROVED for governed mode."
            )

        # 2. Resolved claims
        unresolved = [c for c in claims if c.status not in _RESOLVED_CLAIM_STATES]
        if unresolved:
            reasons.append(
                f"{len(unresolved)} claim(s) unresolved — all must be SUPPORTED/APPROVED_FOR_EXPORT/DELETED."
            )

        # 3. Locked mappings
        if not mappings_locked:
            reasons.append("Mapping decisions are not locked — must be locked for governed mode.")

        # 4. Valid RunSnapshot
        if run_snapshot is None:
            reasons.append("No valid RunSnapshot — a reproducibility snapshot is required.")

        return GovernedCheck(
            allowed=len(reasons) == 0,
            blocking_reasons=reasons,
        )

    def promote_to_governed(
        self,
        *,
        current_mode: ExportMode,
        assumptions: list[Assumption],
        claims: list[Claim],
        mappings_locked: bool,
        run_snapshot: RunSnapshot | None,
    ) -> PromotionResult:
        """Attempt one-way promotion from sandbox to governed.

        If already governed, this is a no-op success.
        """
        if current_mode == ExportMode.GOVERNED:
            return PromotionResult(promoted=True, new_mode=ExportMode.GOVERNED)

        check = self.check_governed(
            assumptions=assumptions,
            claims=claims,
            mappings_locked=mappings_locked,
            run_snapshot=run_snapshot,
        )

        if check.allowed:
            return PromotionResult(promoted=True, new_mode=ExportMode.GOVERNED)

        return PromotionResult(
            promoted=False,
            new_mode=ExportMode.SANDBOX,
            blocking_reasons=check.blocking_reasons,
        )

    @staticmethod
    def demote_to_sandbox(*, current_mode: ExportMode) -> ExportMode:
        """Attempt to demote — governed can never go back to sandbox.

        Raises:
            ValueError: If attempting to demote from governed.
        """
        if current_mode == ExportMode.GOVERNED:
            msg = "Cannot demote from GOVERNED to SANDBOX — promotion is one-way."
            raise ValueError(msg)
        return ExportMode.SANDBOX
