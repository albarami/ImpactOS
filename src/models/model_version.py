"""Immutable versioned model entities — ModelVersion, TaxonomyVersion, ConcordanceVersion."""

from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase, UTCTimestamp, UUIDv7, new_uuid7, utc_now


class ModelVersion(ImpactOSBase, frozen=True):
    """Immutable snapshot of an I-O base model per Section 5.3.

    Append-only: updates create a new version. The deterministic engine
    caches Leontief inverse B = (I-A)^-1 keyed by model_version_id.
    """

    model_version_id: UUIDv7 = Field(default_factory=new_uuid7)
    base_year: int = Field(..., ge=1900, le=2100)
    source: str = Field(..., min_length=1, max_length=500)
    sector_count: int = Field(..., gt=0)
    checksum: str = Field(
        ...,
        pattern=r"^sha256:[a-f0-9]{64}$",
        description="SHA-256 hash of the serialised model data.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)


class TaxonomyVersion(ImpactOSBase, frozen=True):
    """Immutable taxonomy version defining sector codes and hierarchy."""

    taxonomy_version_id: UUIDv7 = Field(default_factory=new_uuid7)
    sector_codes: list[str] = Field(..., min_length=1)
    hierarchy: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Parent → children mapping for sector hierarchy.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)


class ConcordanceVersion(ImpactOSBase, frozen=True):
    """Immutable concordance table translating between taxonomy versions."""

    concordance_id: UUIDv7 = Field(default_factory=new_uuid7)
    from_taxonomy: UUID
    to_taxonomy: UUID
    mappings: dict[str, str] = Field(
        ...,
        min_length=1,
        description="Source sector code → target sector code.",
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)
