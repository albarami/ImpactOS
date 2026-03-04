"""Portfolio optimization Pydantic v2 schemas — Sprint 21.

Defines typed configuration, result, and API request/response models for
deterministic binary portfolio optimization over candidate scenario runs.
These models are consumed by the portfolio optimizer engine, repository
layer, and API endpoints.

All optimization computation is performed by the deterministic engine in
``src/engine/portfolio_optimizer.py`` — these schemas carry structured
inputs and results only.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from src.models.common import ImpactOSBase, UTCTimestamp


class PortfolioConfig(ImpactOSBase):
    """Optimization configuration — what to optimize and under what constraints.

    Specifies the objective metric to maximize, cost metric for budget
    constraint, candidate run IDs, and optional selection/group caps.
    """

    objective_metric: str = Field(..., min_length=1, max_length=50)
    cost_metric: str = Field(..., min_length=1, max_length=50)
    candidate_run_ids: list[UUID] = Field(..., min_length=1)
    budget: float = Field(..., gt=0)
    min_selected: int = Field(default=1, ge=1)
    max_selected: int | None = Field(default=None, ge=1)
    group_caps: dict[str, int] | None = None


class CandidateItem(ImpactOSBase):
    """Per-candidate detail in response.

    Shows each candidate's objective/cost values and whether the solver
    selected it in the optimal portfolio.
    """

    run_id: UUID
    objective_value: float
    cost: float
    group_key: str | None = None
    selected: bool


class PortfolioOptimizationResponse(ImpactOSBase):
    """Full response for a single portfolio optimization result."""

    portfolio_id: str
    workspace_id: str
    model_version_id: str
    config: PortfolioConfig
    selected_run_ids: list[str]
    total_objective: float
    total_cost: float
    solver_method: str
    candidates_evaluated: int
    feasible_count: int
    optimization_version: str
    result_checksum: str
    created_at: UTCTimestamp


class PortfolioListResponse(ImpactOSBase):
    """Paginated list of portfolio optimizations."""

    items: list[PortfolioOptimizationResponse]
    total: int
    limit: int
    offset: int


class CreatePortfolioRequest(ImpactOSBase):
    """Public request schema for POST endpoint.

    Validation mirrors PortfolioConfig constraints to reject invalid
    requests at the API boundary before reaching the engine.
    """

    objective_metric: str = Field(..., min_length=1, max_length=50)
    cost_metric: str = Field(..., min_length=1, max_length=50)
    candidate_run_ids: list[str] = Field(..., min_length=1)
    budget: float = Field(..., gt=0)
    min_selected: int = Field(default=1, ge=1)
    max_selected: int | None = Field(default=None, ge=1)
    group_caps: dict[str, int] | None = None
