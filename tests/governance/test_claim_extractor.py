"""Tests for claim extraction service (MVP-5).

Covers: parsing draft narrative into atomic claims, classification by type,
flagging claims that need evidence.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.claim_extractor import ClaimExtractor, ExtractionResult
from src.models.common import ClaimStatus, ClaimType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WORKSPACE_ID = uuid7()
RUN_ID = uuid7()


def _draft_text_multi() -> str:
    return (
        "The project will generate 12,500 direct jobs by 2030. "
        "Steel prices increased 15% in Q3 2024 according to SAMA. "
        "We assume a 65% domestic content share for construction. "
        "We recommend phasing investments over 5 years to reduce risk."
    )


def _draft_text_single_model() -> str:
    return "Total GDP impact is estimated at SAR 4.2 billion."


def _draft_text_empty() -> str:
    return ""


def _draft_text_whitespace() -> str:
    return "   \n\n   "


# ===================================================================
# Extraction basics
# ===================================================================


class TestClaimExtraction:
    """Parse draft narrative into atomic claims."""

    def test_extracts_multiple_claims(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert isinstance(result, ExtractionResult)
        assert len(result.claims) == 4

    def test_each_claim_has_text(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        for claim in result.claims:
            assert len(claim.text) > 0

    def test_single_sentence_yields_one_claim(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_single_model(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert len(result.claims) == 1

    def test_empty_text_yields_no_claims(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_empty(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert len(result.claims) == 0

    def test_whitespace_only_yields_no_claims(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_whitespace(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert len(result.claims) == 0


# ===================================================================
# Classification
# ===================================================================


class TestClaimClassification:
    """Classify claims as MODEL/SOURCE_FACT/ASSUMPTION/RECOMMENDATION."""

    def test_model_fact_classified(self) -> None:
        """Sentences with model output language → MODEL."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="The project will generate 12,500 direct jobs by 2030.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.claims[0].claim_type == ClaimType.MODEL

    def test_source_fact_classified(self) -> None:
        """Sentences citing external data sources → SOURCE_FACT."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="Steel prices increased 15% in Q3 2024 according to SAMA.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.claims[0].claim_type == ClaimType.SOURCE_FACT

    def test_assumption_classified(self) -> None:
        """Sentences with assumption language → ASSUMPTION."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="We assume a 65% domestic content share for construction.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.claims[0].claim_type == ClaimType.ASSUMPTION

    def test_recommendation_classified(self) -> None:
        """Sentences with recommendation language → RECOMMENDATION."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="We recommend phasing investments over 5 years to reduce risk.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.claims[0].claim_type == ClaimType.RECOMMENDATION


# ===================================================================
# Evidence flagging
# ===================================================================


class TestEvidenceFlagging:
    """Flag claims that need evidence."""

    def test_model_claims_need_evidence(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="Total GDP impact is estimated at SAR 4.2 billion.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        claim = result.claims[0]
        assert claim.status == ClaimStatus.NEEDS_EVIDENCE

    def test_source_fact_needs_evidence(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="Steel prices increased 15% according to SAMA.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        claim = result.claims[0]
        assert claim.status == ClaimStatus.NEEDS_EVIDENCE

    def test_assumption_stays_extracted(self) -> None:
        """Assumptions don't need external evidence — they are declared."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="We assume a 65% domestic content share.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        claim = result.claims[0]
        assert claim.status == ClaimStatus.EXTRACTED

    def test_recommendation_stays_extracted(self) -> None:
        """Recommendations don't need evidence linking initially."""
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text="We recommend a phased approach.",
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        claim = result.claims[0]
        assert claim.status == ClaimStatus.EXTRACTED


# ===================================================================
# ExtractionResult summary
# ===================================================================


class TestExtractionResult:
    """ExtractionResult provides summary counts."""

    def test_total_count(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.total == 4

    def test_needs_evidence_count(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        # MODEL and SOURCE_FACT claims need evidence (2 of 4)
        assert result.needs_evidence_count == 2

    def test_by_type_breakdown(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        assert result.by_type[ClaimType.MODEL] == 1
        assert result.by_type[ClaimType.SOURCE_FACT] == 1
        assert result.by_type[ClaimType.ASSUMPTION] == 1
        assert result.by_type[ClaimType.RECOMMENDATION] == 1

    def test_unique_claim_ids(self) -> None:
        extractor = ClaimExtractor()
        result = extractor.extract(
            draft_text=_draft_text_multi(),
            workspace_id=WORKSPACE_ID,
            run_id=RUN_ID,
        )
        ids = [c.claim_id for c in result.claims]
        assert len(set(ids)) == len(ids)
