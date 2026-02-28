"""Depth Engine models — Al-Muhāsibī 5-step reasoning framework.

The Al-Muhāsibī structured reasoning methodology and framework are the
intellectual property of Salim Al-Barami, licensed to Strategic Gears
for use within ImpactOS. The software implementation, prompt engineering,
and system integration are part of the ImpactOS platform.

Pydantic schemas for the depth engine that generates structured JSON
artifacts challenging "comfortable" scenarios. Every output is typed,
validated, and persisted. The depth engine NEVER computes economic results.

NOTE: Fields marked ``evidence_refs`` are interpretive artifacts produced
by the AI pipeline. They must not be treated as factual claims unless
promoted into governance objects (Claims, Assumptions).  The optional
evidence pointers exist so that governance can be tightened later without
schema changes.

Steps:
1. Khawatir  — Candidate direction generation
2. Muraqaba  — Bias register (cognitive bias detection)
3. Mujahada  — Contrarian challenge ("uncomfortable truths")
4. Muhasaba  — Self-accounting scoring and ranking
5. Suite Planning — Final scenario suite assembly

MVP-9 Amendments applied:
1. DB-backed artifact storage (via DepthArtifactRepository)
2. Structured shock specs (ProposedShockSpec)
3. Workspace-scoped API
4. Classification-aware provider routing
5. Evidence/assumption hooks (evidence_refs fields)
6. LLM scores + deterministic threshold
7. ASCII class names only
8. ExportMode verified as SANDBOX/GOVERNED
9. Per-step metadata (StepMetadata)
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    AssumptionStatus,
    AssumptionType,
    DisclosureTier,
    ExportMode,
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


class DirectionLabel(StrEnum):
    """Khawatir step: classify the origin of each idea.

    - NAFS: ego-driven / status quo bias
    - WASWAS: noise / unfounded speculation
    - INSIGHT: analytically grounded genuine insight
    """

    NAFS = "nafs"
    WASWAS = "waswas"
    INSIGHT = "insight"


class ContrarianType(StrEnum):
    """Whether a contrarian scenario can be quantified in the IO engine."""

    QUANTIFIED = "QUANTIFIED"
    QUALITATIVE_ONLY = "QUALITATIVE_ONLY"


# ---------------------------------------------------------------------------
# Amendment 2: Structured shock specs (not dict[str, float])
# ---------------------------------------------------------------------------


class ProposedShockSpec(ImpactOSBase):
    """A structured shock fragment that the Scenario Compiler / BatchRunner can consume.

    Amendment 2: replaces weak ``dict[str, float]`` with typed specs.
    """

    sector_code: str
    shock_value: float
    shock_year: int | None = None
    denomination: str = "SAR_MILLIONS"
    import_share_override: float | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Amendment 9: Per-step metadata
# ---------------------------------------------------------------------------


class StepMetadata(ImpactOSBase):
    """Metadata for a single Depth Engine step execution.

    Captures provider, model, token usage, and duration per step
    for debugging, cost tracking, and reproducibility.
    """

    step: int
    step_name: DepthStepName
    prompt_pack_version: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int | None = None
    generation_mode: str = "FALLBACK"
    timestamp: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Step 1 output: Khawatir — Candidate direction generation
# ---------------------------------------------------------------------------


class CandidateDirection(ImpactOSBase):
    """A candidate scenario direction generated during Khawatir.

    source_type labels the Al-Muhāsibī provenance:
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
    # MVP-9 Amendment 5: evidence hooks for fact-bearing fields
    disclosure_tier: DisclosureTier = DisclosureTier.TIER1
    evidence_refs: list[UUID] | None = None


class KhawatirOutput(ImpactOSBase):
    """Typed output for Step 1 (Khawatir)."""

    candidates: list[CandidateDirection] = Field(default_factory=list)
    # MVP-9 enhancements
    engagement_context_summary: str | None = None
    evidence_refs: list[UUID] | None = None
    timestamp: UTCTimestamp = Field(default_factory=utc_now)


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
    mitigation: str | None = None
    # MVP-9 Amendment 5: evidence hooks
    evidence_refs: list[UUID] | None = None


class AssumptionDraft(ImpactOSBase):
    """A draft assumption surfaced during bias audit (Step 2).

    These become formal Assumptions in the AssumptionRegister if approved.
    Uses existing AssumptionType and AssumptionStatus from common.py.
    """

    assumption_draft_id: UUIDv7 = Field(default_factory=new_uuid7)
    name: str
    description: str
    assumption_type: AssumptionType
    proposed_value: str
    proposed_range: tuple[str, str] | None = None
    rationale: str
    status: AssumptionStatus = AssumptionStatus.DRAFT
    evidence_refs: list[UUID] | None = None


class BiasRegister(ImpactOSBase):
    """Full bias register for a set of candidate directions."""

    entries: list[BiasEntry] = Field(default_factory=list)
    overall_bias_risk: float = Field(ge=0.0, le=10.0)


class MuraqabaOutput(ImpactOSBase):
    """Typed output for Step 2 (Muraqaba)."""

    bias_register: BiasRegister
    # MVP-9 enhancements
    assumption_drafts: list[AssumptionDraft] = Field(default_factory=list)
    framing_assessment: str | None = None
    missing_perspectives: list[str] = Field(default_factory=list)
    evidence_refs: list[UUID] | None = None
    timestamp: UTCTimestamp = Field(default_factory=utc_now)


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
    # MVP-9 Amendment 2: structured shock specs
    contrarian_type: ContrarianType | None = None
    proposed_shock_specs: list[ProposedShockSpec] | None = None
    # MVP-9 Amendment 5: disclosure tier + evidence hooks
    disclosure_tier: DisclosureTier = DisclosureTier.TIER0
    source_direction_ids: list[UUID] = Field(default_factory=list)
    evidence_refs: list[UUID] | None = None


