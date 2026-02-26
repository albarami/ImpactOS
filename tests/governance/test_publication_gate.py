"""Tests for publication gate (MVP-5).

Covers: check all claims for a run, block export if ANY claim is
unresolved, return blocking reasons, pass only when all claims are
SUPPORTED/APPROVED_FOR_EXPORT or DELETED.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.publication_gate import BlockingReason, GateResult, PublicationGate
from src.models.common import ClaimStatus, ClaimType
from src.models.governance import Claim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claim(
    status: ClaimStatus = ClaimStatus.SUPPORTED,
    claim_type: ClaimType = ClaimType.MODEL,
    text: str = "Some claim.",
) -> Claim:
    return Claim(text=text, claim_type=claim_type, status=status)


# ===================================================================
# Gate passes
# ===================================================================


class TestGatePasses:
    """Publication gate passes when all claims are resolved."""

    def test_all_supported_passes(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.SUPPORTED),
        ]
        result = gate.check(claims)
        assert result.passed is True

    def test_all_approved_for_export_passes(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.APPROVED_FOR_EXPORT),
            _make_claim(status=ClaimStatus.APPROVED_FOR_EXPORT),
        ]
        result = gate.check(claims)
        assert result.passed is True

    def test_deleted_claims_pass(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.DELETED),
            _make_claim(status=ClaimStatus.SUPPORTED),
        ]
        result = gate.check(claims)
        assert result.passed is True

    def test_mix_of_supported_approved_deleted_passes(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.APPROVED_FOR_EXPORT),
            _make_claim(status=ClaimStatus.DELETED),
        ]
        result = gate.check(claims)
        assert result.passed is True

    def test_empty_claims_passes(self) -> None:
        gate = PublicationGate()
        result = gate.check([])
        assert result.passed is True

    def test_rewritten_as_assumption_passes(self) -> None:
        """REWRITTEN_AS_ASSUMPTION is a resolved state — it passes."""
        gate = PublicationGate()
        claims = [_make_claim(status=ClaimStatus.REWRITTEN_AS_ASSUMPTION)]
        result = gate.check(claims)
        assert result.passed is True


# ===================================================================
# Gate blocks
# ===================================================================


class TestGateBlocks:
    """Publication gate blocks when unresolved claims exist."""

    def test_extracted_blocks(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.EXTRACTED, text="Unclassified claim."),
            _make_claim(status=ClaimStatus.SUPPORTED),
        ]
        result = gate.check(claims)
        assert result.passed is False

    def test_needs_evidence_blocks(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE, text="Missing evidence."),
        ]
        result = gate.check(claims)
        assert result.passed is False

    def test_single_unresolved_blocks_all(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE, text="One bad apple."),
        ]
        result = gate.check(claims)
        assert result.passed is False


# ===================================================================
# Blocking reasons
# ===================================================================


class TestBlockingReasons:
    """Gate returns detailed blocking reasons."""

    def test_blocking_reasons_list(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.EXTRACTED, text="Unclassified claim."),
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE, text="Missing evidence claim."),
        ]
        result = gate.check(claims)
        assert len(result.blocking_reasons) == 2

    def test_blocking_reason_contains_claim_id(self) -> None:
        gate = PublicationGate()
        claim = _make_claim(status=ClaimStatus.EXTRACTED, text="Bad claim.")
        result = gate.check([claim])
        assert result.blocking_reasons[0].claim_id == claim.claim_id

    def test_blocking_reason_contains_status(self) -> None:
        gate = PublicationGate()
        claim = _make_claim(status=ClaimStatus.NEEDS_EVIDENCE, text="Needs work.")
        result = gate.check([claim])
        assert result.blocking_reasons[0].current_status == ClaimStatus.NEEDS_EVIDENCE

    def test_blocking_reason_contains_text(self) -> None:
        gate = PublicationGate()
        claim = _make_claim(status=ClaimStatus.EXTRACTED, text="Specific claim text.")
        result = gate.check([claim])
        assert "Specific claim text" in result.blocking_reasons[0].reason

    def test_no_blocking_reasons_when_passed(self) -> None:
        gate = PublicationGate()
        claims = [_make_claim(status=ClaimStatus.SUPPORTED)]
        result = gate.check(claims)
        assert len(result.blocking_reasons) == 0


# ===================================================================
# GateResult summary
# ===================================================================


class TestGateResult:
    """GateResult provides summary statistics."""

    def test_total_claims(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE),
        ]
        result = gate.check(claims)
        assert result.total_claims == 2

    def test_resolved_count(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.APPROVED_FOR_EXPORT),
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE),
        ]
        result = gate.check(claims)
        assert result.resolved_count == 2

    def test_unresolved_count(self) -> None:
        gate = PublicationGate()
        claims = [
            _make_claim(status=ClaimStatus.SUPPORTED),
            _make_claim(status=ClaimStatus.EXTRACTED),
            _make_claim(status=ClaimStatus.NEEDS_EVIDENCE),
        ]
        result = gate.check(claims)
        assert result.unresolved_count == 2
