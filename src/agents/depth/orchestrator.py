"""Depth Engine Orchestrator — sequential 5-step pipeline.

Runs all 5 Al-Muhasabi steps in order, persisting each artifact.
Supports partial failure: if step N fails, steps 1..N-1 are preserved.

Status semantics:
- COMPLETED: Suite plan artifact exists (even if earlier steps used fallback)
- PARTIAL: Suite plan missing (some steps failed)
- FAILED: Critical failure (no artifacts produced)
"""

import hashlib
import json
import logging
from uuid import UUID

from src.agents.depth.base import DepthStepAgent  # noqa: F401
from src.agents.depth.khawatir import KhawatirAgent
from src.agents.depth.muhasaba import MuhasabaAgent
from src.agents.depth.mujahada import MujahadaAgent
from src.agents.depth.muraqaba import MuraqabaAgent
from src.agents.depth.suite_planner import SuitePlannerAgent
from src.agents.llm_client import LLMClient
from src.models.common import DataClassification, DisclosureTier, new_uuid7
from src.models.depth import DepthPlanStatus, DepthStepName
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
    """Sequential 5-step pipeline with persistence and partial failure handling."""

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
    ) -> DepthPlanStatus:
        """Execute the full 5-step depth engine pipeline.

        Each step:
        1. Update plan status -> RUNNING, current_step
        2. Run step agent (LLM or fallback)
        3. Persist artifact with metadata
        4. Feed output into accumulated context for next step

        On failure: log error, record degraded_step, continue.
        Final status: COMPLETED if suite plan exists, PARTIAL otherwise.
        """
        degraded_steps: list[str] = []
        step_errors: dict[str, str] = {}
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

                # Run the step
                payload = agent.run(
                    context=accumulated_context,
                    llm_client=llm_client,
                    classification=classification,
                )

                if not can_use_llm:
                    degraded_steps.append(step.value)

                # Build audit metadata
                metadata = {
                    "generation_mode": generation_mode,
                    "context_hash": _compute_context_hash(accumulated_context),
                    "classification": classification.value,
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
                    "Depth plan %s: step %s completed (%s)",
                    plan_id, step.value, generation_mode,
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
        elif step == DepthStepName.MUJAHADA:
            context["contrarians"] = payload.get("contrarians", [])
            context["qualitative_risks"] = payload.get("qualitative_risks", [])
        elif step == DepthStepName.MUHASABA:
            context["scored"] = payload.get("scored", [])