class QualitativeRisk(ImpactOSBase):
    """A qualitative risk that CANNOT be modeled by the engine.

    not_modeled is ALWAYS True — this enforces the agent-to-math boundary.
    The depth engine surfaces risks; the deterministic engine computes numbers.
    Labeled "qualitative -- not modeled" in all output contexts.
    """

    risk_id: UUIDv7 = Field(default_factory=new_uuid7)
    label: str = Field(..., min_length=1)
    description: str
    not_modeled: bool = True
    affected_sectors: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    expected_direction: str | None = None
    disclosure_tier: DisclosureTier = DisclosureTier.TIER0
    evidence_refs: list[UUID] | None = None

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
    timestamp: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Step 4 output: Muhasaba — Scoring and ranking
# ---------------------------------------------------------------------------


class ScoredCandidate(ImpactOSBase):
    """A scored and ranked candidate direction.

    Muhasaba scores ALL candidates (regular + contrarian) and explicitly
    accepts or rejects each with documented rationale for the audit trail.

    Amendment 6: LLM-produced scores are passed through a deterministic
    threshold (composite >= 3.0) that the agent cannot override.
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
    # MVP-9 Amendment 5: evidence hooks
    evidence_refs: list[UUID] | None = None


class MuhasabaOutput(ImpactOSBase):
    """Typed output for Step 4 (Muhasaba)."""

    scored: list[ScoredCandidate] = Field(default_factory=list)
    # MVP-9 enhancements
    timestamp: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Step 5 output: Suite Planning — Executable scenario suite
# ---------------------------------------------------------------------------


class SuiteRun(ImpactOSBase):
    """A single executable run within the scenario suite.

    executable_levers are constrained to the engine's supported types:
    FINAL_DEMAND_SHOCK, IMPORT_SHARE_ADJUSTMENT, LOCAL_CONTENT_TARGET,
    PHASING_SHIFT, CONSTRAINT_SET_TOGGLE, SENSITIVITY_SWEEP.

    Amendment 2: proposed_shock_specs adds typed shock fragments alongside
    the legacy executable_levers dict format.
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
    # MVP-9 Amendment 2: structured shock specs for compiler consumption
    proposed_shock_specs: list[ProposedShockSpec] = Field(
        default_factory=list,
        description="Typed shock specs that BatchRunner/Compiler can consume directly.",
    )
    mode: str = Field(default="SANDBOX")
    sensitivities: list[str] = Field(default_factory=list)
    disclosure_tier: DisclosureTier = DisclosureTier.TIER1
    is_contrarian: bool = False


class ScenarioSuitePlan(ImpactOSBase):
    """Final scenario suite assembled from scored candidates.

    This is the primary output of the depth engine — a structured plan
    that is directly feedable to the compiler/engine for execution.

    Amendment 8: mode field must be SANDBOX or GOVERNED only.
    """

    suite_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    engagement_id: UUID | None = None
    runs: list[SuiteRun] = Field(default_factory=list)
    recommended_outputs: list[str] = Field(
        default_factory=list,
        description=(
            "e.g. multipliers, jobs, imports, variance_bridge"
        ),
    )
    qualitative_risks: list[QualitativeRisk] = Field(default_factory=list)
    rationale: str = ""
    notes: str | None = None
    export_mode: ExportMode = ExportMode.SANDBOX
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
    """A depth engine plan — tracks the full 5-step execution.

    Amendment 9: step_metadata captures per-step provider, token usage,
    and duration for debugging, cost tracking, and reproducibility.
    """

    plan_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    scenario_spec_id: UUID | None = None
    engagement_id: UUID | None = None
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
    # MVP-9 Amendment 9: per-step metadata
    step_metadata: list[StepMetadata] = Field(
        default_factory=list,
        description="Metadata for each executed step (provider, tokens, duration).",
    )
    error_message: str | None = None
    created_at: UTCTimestamp = Field(default_factory=utc_now)
    updated_at: UTCTimestamp = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Top-level result — returned by the orchestrator
# ---------------------------------------------------------------------------


class DepthEngineResult(ImpactOSBase):
    """Complete result of a depth engine execution.

    Aggregates all step outputs, metadata, and the final suite plan
    into a single returnable object. This is what the API returns
    to clients after a full pipeline run.

    The depth engine produces structured JSON only — it NEVER computes
    economic results. That boundary is enforced at the model level.
    """

    plan_id: UUID
    workspace_id: UUID
    status: DepthPlanStatus
    # Step outputs (None if step failed)
    khawatir: KhawatirOutput | None = None
    muraqaba: MuraqabaOutput | None = None
    mujahada: MujahadaOutput | None = None
    muhasaba: MuhasabaOutput | None = None
    suite_plan: ScenarioSuitePlan | None = None
    # Aggregated metadata
    step_metadata: list[StepMetadata] = Field(default_factory=list)
    degraded_steps: list[str] = Field(default_factory=list)
    step_errors: dict = Field(default_factory=dict)
    # Totals
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_duration_ms: int | None = None
    # Provenance
    prompt_pack_version: str = ""
    export_mode: ExportMode = ExportMode.SANDBOX
    created_at: UTCTimestamp = Field(default_factory=utc_now)
