"""Tests for evidence linking service (MVP-5).

Covers: matching claims to EvidenceSnippets and ResultSet model refs,
attaching evidence_refs to claims, transitioning claims from
NEEDS_EVIDENCE to SUPPORTED.
"""

import pytest
from uuid_extensions import uuid7

from src.governance.evidence_linker import EvidenceLinker, LinkResult
from src.models.common import ClaimStatus, ClaimType, DisclosureTier
from src.models.governance import BoundingBox, Claim, EvidenceSnippet, ModelRef
from src.models.run import ResultSet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = uuid7()


def _make_snippet(**overrides: object) -> EvidenceSnippet:
    defaults: dict[str, object] = {
        "source_id": uuid7(),
        "page": 1,
        "bbox": BoundingBox(x0=0.0, y0=0.0, x1=0.5, y1=0.1),
        "extracted_text": "Steel prices increased 15% in Q3 2024.",
        "checksum": "sha256:" + "a" * 64,
    }
    defaults.update(overrides)
    return EvidenceSnippet(**defaults)  # type: ignore[arg-type]


def _make_result_set(**overrides: object) -> ResultSet:
    defaults: dict[str, object] = {
        "run_id": RUN_ID,
        "metric_type": "gdp_impact",
        "values": {"total": 4200000000.0},
    }
    defaults.update(overrides)
    return ResultSet(**defaults)  # type: ignore[arg-type]


def _make_claim(
    text: str = "Total GDP impact is SAR 4.2 billion.",
    claim_type: ClaimType = ClaimType.MODEL,
    status: ClaimStatus = ClaimStatus.NEEDS_EVIDENCE,
) -> Claim:
    return Claim(text=text, claim_type=claim_type, status=status)


# ===================================================================
# Link evidence snippets to claims
# ===================================================================


