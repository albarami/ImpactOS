"""Shared types, enums, and base models used across ImpactOS domain models."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field
from uuid_extensions import uuid7


def utc_now() -> datetime:
    """Return the current UTC timestamp (timezone-aware)."""
    return datetime.now(tz=timezone.utc)


def new_uuid7() -> UUID:
    """Generate a new time-sortable UUID v7."""
    return uuid7()


# --- Reusable annotated types ---

UUIDv7 = Annotated[UUID, Field(description="Time-sortable UUID v7.")]
UTCTimestamp = Annotated[
    datetime, Field(description="UTC timezone-aware timestamp.")
]


# --- Shared enums ---


class DataClassification(StrEnum):
    """Workspace data classification per Section 4.3."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DisclosureTier(StrEnum):
    """Tiered disclosure level for claims and scenario artifacts."""

    TIER0 = "TIER0"
    TIER1 = "TIER1"
    TIER2 = "TIER2"


class ExportMode(StrEnum):
    """Export / run mode."""

    SANDBOX = "SANDBOX"
    GOVERNED = "GOVERNED"


class AssumptionType(StrEnum):
    """Governed assumption categories per Appendix B."""

    IMPORT_SHARE = "IMPORT_SHARE"
    PHASING = "PHASING"
    DEFLATOR = "DEFLATOR"
    WAGE_PROXY = "WAGE_PROXY"
    CAPACITY_CAP = "CAPACITY_CAP"
    JOBS_COEFF = "JOBS_COEFF"


class AssumptionStatus(StrEnum):
    """Lifecycle status for an assumption."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ClaimType(StrEnum):
    """Claim provenance categories per NFF governance."""

    MODEL = "MODEL"
    SOURCE_FACT = "SOURCE_FACT"
    ASSUMPTION = "ASSUMPTION"
    RECOMMENDATION = "RECOMMENDATION"


class ClaimStatus(StrEnum):
    """Claim lifecycle states per Appendix C."""

    EXTRACTED = "EXTRACTED"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"
    SUPPORTED = "SUPPORTED"
    REWRITTEN_AS_ASSUMPTION = "REWRITTEN_AS_ASSUMPTION"
    DELETED = "DELETED"
    APPROVED_FOR_EXPORT = "APPROVED_FOR_EXPORT"


class ConstraintConfidence(StrEnum):
    """Confidence label for constraint parameters."""

    HARD = "HARD"
    ESTIMATED = "ESTIMATED"
    ASSUMED = "ASSUMED"


class MappingConfidenceBand(StrEnum):
    """Confidence bands for mapping quality metrics."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# --- Base model ---


class ImpactOSBase(BaseModel):
    """Base model with common configuration for all ImpactOS Pydantic models."""

    model_config = {
        "populate_by_name": True,
        "ser_json_timedelta": "iso8601",
        "protected_namespaces": (),
    }
