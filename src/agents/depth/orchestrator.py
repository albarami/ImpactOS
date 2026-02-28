"""Depth Engine Orchestrator — sequential 5-step pipeline.

The Al-Muhasabi structured reasoning methodology and framework are the
intellectual property of Salim Al-Barami, licensed to Strategic Gears
for use within ImpactOS. The software implementation, prompt engineering,
and system integration are part of the ImpactOS platform.

Runs all 5 Al-Muhasabi steps in order, persisting each artifact.
Supports partial failure: if step N fails, steps 1..N-1 are preserved.

Status semantics:
- COMPLETED: Suite plan artifact exists (even if earlier steps used fallback)
- PARTIAL: Suite plan missing (some steps failed)
- FAILED: Critical failure (no artifacts produced)

MVP-9 Amendment 9: Per-step metadata (StepMetadata) is captured for
each step execution and stored on the DepthPlan for audit.
"""

import hashlib
import json
import logging
import time
from uuid import UUID

from src.agents.depth.base import DepthStepAgent  # noqa: F401
from src.agents.depth.khawatir import KhawatirAgent
from src.agents.depth.muhasaba import MuhasabaAgent
from src.agents.depth.mujahada import MujahadaAgent
from src.agents.depth.muraqaba import MuraqabaAgent
from src.agents.depth.prompts import PROMPT_PACK_VERSION
from src.agents.depth.suite_planner import SuitePlannerAgent
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification, DisclosureTier, new_uuid7
from src.models.depth import DepthPlanStatus, DepthStepName, StepMetadata
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository

logger = logging.getLogger(__name__)

# Disclosure tiers per step
_STEP_DISCLOSURE: dict[DepthStepName, DisclosureTier] = {
    DepthStepName.KHAWATIR: DisclosureTier.TIER0,
    DepthStepName.MURAQABA: DisclosureTier.TIER0,
    DepthStepName.MUJAHADA: DisclosureTier.TIER0,  # Contrarian = internal only
    DepthStepName.MUHASABA: DisclosureTier.TIER0,
    DepthStepName.SUITE_PLANNING: DisclosureTier.TIER1,
}

# Step number mapping (1-indexed per Al-Muhasabi spec)
_STEP_NUMBER: dict[DepthStepName, int] = {
    DepthStepName.KHAWATIR: 1,
    DepthStepName.MURAQABA: 2,
    DepthStepName.MUJAHADA: 3,
    DepthStepName.MUHASABA: 4,
    DepthStepName.SUITE_PLANNING: 5,
}


def _get_step_agent(step: DepthStepName) -> DepthStepAgent:
    """Get the agent for a given step."""
    agents: dict[DepthStepName, type[DepthStepAgent]] = {
        DepthStepName.KHAWATIR: KhawatirAgent,
        DepthStepName.MURAQABA: MuraqabaAgent,
        DepthStepName.MUJAHADA: MujahadaAgent,
        DepthStepName.MUHASABA: MuhasabaAgent,
        DepthStepName.SUITE_PLANNING: SuitePlannerAgent,
    }
    return agents[step]()


