"""Structural Path Analysis models — Pydantic v2 schemas.

Defines typed configuration, result, and API request/response models for
Structural Path Analysis (SPA) and chokepoint detection. These models are
consumed by the SPA engine, repository layer, and API endpoints.

All numerical computation is performed by the deterministic engine in
``src/engine/`` — these schemas carry structured results only.
"""

from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase, UTCTimestamp


class PathAnalysisConfig(ImpactOSBase):
    """Typed config for SPA computation. Validated bounds, stable OpenAPI."""

    max_depth: int = Field(default=6, ge=0, le=12)
    top_k: int = Field(default=20, ge=1, le=100)


class PathContributionItem(ImpactOSBase):
    """A single structural path contribution.

    Represents the contribution of a path at a given depth from a source
    sector (final demand target) to a target sector (affected sector).
    """

    source_sector_code: str  # j -- final demand target
    target_sector_code: str  # i -- affected sector
    depth: int  # k -- hop count (0=direct)
    coefficient: float  # (A^k)[i,j] pure
    contribution: float  # (A^k)[i,j] * delta_d[j]


class DepthContributionItem(ImpactOSBase):
    """Aggregated contribution at a single depth level."""

    signed: float  # net contribution at this depth
    absolute: float  # sum of |values| at this depth


class ChokePointItem(ImpactOSBase):
    """Chokepoint detection result for a single sector.

    A sector is a chokepoint when both its normalized forward and backward
    linkages exceed 1.0, indicating it is a critical intermediary in the
    inter-industry flow structure.
    """

    sector_code: str
    forward_linkage: float  # raw row sum of B
    backward_linkage: float  # raw column sum of B
    norm_forward: float  # divided by mean(forward)
    norm_backward: float  # divided by mean(backward)
    chokepoint_score: float  # sqrt(nf * nb)
    is_chokepoint: bool  # both normalized > 1.0


class CreatePathAnalysisRequest(ImpactOSBase):
    """API request to create a new path analysis for an existing run."""

    run_id: UUID
    config: PathAnalysisConfig = Field(default_factory=PathAnalysisConfig)


class PathAnalysisResponse(ImpactOSBase):
    """Full path analysis result returned by the API."""

    analysis_id: UUID
    run_id: UUID
    analysis_version: str
    config: PathAnalysisConfig
    config_hash: str
    top_paths: list[PathContributionItem]
    chokepoints: list[ChokePointItem]
    depth_contributions: dict[str, DepthContributionItem]  # str(k) -> item
    coverage_ratio: float
    result_checksum: str
    created_at: UTCTimestamp


class PathAnalysisListResponse(ImpactOSBase):
    """Paginated list of path analysis results."""

    items: list[PathAnalysisResponse]
    total: int