class TestLinkEvidenceSnippets:
    """Match claims to EvidenceSnippet objects."""

    def test_link_snippet_to_claim(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(
            text="Steel prices increased 15%.",
            claim_type=ClaimType.SOURCE_FACT,
        )
        snippet = _make_snippet(extracted_text="Steel prices increased 15% in Q3 2024.")
        result = linker.link_evidence(
            claims=[claim],
            snippets=[snippet],
            result_sets=[],
        )
        assert len(result.linked_claims) == 1
        linked = result.linked_claims[0]
        assert snippet.snippet_id in linked.evidence_refs

    def test_link_transitions_to_supported(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(
            text="Steel prices increased 15%.",
            claim_type=ClaimType.SOURCE_FACT,
        )
        snippet = _make_snippet(extracted_text="Steel prices increased 15% in Q3 2024.")
        result = linker.link_evidence(
            claims=[claim],
            snippets=[snippet],
            result_sets=[],
        )
        assert result.linked_claims[0].status == ClaimStatus.SUPPORTED

    def test_no_match_stays_needs_evidence(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(
            text="Unemployment will decrease by 5%.",
            claim_type=ClaimType.MODEL,
        )
        snippet = _make_snippet(extracted_text="Steel prices increased 15% in Q3 2024.")
        result = linker.link_evidence(
            claims=[claim],
            snippets=[snippet],
            result_sets=[],
        )
        assert result.linked_claims[0].status == ClaimStatus.NEEDS_EVIDENCE
        assert len(result.linked_claims[0].evidence_refs) == 0

    def test_multiple_snippets_linked(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(text="Steel production capacity.", claim_type=ClaimType.SOURCE_FACT)
        s1 = _make_snippet(extracted_text="Steel production capacity constraints.")
        s2 = _make_snippet(extracted_text="Steel sector output growth.")
        result = linker.link_evidence(
            claims=[claim],
            snippets=[s1, s2],
            result_sets=[],
        )
        linked = result.linked_claims[0]
        assert s1.snippet_id in linked.evidence_refs
        assert linked.status == ClaimStatus.SUPPORTED


# ===================================================================
# Link model refs to claims
# ===================================================================


class TestLinkModelRefs:
    """Match claims to ResultSet model refs."""

    def test_link_result_set_to_model_claim(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(text="GDP impact is SAR 4.2 billion.", claim_type=ClaimType.MODEL)
        rs = _make_result_set(metric_type="gdp_impact", values={"total": 4.2e9})
        result = linker.link_evidence(
            claims=[claim],
            snippets=[],
            result_sets=[rs],
        )
        linked = result.linked_claims[0]
        assert len(linked.model_refs) >= 1
        assert linked.status == ClaimStatus.SUPPORTED

    def test_result_set_no_match(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(text="Unemployment will decrease.", claim_type=ClaimType.MODEL)
        rs = _make_result_set(metric_type="gdp_impact", values={"total": 4.2e9})
        result = linker.link_evidence(
            claims=[claim],
            snippets=[],
            result_sets=[rs],
        )
        linked = result.linked_claims[0]
        assert len(linked.model_refs) == 0


# ===================================================================
# Mixed linking
# ===================================================================


class TestMixedLinking:
    """Both snippets and result sets together."""

    def test_claim_with_both_evidence_types(self) -> None:
        linker = EvidenceLinker()
        claim = _make_claim(text="GDP impact is SAR 4.2 billion.", claim_type=ClaimType.MODEL)
        snippet = _make_snippet(extracted_text="GDP impact analysis for the region.")
        rs = _make_result_set(metric_type="gdp_impact", values={"total": 4.2e9})
        result = linker.link_evidence(
            claims=[claim],
            snippets=[snippet],
            result_sets=[rs],
        )
        linked = result.linked_claims[0]
        assert len(linked.evidence_refs) >= 1
        assert len(linked.model_refs) >= 1
        assert linked.status == ClaimStatus.SUPPORTED

    def test_only_extracted_claims_skipped(self) -> None:
        """Claims in EXTRACTED status (assumptions/recommendations) are not linked."""
        linker = EvidenceLinker()
        claim = _make_claim(
            text="We assume 65% domestic share.",
            claim_type=ClaimType.ASSUMPTION,
            status=ClaimStatus.EXTRACTED,
        )
        snippet = _make_snippet(extracted_text="domestic share assumptions")
        result = linker.link_evidence(
            claims=[claim],
            snippets=[snippet],
            result_sets=[],
        )
        linked = result.linked_claims[0]
        assert linked.status == ClaimStatus.EXTRACTED

    def test_already_supported_not_downgraded(self) -> None:
        """Claims already SUPPORTED should not be downgraded."""
        linker = EvidenceLinker()
        claim = _make_claim(
            text="GDP impact is large.",
            claim_type=ClaimType.MODEL,
            status=ClaimStatus.SUPPORTED,
        )
        result = linker.link_evidence(
            claims=[claim],
            snippets=[],
            result_sets=[],
        )
        assert result.linked_claims[0].status == ClaimStatus.SUPPORTED


# ===================================================================
# LinkResult summary
# ===================================================================


class TestLinkResult:
    """LinkResult provides summary statistics."""

    def test_total_linked(self) -> None:
        linker = EvidenceLinker()
        c1 = _make_claim(text="Steel prices increased 15%.", claim_type=ClaimType.SOURCE_FACT)
        c2 = _make_claim(text="Unemployment forecast.", claim_type=ClaimType.MODEL)
        snippet = _make_snippet(extracted_text="Steel prices increased 15% in Q3 2024.")
        result = linker.link_evidence(
            claims=[c1, c2],
            snippets=[snippet],
            result_sets=[],
        )
        assert result.total_linked >= 1

    def test_total_unlinked(self) -> None:
        linker = EvidenceLinker()
        c1 = _make_claim(text="Totally unrelated claim about weather.", claim_type=ClaimType.MODEL)
        result = linker.link_evidence(
            claims=[c1],
            snippets=[],
            result_sets=[],
        )
        assert result.total_unlinked == 1
