"""Agent fail-closed guards — Issue #17.

Centralized environment-aware guard that enforces real LLM backing
for governed agent paths in non-dev environments.
"""

import logging

from src.agents.llm_client import ProviderUnavailableError

_logger = logging.getLogger(__name__)

_NON_DEV_ENVIRONMENTS = frozenset({"staging", "prod"})


def require_llm_backing(
    *,
    agent_name: str,
    environment: str,
    has_llm: bool,
    reason_code: str,
) -> None:
    """Raise ProviderUnavailableError in non-dev if agent lacks LLM backing.

    In dev: logs warning, returns normally (deterministic fallback allowed).
    In non-dev: raises with structured reason_code for API translation.
    """
    if has_llm:
        return

    if environment in _NON_DEV_ENVIRONMENTS:
        raise ProviderUnavailableError(
            f"{agent_name} has no LLM backing in {environment} "
            f"(reason: {reason_code}). Deterministic fallback is "
            f"not permitted in governed non-dev flows.",
            reason_code=reason_code,
            agent_name=agent_name,
            environment=environment,
        )

    _logger.warning(
        "%s has no LLM backing — deterministic fallback allowed in %s "
        "(reason: %s)",
        agent_name,
        environment,
        reason_code,
    )
