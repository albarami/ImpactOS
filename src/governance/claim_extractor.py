"""Claim extraction service — MVP-5 Section 12 / 11.3.

Parse draft narrative text into atomic Claim objects, classify each as
MODEL / SOURCE_FACT / ASSUMPTION / RECOMMENDATION, flag claims that
need evidence.

Deterministic heuristic classifier — no LLM calls.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from src.models.common import ClaimStatus, ClaimType
from src.models.governance import Claim


# ---------------------------------------------------------------------------
# Classification heuristics (keyword-based, deterministic)
# ---------------------------------------------------------------------------

_ASSUMPTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bassume[sd]?\b", re.IGNORECASE),
    re.compile(r"\bassuming\b", re.IGNORECASE),
    re.compile(r"\bassumption\b", re.IGNORECASE),
]

_RECOMMENDATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brecommend(?:s|ed|ation)?\b", re.IGNORECASE),
    re.compile(r"\bshould\b", re.IGNORECASE),
    re.compile(r"\badvise[sd]?\b", re.IGNORECASE),
    re.compile(r"\bpropose[sd]?\b", re.IGNORECASE),
]

_SOURCE_FACT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\baccording to\b", re.IGNORECASE),
    re.compile(r"\breported by\b", re.IGNORECASE),
    re.compile(r"\bdata (?:from|shows?)\b", re.IGNORECASE),
    re.compile(r"\bsource[sd]?\b", re.IGNORECASE),
    re.compile(r"\bstatistics\b", re.IGNORECASE),
    re.compile(r"\bSAMA\b"),
    re.compile(r"\bGAStat\b"),
    re.compile(r"\bWorld Bank\b", re.IGNORECASE),
    re.compile(r"\bIMF\b"),
]

# MODEL is the fallback — sentences with quantitative claims from the model
_MODEL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bgenerate[sd]?\b", re.IGNORECASE),
    re.compile(r"\bimpact\b", re.IGNORECASE),
    re.compile(r"\bestimate[sd]?\b", re.IGNORECASE),
    re.compile(r"\bproject(?:ed|ion)?\b", re.IGNORECASE),
    re.compile(r"\boutput\b", re.IGNORECASE),
    re.compile(r"\bjobs?\b", re.IGNORECASE),
    re.compile(r"\bGDP\b"),
    re.compile(r"\bSAR\s+[\d.,]+\b"),
    re.compile(r"\b[\d.,]+\s*(?:billion|million|thousand|%)\b", re.IGNORECASE),
]

# Types that get auto-flagged as NEEDS_EVIDENCE
_NEEDS_EVIDENCE_TYPES = frozenset({ClaimType.MODEL, ClaimType.SOURCE_FACT})


# ---------------------------------------------------------------------------
# Extraction result
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Result of extracting claims from draft text."""

    claims: list[Claim] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.claims)

    @property
    def needs_evidence_count(self) -> int:
        return sum(1 for c in self.claims if c.status == ClaimStatus.NEEDS_EVIDENCE)

    @property
    def by_type(self) -> dict[ClaimType, int]:
        counts: Counter[ClaimType] = Counter()
        for c in self.claims:
            counts[c.claim_type] += 1
        return dict(counts)


# ---------------------------------------------------------------------------
# Claim extractor
# ---------------------------------------------------------------------------


class ClaimExtractor:
    """Parse draft narrative text into atomic Claim objects.

    Uses deterministic heuristics for classification — no LLM calls.
    Production would use Al-Muhāsibī for deeper classification.
    """

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences, filtering empty/whitespace."""
        # Split on sentence-ending punctuation followed by space or end
        raw = re.split(r"(?<=[.!?])\s+", text.strip())
        return [s.strip() for s in raw if s.strip()]

    @staticmethod
    def _classify(sentence: str) -> ClaimType:
        """Classify a sentence into a ClaimType using keyword heuristics.

        Priority: ASSUMPTION > RECOMMENDATION > SOURCE_FACT > MODEL (fallback).
        """
        for pattern in _ASSUMPTION_PATTERNS:
            if pattern.search(sentence):
                return ClaimType.ASSUMPTION

        for pattern in _RECOMMENDATION_PATTERNS:
            if pattern.search(sentence):
                return ClaimType.RECOMMENDATION

        for pattern in _SOURCE_FACT_PATTERNS:
            if pattern.search(sentence):
                return ClaimType.SOURCE_FACT

        # Default to MODEL for quantitative / analytical statements
        return ClaimType.MODEL

    def extract(
        self,
        *,
        draft_text: str,
        workspace_id: UUID,
        run_id: UUID,
    ) -> ExtractionResult:
        """Extract atomic claims from draft narrative text.

        Each sentence becomes one claim. Claims of type MODEL or SOURCE_FACT
        are auto-transitioned to NEEDS_EVIDENCE.
        """
        sentences = self._split_sentences(draft_text)
        claims: list[Claim] = []

        for sentence in sentences:
            claim_type = self._classify(sentence)

            # Determine initial status
            if claim_type in _NEEDS_EVIDENCE_TYPES:
                status = ClaimStatus.NEEDS_EVIDENCE
            else:
                status = ClaimStatus.EXTRACTED

            claim = Claim(
                text=sentence,
                claim_type=claim_type,
                status=status,
            )
            claims.append(claim)

        return ExtractionResult(claims=claims)
