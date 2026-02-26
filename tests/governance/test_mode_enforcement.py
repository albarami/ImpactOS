"""Tests for sandbox/governed mode enforcement (MVP-5).

Covers: sandbox watermarking, governed mode prerequisites,
one-way promotion from sandbox to governed.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.mode_enforcement import (
    DRAFT_WATERMARK,
    GovernedCheck,
    ModeEnforcer,
    PromotionResult,
)
from src.models.common import AssumptionStatus, ClaimStatus, ClaimType, ExportMode
from src.models.governance import Assumption, AssumptionRange, Claim
from src.models.run import RunSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = uuid7()


def _make_run_snapshot(**overrides: object) -> RunSnapshot:
    defaults: dict[str, object] = {
        "run_id": RUN_ID,
        "model_version_id": uuid7(),
        "taxonomy_version_id": uuid7(),
        "concordance_version_id": uuid7(),
        "mapping_library_version_id": uuid7(),
        "assumption_library_version_id": uuid7(),
        "prompt_pack_version_id": uuid7(),
    }
    defaults.update(overrides)
    return RunSnapshot(**defaults)  # type: ignore[arg-type]


def _make_approved_assumption() -> Assumption:
    return Assumption(
        type="IMPORT_SHARE",
        value=0.35,
        units="ratio",
        justification="Based on data.",
        status=AssumptionStatus.APPROVED,
        range=AssumptionRange(min=0.2, max=0.5),
        approved_by=uuid7(),
    )


def _make_draft_assumption() -> Assumption:
    return Assumption(
        type="IMPORT_SHARE",
        value=0.35,
        units="ratio",
        justification="Based on data.",
    )


def _make_supported_claim() -> Claim:
    return Claim(
        text="GDP impact is SAR 4.2 billion.",
        claim_type=ClaimType.MODEL,
        status=ClaimStatus.SUPPORTED,
    )


def _make_unresolved_claim() -> Claim:
    return Claim(
        text="Unresolved claim.",
        claim_type=ClaimType.MODEL,
        status=ClaimStatus.NEEDS_EVIDENCE,
    )


# ===================================================================
# Sandbox mode
# ===================================================================


class TestSandboxMode:
    """Sandbox outputs always watermarked."""

    def test_sandbox_watermark_text(self) -> None:
        assert DRAFT_WATERMARK == "DRAFT \u2014 FAILS NFF GOVERNANCE"

    def test_sandbox_is_always_allowed(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_sandbox()
        assert result.allowed is True
        assert result.watermark == DRAFT_WATERMARK


# ===================================================================
# Governed mode prerequisites
# ===================================================================


class TestGovernedMode:
    """Governed mode requires approved assumptions + resolved claims +
    locked mappings + valid RunSnapshot."""

    def test_governed_passes_all_checks(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_approved_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.allowed is True
        assert len(result.blocking_reasons) == 0

    def test_governed_blocks_unapproved_assumptions(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_draft_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.allowed is False
        assert any("assumption" in r.lower() for r in result.blocking_reasons)

    def test_governed_blocks_unresolved_claims(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_approved_assumption()],
            claims=[_make_unresolved_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.allowed is False
        assert any("claim" in r.lower() for r in result.blocking_reasons)

    def test_governed_blocks_unlocked_mappings(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_approved_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=False,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.allowed is False
        assert any("mapping" in r.lower() for r in result.blocking_reasons)

    def test_governed_blocks_missing_snapshot(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_approved_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=None,
        )
        assert result.allowed is False
        assert any("snapshot" in r.lower() for r in result.blocking_reasons)

    def test_governed_accumulates_all_reasons(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[_make_draft_assumption()],
            claims=[_make_unresolved_claim()],
            mappings_locked=False,
            run_snapshot=None,
        )
        assert result.allowed is False
        assert len(result.blocking_reasons) == 4

    def test_governed_empty_assumptions_and_claims_passes(self) -> None:
        """No assumptions and no claims = nothing to block."""
        enforcer = ModeEnforcer()
        result = enforcer.check_governed(
            assumptions=[],
            claims=[],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.allowed is True


# ===================================================================
# One-way promotion: sandbox → governed
# ===================================================================


class TestPromotion:
    """One-way promotion from sandbox to governed."""

    def test_promote_succeeds_when_governed_passes(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.promote_to_governed(
            current_mode=ExportMode.SANDBOX,
            assumptions=[_make_approved_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.promoted is True
        assert result.new_mode == ExportMode.GOVERNED

    def test_promote_fails_when_governed_blocks(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.promote_to_governed(
            current_mode=ExportMode.SANDBOX,
            assumptions=[_make_draft_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.promoted is False
        assert result.new_mode == ExportMode.SANDBOX

    def test_already_governed_no_op(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.promote_to_governed(
            current_mode=ExportMode.GOVERNED,
            assumptions=[_make_approved_assumption()],
            claims=[_make_supported_claim()],
            mappings_locked=True,
            run_snapshot=_make_run_snapshot(),
        )
        assert result.promoted is True
        assert result.new_mode == ExportMode.GOVERNED

    def test_cannot_demote_governed_to_sandbox(self) -> None:
        """One-way: governed can never go back to sandbox."""
        enforcer = ModeEnforcer()
        with pytest.raises(ValueError, match="Cannot demote"):
            enforcer.demote_to_sandbox(current_mode=ExportMode.GOVERNED)

    def test_sandbox_stays_sandbox(self) -> None:
        enforcer = ModeEnforcer()
        result = enforcer.demote_to_sandbox(current_mode=ExportMode.SANDBOX)
        assert result == ExportMode.SANDBOX