def _compute_context_hash(context: dict) -> str:
    """Hash the context dict for audit metadata."""
    serialized = json.dumps(context, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


class DepthOrchestrator:
    """Sequential 5-step pipeline with persistence and partial failure handling.

    MVP-9 enhancements:
    - Captures StepMetadata per step (provider, tokens, duration)
    - Tracks prompt_pack_version for reproducibility
    - Returns enriched step_metadata list alongside status
    """

    STEPS = [
        DepthStepName.KHAWATIR,
        DepthStepName.MURAQABA,
        DepthStepName.MUJAHADA,
        DepthStepName.MUHASABA,
        DepthStepName.SUITE_PLANNING,
    ]

    async def run(
        self,
        *,
        plan_id: UUID,
        workspace_id: UUID,
        context: dict,
        classification: DataClassification,
        llm_client: LLMClient | None = None,
        plan_repo: DepthPlanRepository,
        artifact_repo: DepthArtifactRepository,
        prompt_pack_version: str = PROMPT_PACK_VERSION,
    ) -> DepthPlanStatus:
        """Execute the full 5-step depth engine pipeline.

        Each step:
        1. Update plan status -> RUNNING, current_step
        2. Run step agent (LLM or fallback)
        3. Capture per-step metadata (Amendment 9)
        4. Persist artifact with metadata
        5. Feed output into accumulated context for next step

        On failure: log error, record degraded_step, continue.
        Final status: COMPLETED if suite plan exists, PARTIAL otherwise.
        """
        degraded_steps: list[str] = []
        step_errors: dict[str, str] = {}
        step_metadata_list: list[dict] = []
        accumulated_context = dict(context)
        accumulated_context["workspace_id"] = str(workspace_id)
        has_suite_plan = False

        # Mark plan as RUNNING
        await plan_repo.update_status(
            plan_id, DepthPlanStatus.RUNNING.value,
            current_step=self.STEPS[0].value,
        )

        for step in self.STEPS:
            try:
                # Update current step
                await plan_repo.update_status(
                    plan_id, DepthPlanStatus.RUNNING.value,
                    current_step=step.value,
                )

                agent = _get_step_agent(step)
                can_use_llm = (
                    llm_client is not None
                    and llm_client.is_available_for(classification)
                )
                generation_mode = "LLM" if can_use_llm else "FALLBACK"

                # Determine provider/model info
                provider = "none"
                model = "fallback"
                if can_use_llm and llm_client is not None:
                    try:
                        selected = llm_client._router.select_provider(classification)
                        provider = selected.value if selected else "none"
                        model = "default"
                    except Exception:
                        provider = "none"
                        model = "fallback"

                # Run the step with timing (Amendment 9)
                start_time = time.monotonic()
                payload = agent.run(
                    context=accumulated_context,
                    llm_client=llm_client,
                    classification=classification,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)

                if not can_use_llm:
                    degraded_steps.append(step.value)

                # Capture token usage from LLM client if available
                input_tokens = 0
                output_tokens = 0
                if can_use_llm and llm_client is not None:
                    usage = llm_client.cumulative_usage()
                    input_tokens = usage.input_tokens
                    output_tokens = usage.output_tokens

                # Build per-step metadata (Amendment 9)
                step_meta = StepMetadata(
                    step=_STEP_NUMBER[step],
                    step_name=step,
                    prompt_pack_version=prompt_pack_version,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration_ms=duration_ms,
                    generation_mode=generation_mode,
                )
                step_metadata_list.append(step_meta.model_dump(mode="json"))

                # Build audit metadata (enriched with Amendment 9 fields)
                metadata = {
                    "generation_mode": generation_mode,
                    "context_hash": _compute_context_hash(accumulated_context),
                    "classification": classification.value,
                    "prompt_pack_version": prompt_pack_version,
                    "duration_ms": duration_ms,
                    "provider": provider,
                    "model": model,
                }

                # Persist artifact
                await artifact_repo.create(
                    artifact_id=new_uuid7(),
                    plan_id=plan_id,
                    step=step.value,
                    payload=payload,
                    disclosure_tier=_STEP_DISCLOSURE[step].value,
                    metadata_json=metadata,
                )

                # Feed output into accumulated context for next step
                self._merge_step_output(accumulated_context, step, payload)

                if step == DepthStepName.SUITE_PLANNING:
                    has_suite_plan = True

                logger.info(
                    "Depth plan %s: step %s completed (%s, %dms)",
                    plan_id, step.value, generation_mode, duration_ms,
                )

            except Exception as exc:
                logger.exception(
                    "Depth plan %s: step %s failed: %s",
                    plan_id, step.value, exc,
                )
                degraded_steps.append(step.value)
                step_errors[step.value] = str(exc)

        # Determine final status
        if has_suite_plan:
            final_status = DepthPlanStatus.COMPLETED
        elif any(step.value not in step_errors for step in self.STEPS):
            final_status = DepthPlanStatus.PARTIAL
        else:
            final_status = DepthPlanStatus.FAILED

        # Update plan with final status
        error_msg = None
        if step_errors:
            error_msg = "; ".join(
                f"{k}: {v}" for k, v in step_errors.items()
            )

        await plan_repo.update_status(
            plan_id,
            final_status.value,
            current_step=None,
            error_message=error_msg,
            degraded_steps=degraded_steps,
            step_errors=step_errors,
            step_metadata=step_metadata_list,
        )

        return final_status

    def _merge_step_output(
        self,
        context: dict,
        step: DepthStepName,
        payload: dict,
    ) -> None:
        """Merge step output into accumulated context for downstream steps."""
        if step == DepthStepName.KHAWATIR:
            context["candidates"] = payload.get("candidates", [])
        elif step == DepthStepName.MURAQABA:
            context["bias_register"] = payload.get("bias_register", {})
            # MVP-9: pass assumption drafts downstream
            context["assumption_drafts"] = payload.get("assumption_drafts", [])
        elif step == DepthStepName.MUJAHADA:
            context["contrarians"] = payload.get("contrarians", [])
            context["qualitative_risks"] = payload.get("qualitative_risks", [])
        elif step == DepthStepName.MUHASABA:
            context["scored"] = payload.get("scored", [])
