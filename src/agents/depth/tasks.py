"""Celery async tasks for depth engine — follows ingestion/tasks.py pattern.

When CELERY_BROKER_URL is configured, depth plan runs in a Celery worker.
When empty (dev/test), depth plan runs synchronously inline.

The run_depth_plan function contains the shared orchestration logic
used by both sync and async paths.
"""

import asyncio
import logging
from uuid import UUID

from src.agents.depth.orchestrator import DepthOrchestrator
from src.agents.llm_client import LLMClient
from src.config.settings import get_settings
from src.models.common import DataClassification
from src.repositories.depth import DepthArtifactRepository, DepthPlanRepository

logger = logging.getLogger(__name__)

_orchestrator = DepthOrchestrator()


async def run_depth_plan(
    *,
    plan_id: UUID,
    workspace_id: UUID,
    context: dict,
    classification: str,
    plan_repo: DepthPlanRepository | None = None,
    artifact_repo: DepthArtifactRepository | None = None,
) -> str:
    """Run the full depth engine pipeline.

    This is the core orchestration function called by both the sync path
    (inline in the API endpoint) and the async path (Celery task).

    Returns:
        Final plan status string ("COMPLETED", "PARTIAL", or "FAILED").
    """
    settings = get_settings()

    # Build LLM client from settings
    llm_client: LLMClient | None = None
    cls = DataClassification(classification)

    if cls != DataClassification.RESTRICTED:
        llm_client = LLMClient(
            anthropic_key=settings.ANTHROPIC_API_KEY,
            openai_key=settings.OPENAI_API_KEY,
            openrouter_key=settings.OPENROUTER_API_KEY,
        )

    status = await _orchestrator.run(
        plan_id=plan_id,
        workspace_id=workspace_id,
        context=context,
        classification=cls,
        llm_client=llm_client,
        plan_repo=plan_repo,
        artifact_repo=artifact_repo,
    )

    return status.value


# ---------------------------------------------------------------------------
# Celery task wrapper
# ---------------------------------------------------------------------------


def _celery_depth_task(
    plan_id_str: str,
    workspace_id_str: str,
    context_json: dict,
    classification: str,
) -> str:
    """Celery task that runs depth plan in a worker process.

    Creates its own async session and runs the orchestration function.
    """
    from src.db.session import async_session_factory

    async def _run() -> str:
        async with async_session_factory() as session:
            plan_repo = DepthPlanRepository(session)
            artifact_repo = DepthArtifactRepository(session)

            result = await run_depth_plan(
                plan_id=UUID(plan_id_str),
                workspace_id=UUID(workspace_id_str),
                context=context_json,
                classification=classification,
                plan_repo=plan_repo,
                artifact_repo=artifact_repo,
            )

            await session.commit()
            return result

    return asyncio.run(_run())


def dispatch_depth_plan(
    *,
    plan_id: UUID,
    workspace_id: UUID,
    context: dict,
    classification: str,
) -> None:
    """Dispatch depth plan to Celery worker.

    Serializes all arguments as JSON-safe types for Celery transport.
    """
    settings = get_settings()
    if not settings.CELERY_BROKER_URL:
        logger.warning(
            "dispatch_depth_plan called but CELERY_BROKER_URL not set"
        )
        return

    from celery import Celery

    broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
    app = Celery("impactos", broker=broker_url, backend=broker_url)
    app.conf.task_serializer = "json"
    app.conf.result_serializer = "json"

    task = app.task(name="impactos.depth_plan")(_celery_depth_task)
    task.delay(
        str(plan_id),
        str(workspace_id),
        context,
        classification,
    )
