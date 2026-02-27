"""Depth Engine models — Al-Muhasabi 5-step reasoning framework.

Pydantic schemas for the proprietary depth engine that generates structured
JSON artifacts challenging "comfortable" scenarios. Every output is typed,
validated, and persisted. The depth engine NEVER computes economic results.

Steps:
1. Khawatir  — Candidate direction generation
2. Muraqaba  — Bias register (cognitive bias detection)
3. Mujahada  — Contrarian challenge ("uncomfortable truths")
4. Muhasaba  — Self-accounting scoring and ranking
5. Suite Planning — Final scenario suite assembly

Amendments applied:
- CandidateDirection: +source_type, +test_plan, +required_levers, -novelty_score
- ContrarianDirection: +broken_assumption, +is_quantifiable, +quantified_levers, -novelty_score
- ScoredCandidate: +accepted, +rejection_reason
- ScenarioSuitePlan: +runs (list[SuiteRun]), +recommended_outputs
- Typed output models per step
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    DisclosureTier,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DepthStepName(StrEnum):
    """The 5 steps of the Al-Muhasabi depth engine."""

    KHAWATIR = "KHAWATIR"
    MURAQABA = "MURAQABA"
    MUJAHADA = "MUJAHADA"
    MUHASABA = "MUHASABA"
    SUITE_PLANNING = "SUITE_PLANNING"


class DepthPlanStatus(StrEnum):
    """Lifecycle status for a depth plan execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"  # Suite plan artifact exists
    PARTIAL = "PARTIAL"      # Suite plan missing
    FAILED = "FAILED"


# ---------------------------------------------------------------------------
# Step 1 output: Khawatir — Candidate direction generation
# ---------------------------------------------------------------------------


class CandidateDirection(ImpactOSBase):
    """A candidate scenario direction generated during Khawatir.

    source_type labels the Al-Muhasabi provenance:
    - nafs: ego-driven / comfortable direction
    - waswas: noise / distraction
    - insight: analytically grounded direction
    """

    direction_id: UUIDv7 = Field(default_factory=new_uuid7)
    label: str = Field(..., min_length=1)
    description: str
    sector_codes: list[str] = Field(default_factory=list)
    rationale: str
    source_type: Literal["nafs", "waswas", "insight"]
    test_plan: str = Field(
        ...,
        description="How to model this direction using available engine levers.",
    )
    required_levers: list[str] = Field(
        default_factory=list,
        description=(
            "Shock types needed: FINAL_DEMAND_SHOCK, IMPORT_SUBSTITUTION,"
            " LOCAL_CONTENT, CONSTRAINT_OVERRIDE"
        ),
    )


