"""Tests for quality metrics (MVP-7).

Covers: % claims supported vs rewritten, revision cycles from sourcing
disputes, sensitivity coverage rate, mapping confidence distribution.
"""

import pytest
from uuid_extensions import uuid7

from src.observability.quality import QualityMetrics, QualitySnapshot
from src.models.common import ClaimStatus, ClaimType, MappingConfidenceBand
from src.models.governance import Claim


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_claims(
    supported: int = 5,
    rewritten: int = 2,
    needs_evidence: int = 1,
    deleted: int = 0,
) -> list[Claim]:
    claims: list[Claim] = []
    for _ in range(supported):
        claims.append(Claim(text="Supported.", claim_type=ClaimType.MODEL, status=ClaimStatus.SUPPORTED))
    for _ in range(rewritten):
        claims.append(Claim(text="Rewritten.", claim_type=ClaimType.ASSUMPTION, status=ClaimStatus.REWRITTEN_AS_ASSUMPTION))
    for _ in range(needs_evidence):
        claims.append(Claim(text="Needs evidence.", claim_type=ClaimType.SOURCE_FACT, status=ClaimStatus.NEEDS_EVIDENCE))
    for _ in range(deleted):
        claims.append(Claim(text="Deleted.", claim_type=ClaimType.MODEL, status=ClaimStatus.DELETED))
    return claims


# ===================================================================
# Claim quality metrics
# ===================================================================


class TestClaimQuality:
    """Percentage of claims supported vs rewritten."""

    def test_supported_pct(self) -> None:
        qm = QualityMetrics()
        snapshot = qm.compute_claim_quality(_make_claims(supported=8, rewritten=2, needs_evidence=0))
        assert snapshot.supported_pct == pytest.approx(0.8)

    def test_rewritten_pct(self) -> None:
        qm = QualityMetrics()
        snapshot = qm.compute_claim_quality(_make_claims(supported=7, rewritten=3, needs_evidence=0))
        assert snapshot.rewritten_pct == pytest.approx(0.3)

    def test_empty_claims(self) -> None:
        qm = QualityMetrics()
        snapshot = qm.compute_claim_quality([])
        assert snapshot.supported_pct == 0.0
        assert snapshot.rewritten_pct == 0.0

    def test_total_claims(self) -> None:
        qm = QualityMetrics()
        snapshot = qm.compute_claim_quality(_make_claims(supported=5, rewritten=2, needs_evidence=1))
        assert snapshot.total_claims == 8


# ===================================================================
# Revision cycles
# ===================================================================


class TestRevisionCycles:
    """Track revision cycles from sourcing disputes."""

    def test_record_revision_cycle(self) -> None:
        qm = QualityMetrics()
        qm.record_revision_cycle(engagement_id=uuid7(), reason="Sourcing dispute")
        assert qm.total_revision_cycles() == 1

    def test_multiple_cycles(self) -> None:
        qm = QualityMetrics()
        eid = uuid7()
        qm.record_revision_cycle(engagement_id=eid, reason="Dispute A")
        qm.record_revision_cycle(engagement_id=eid, reason="Dispute B")
        assert qm.revision_cycles_for(eid) == 2

    def test_sourcing_dispute_count(self) -> None:
        qm = QualityMetrics()
        qm.record_revision_cycle(engagement_id=uuid7(), reason="sourcing dispute")
        qm.record_revision_cycle(engagement_id=uuid7(), reason="formatting issue")
        assert qm.sourcing_dispute_count() == 1


# ===================================================================
# Sensitivity coverage
# ===================================================================


class TestSensitivityCoverage:
    """Sensitivity coverage rate (% of assumptions with ranges)."""

    def test_full_coverage(self) -> None:
        qm = QualityMetrics()
        assumptions = [
            {"name": "A", "range_min": 0.5, "range_max": 0.8},
            {"name": "B", "range_min": 0.2, "range_max": 0.4},
        ]
        assert qm.sensitivity_coverage(assumptions) == pytest.approx(1.0)

    def test_partial_coverage(self) -> None:
        qm = QualityMetrics()
        assumptions = [
            {"name": "A", "range_min": 0.5, "range_max": 0.8},
            {"name": "B"},  # No range
        ]
        assert qm.sensitivity_coverage(assumptions) == pytest.approx(0.5)

    def test_no_assumptions(self) -> None:
        qm = QualityMetrics()
        assert qm.sensitivity_coverage([]) == 0.0


# ===================================================================
# Mapping confidence distribution
# ===================================================================


class TestMappingConfidence:
    """Mapping confidence distribution per engagement."""

    def test_confidence_distribution(self) -> None:
        qm = QualityMetrics()
        confidences = [
            MappingConfidenceBand.HIGH,
            MappingConfidenceBand.HIGH,
            MappingConfidenceBand.MEDIUM,
            MappingConfidenceBand.LOW,
        ]
        dist = qm.confidence_distribution(confidences)
        assert dist["HIGH"] == pytest.approx(0.5)
        assert dist["MEDIUM"] == pytest.approx(0.25)
        assert dist["LOW"] == pytest.approx(0.25)

    def test_empty_distribution(self) -> None:
        qm = QualityMetrics()
        dist = qm.confidence_distribution([])
        assert dist["HIGH"] == 0.0
        assert dist["MEDIUM"] == 0.0
        assert dist["LOW"] == 0.0
