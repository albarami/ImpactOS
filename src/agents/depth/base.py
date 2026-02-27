"""Abstract base class for depth engine step agents.

Each step agent is stateless. It takes context + optional LLM client,
returns a typed dict payload. No side effects.
"""

from abc import ABC, abstractmethod

from src.agents.llm_client import LLMClient
from src.models.common import DataClassification
from src.models.depth import DepthStepName


class DepthStepAgent(ABC):
    """Abstract base for a single step of the Al-Muhasabi depth engine.

    Subclasses implement `run()` which:
    1. Checks if LLM is available for the given classification
    2. If yes: builds prompt, calls LLM, parses structured output
    3. If no: returns deterministic fallback output
    """

    step_name: DepthStepName

    @abstractmethod
    def run(
        self,
        *,
        context: dict,
        llm_client: LLMClient | None = None,
        classification: DataClassification = DataClassification.INTERNAL,
    ) -> dict:
        """Execute this step and return the artifact payload.

        Args:
            context: Accumulated context from previous steps + scenario metadata.
            llm_client: Optional LLM client for AI-assisted mode.
            classification: Workspace data classification for provider routing.

        Returns:
            Serializable dict (model_dump of typed output model).
        """
        ...

    def _can_use_llm(
        self,
        llm_client: LLMClient | None,
        classification: DataClassification,
    ) -> bool:
        """Check if LLM is available for this classification level."""
        if llm_client is None:
            return False
        return llm_client.is_available_for(classification)
