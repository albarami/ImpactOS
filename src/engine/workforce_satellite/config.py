"""Workforce satellite configuration — tier-range defaults and confidence.

Amendment 7: Tier ranges are config, not hardcoded in the service.
Amendment 6: Unified confidence ranking across pipeline steps.
"""

from __future__ import annotations

from src.data.workforce.nationality_classification import NationalityTier
from src.data.workforce.unit_registry import QualityConfidence
from src.models.common import ConstraintConfidence

# ---------------------------------------------------------------------------
# Amendment 7: Tier-range policy (configurable per engagement)
# ---------------------------------------------------------------------------

# (min_saudi_share, mid_saudi_share, max_saudi_share)
DEFAULT_TIER_RANGES: dict[NationalityTier, tuple[float, float, float]] = {
    NationalityTier.SAUDI_READY: (0.70, 0.85, 1.00),
    NationalityTier.SAUDI_TRAINABLE: (0.20, 0.40, 0.60),
    NationalityTier.EXPAT_RELIANT: (0.00, 0.05, 0.20),
}

# Sensitivity band when current_saudi_pct is known from D-4
KNOWN_PCT_SENSITIVITY = 0.10  # ±10%


# ---------------------------------------------------------------------------
# Amendment 6: Unified confidence ranking
# ---------------------------------------------------------------------------

# Reuses existing enums: ConstraintConfidence (HARD/ESTIMATED/ASSUMED)
# and QualityConfidence (HIGH/MEDIUM/LOW).
# We map both into a single ranked integer for worst-case propagation.

CONFIDENCE_RANK: dict[str, int] = {
    "HARD": 0,         # Best — from ConstraintConfidence
    "HIGH": 1,         # From QualityConfidence
    "MEDIUM": 2,       # From QualityConfidence
    "ESTIMATED": 3,    # From ConstraintConfidence
    "LOW": 4,          # From QualityConfidence
    "ASSUMED": 5,      # Worst — from ConstraintConfidence
}


def worst_confidence(*confidences: str) -> str:
    """Return the worst (least certain) confidence level.

    Accepts any mix of ConstraintConfidence and QualityConfidence values.
    Returns the string with the highest (worst) rank.
    """
    if not confidences:
        return "ASSUMED"
    return max(
        confidences,
        key=lambda c: CONFIDENCE_RANK.get(c.upper(), 5),
    )


def confidence_to_str(
    conf: ConstraintConfidence | QualityConfidence | str,
) -> str:
    """Normalize a confidence enum or string to uppercase string."""
    if isinstance(conf, ConstraintConfidence | QualityConfidence):
        return conf.value.upper()
    return str(conf).upper()
