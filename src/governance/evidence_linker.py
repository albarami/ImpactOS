"""Evidence linking service — MVP-5.

Match claims to EvidenceSnippet objects and ResultSet model refs,
attach evidence_refs to claims, transition claims from NEEDS_EVIDENCE
to SUPPORTED.

Deterministic keyword matching — no LLM calls.
"""

import re
from dataclasses import dataclass, field

from src.models.common import ClaimStatus
from src.models.governance import Claim, EvidenceSnippet, ModelRef
from src.models.run import ResultSet


# ---------------------------------------------------------------------------
# Keyword matching helpers
# ---------------------------------------------------------------------------


def _tokenise(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _keyword_overlap(text_a: str, text_b: str, threshold: int = 2) -> bool:
    """Check if two texts share enough meaningful keywords."""
    tokens_a = _tokenise(text_a)
    tokens_b = _tokenise(text_b)
    # Remove very common stop words
    stop = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "by", "it", "we", "be", "as"}
    meaningful_a = tokens_a - stop
    meaningful_b = tokens_b - stop
    overlap = meaningful_a & meaningful_b
    return len(overlap) >= threshold


def _metric_matches_claim(metric_type: str, claim_text: str) -> bool:
    """Check if a result set metric type is referenced in the claim."""
    # Normalise metric_type: "gdp_impact" → {"gdp", "impact"}
    metric_tokens = set(metric_type.lower().replace("_", " ").split())
    claim_lower = claim_text.lower()
    return all(token in claim_lower for token in metric_tokens)


# ---------------------------------------------------------------------------
# Link result
# ---------------------------------------------------------------------------


@dataclass
class LinkResult:
    """Result of linking evidence to claims."""

    linked_claims: list[Claim] = field(default_factory=list)

    @property
    def total_linked(self) -> int:
        return sum(
            1 for c in self.linked_claims
            if c.status == ClaimStatus.SUPPORTED
        )

    @property
    def total_unlinked(self) -> int:
        return sum(
            1 for c in self.linked_claims
            if c.status == ClaimStatus.NEEDS_EVIDENCE
        )


# ---------------------------------------------------------------------------
# Evidence linker
# ---------------------------------------------------------------------------


class EvidenceLinker:
    """Link claims to evidence snippets and model result sets.

    Only processes claims in NEEDS_EVIDENCE status. Claims in other
    states are passed through unchanged.
    """

    def link_evidence(
        self,
        *,
        claims: list[Claim],
        snippets: list[EvidenceSnippet],
        result_sets: list[ResultSet],
    ) -> LinkResult:
        """Match claims to evidence and transition supported claims.

        For each claim in NEEDS_EVIDENCE:
        - Check snippet text overlap → attach snippet_id to evidence_refs
        - Check result set metric match → attach ModelRef to model_refs
        - If any evidence found → transition to SUPPORTED
        """
        linked: list[Claim] = []

        for claim in claims:
            # Only process NEEDS_EVIDENCE claims
            if claim.status != ClaimStatus.NEEDS_EVIDENCE:
                linked.append(claim)
                continue

            new_evidence_refs = list(claim.evidence_refs)
            new_model_refs = list(claim.model_refs)

            # Match against snippets
            for snippet in snippets:
                if _keyword_overlap(claim.text, snippet.extracted_text):
                    new_evidence_refs.append(snippet.snippet_id)

            # Match against result sets
            for rs in result_sets:
                if _metric_matches_claim(rs.metric_type, claim.text):
                    new_model_refs.append(
                        ModelRef(
                            run_id=rs.run_id,
                            metric=rs.metric_type,
                            value=sum(rs.values.values()),
                        )
                    )

            # Determine if evidence was found
            has_evidence = (
                len(new_evidence_refs) > len(claim.evidence_refs)
                or len(new_model_refs) > len(claim.model_refs)
            )

            if has_evidence:
                updated = claim.model_copy(
                    update={
                        "evidence_refs": new_evidence_refs,
                        "model_refs": new_model_refs,
                        "status": ClaimStatus.SUPPORTED,
                    }
                )
            else:
                updated = claim

            linked.append(updated)

        return LinkResult(linked_claims=linked)