class KhawatirOutput(ImpactOSBase):
    """Typed output for Step 1 (Khawatir)."""

    candidates: list[CandidateDirection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 2 output: Muraqaba — Bias register
# ---------------------------------------------------------------------------


class BiasEntry(ImpactOSBase):
    """A single detected cognitive bias."""

    bias_type: str = Field(
        ..., min_length=1,
        description="e.g. anchoring, availability, optimism, groupthink",
    )
    description: str
    affected_directions: list[UUID] = Field(default_factory=list)
    severity: float = Field(ge=0.0, le=10.0)


class BiasRegister(ImpactOSBase):
    """Full bias register for a set of candidate directions."""

    entries: list[BiasEntry] = Field(default_factory=list)
    overall_bias_risk: float = Field(ge=0.0, le=10.0)


class MuraqabaOutput(ImpactOSBase):
    """Typed output for Step 2 (Muraqaba)."""

    bias_register: BiasRegister


# ---------------------------------------------------------------------------
# Step 3 output: Mujahada — Contrarian challenge
# ---------------------------------------------------------------------------


class ContrarianDirection(ImpactOSBase):
    """A contrarian scenario direction challenging base assumptions.

    Disclosure: all contrarian outputs default TIER0 (internal only).
    """

    direction_id: UUIDv7 = Field(default_factory=new_uuid7)
    label: str = Field(..., min_length=1)
    description: str
    uncomfortable_truth: str
    sector_codes: list[str] = Field(default_factory=list)
    rationale: str
    broken_assumption: str = Field(
        ...,
        description="Which specific base scenario assumption this challenges.",
    )
    is_quantifiable: bool = Field(
        default=False,
        description="Can the deterministic engine model this?",
    )
    quantified_levers: list[dict] | None = Field(
        default=None,
        description=(
            "ShockItem-like overrides when is_quantifiable=True."
        ),
    )


class QualitativeRisk(ImpactOSBase):
    """A qualitative risk that CANNOT be modeled by the engine.

    not_modeled is ALWAYS True — this enforces the agent-to-math boundary.
    The depth engine surfaces risks; the deterministic engine computes numbers.
    """

    risk_id: UUIDv7 = Field(default_factory=new_uuid7)
    label: str = Field(..., min_length=1)
    description: str
    not_modeled: bool = True
    affected_sectors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_not_modeled(self) -> "QualitativeRisk":
        """Agent-to-math boundary: qualitative risks are NEVER modeled."""
        if not self.not_modeled:
            raise ValueError(
                "QualitativeRisk.not_modeled must always be True. "
                "The depth engine does not compute economic results."
            )
        return self


class MujahadaOutput(ImpactOSBase):
    """Typed output for Step 3 (Mujahada)."""

    contrarians: list[ContrarianDirection] = Field(default_factory=list)
    qualitative_risks: list[QualitativeRisk] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 4 output: Muhasaba — Scoring and ranking
# ---------------------------------------------------------------------------


class ScoredCandidate(ImpactOSBase):
    """A scored and ranked candidate direction.

    Muhasaba scores ALL candidates (regular + contrarian) and explicitly
    accepts or rejects each with documented rationale for the audit trail.
    """

    direction_id: UUID
    label: str
    composite_score: float = Field(ge=0.0, le=10.0)
    novelty_score: float = Field(ge=0.0, le=10.0)
    feasibility_score: float = Field(ge=0.0, le=10.0)
    data_availability_score: float = Field(ge=0.0, le=10.0)
    is_contrarian: bool = False
    rank: int = Field(ge=1)
    accepted: bool = True
    rejection_reason: str | None = None


class MuhasabaOutput(ImpactOSBase):
    """Typed output for Step 4 (Muhasaba)."""

    scored: list[ScoredCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 5 output: Suite Planning — Executable scenario suite
# ---------------------------------------------------------------------------


class SuiteRun(ImpactOSBase):
    """A single executable run within the scenario suite.

    executable_levers are constrained to the engine's supported types:
    FINAL_DEMAND_SHOCK, IMPORT_SHARE_ADJUSTMENT, LOCAL_CONTENT_TARGET,
    PHASING_SHIFT, CONSTRAINT_SET_TOGGLE, SENSITIVITY_SWEEP.
    """

    name: str = Field(..., min_length=1)
    direction_id: UUID
    executable_levers: list[dict] = Field(
        default_factory=list,
        description=(
            "ShockItem-like dicts with type, sector, value. Constrained to:"
            " FINAL_DEMAND_SHOCK, IMPORT_SHARE_ADJUSTMENT,"
            " LOCAL_CONTENT_TARGET, PHASING_SHIFT,"
            " CONSTRAINT_SET_TOGGLE, SENSITIVITY_SWEEP"
        ),
    )
    mode: str = Field(default="SANDBOX")
    sensitivities: list[str] = Field(default_factory=list)
    disclosure_tier: DisclosureTier = DisclosureTier.TIER1


class ScenarioSuitePlan(ImpactOSBase):
    """Final scenario suite assembled from scored candidates.

    This is the primary output of the depth engine — a structured plan
    that is directly feedable to the compiler/engine for execution.
    """

    suite_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    runs: list[SuiteRun] = Field(default_factory=list)
    recommended_outputs: list[str] = Field(
        default_factory=list,
        description=(
            "e.g. multipliers, jobs, imports, variance_bridge"
        ),
    )
    qualitative_risks: list[QualitativeRisk] = Field(default_factory=list)
    rationale: str = ""
    disclosure_tier: DisclosureTier = DisclosureTier.TIER1


class SuitePlanningOutput(ImpactOSBase):
    """Typed output for Step 5 (Suite Planning)."""

    suite_plan: ScenarioSuitePlan


# ---------------------------------------------------------------------------
# Artifact wrapper — per-step persisted output
# ---------------------------------------------------------------------------


class DepthArtifact(ImpactOSBase):
    """A single persisted artifact from one step of the depth engine."""

    artifact_id: UUIDv7 = Field(default_factory=new_uuid7)
    plan_id: UUID
    step: DepthStepName
    payload: dict = Field(
        ...,
        description="Serialized step output (model_dump of typed output).",
    )
    disclosure_tier: DisclosureTier = DisclosureTier.TIER0
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "LLM audit metadata: provider, model, temperature, "
            "max_tokens, prompt_pack_version, context_hash, "
            "generation_mode (LLM|FALLBACK)."
        ),
    )
    created_at: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Plan-level model
# ---------------------------------------------------------------------------


class DepthPlan(ImpactOSBase):
    """A depth engine plan — tracks the full 5-step execution."""

    plan_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    scenario_spec_id: UUID | None = None
    status: DepthPlanStatus = DepthPlanStatus.PENDING
    current_step: DepthStepName | None = None
    degraded_steps: list[str] = Field(
        default_factory=list,
        description="Steps that used fallback or failed.",
    )
    step_errors: dict = Field(
        default_factory=dict,
        description="Error details per step (step_name -> error message).",
    )
    error_message: str | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)
