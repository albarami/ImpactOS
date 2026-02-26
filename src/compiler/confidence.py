"""Confidence thresholds — MVP-4 Section 9.5.

HIGH >= 0.85: eligible for bulk-approve.
MEDIUM 0.60–0.85: require spot-check.
LOW < 0.60: must be explicitly resolved.

Deterministic — no LLM calls.
"""

from enum import StrEnum


class ConfidenceBand(StrEnum):
    """Confidence classification bands per Section 9.5."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def classify_confidence(confidence: float) -> ConfidenceBand:
    """Classify a single confidence score into a band."""
    if confidence >= 0.85:
        return ConfidenceBand.HIGH
    if confidence >= 0.60:
        return ConfidenceBand.MEDIUM
    return ConfidenceBand.LOW


def classify_mappings(
    confidences: list[float],
) -> dict[ConfidenceBand, list[float]]:
    """Group confidence values by band."""
    result: dict[ConfidenceBand, list[float]] = {
        ConfidenceBand.HIGH: [],
        ConfidenceBand.MEDIUM: [],
        ConfidenceBand.LOW: [],
    }
    for c in confidences:
        band = classify_confidence(c)
        result[band].append(c)
    return result
