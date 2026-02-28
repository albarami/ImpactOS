"""Shared enums and foundation models for the Knowledge Flywheel (MVP-12).

These enums are used across all flywheel components: capture, review,
promotion, and reuse services.
"""

from __future__ import annotations

from enum import StrEnum


class ReuseScopeLevel(StrEnum):
    """Visibility scope for promoted knowledge items.

    Controls where a promoted refinement can be reused.
    """

    WORKSPACE_ONLY = "WORKSPACE_ONLY"
    SANITIZED_GLOBAL = "SANITIZED_GLOBAL"
    GLOBAL_INTERNAL = "GLOBAL_INTERNAL"


class DraftStatus(StrEnum):
    """Status of a captured refinement before promotion review.

    Tracks the lifecycle from initial capture through review.
    """

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class PromotionStatus(StrEnum):
    """Status of a refinement in the promotion pipeline.

    Tracks the lifecycle from raw capture to promoted knowledge.
    """

    RAW = "RAW"
    REVIEWED = "REVIEWED"
    PROMOTED = "PROMOTED"
    DISMISSED = "DISMISSED"


class AssumptionValueType(StrEnum):
    """Type of value held by an assumption refinement.

    Determines how the refinement value is interpreted and validated.
    """

    NUMERIC = "NUMERIC"
    CATEGORICAL = "CATEGORICAL"
