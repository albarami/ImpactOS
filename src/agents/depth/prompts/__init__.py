"""Prompt templates for depth engine steps.

The Al-Muhasabi structured reasoning methodology and framework are the
intellectual property of Salim Al-Barami, licensed to Strategic Gears
for use within ImpactOS. The software implementation, prompt engineering,
and system integration are part of the ImpactOS platform.

PromptPack provides versioned access to all 5 step prompts. Each pack
has an immutable version string used for reproducibility tracking in
StepMetadata and DepthArtifact audit metadata.
"""

from collections.abc import Callable
from dataclasses import dataclass

from src.agents.depth.prompts import (
    khawatir,
    muhasaba,
    mujahada,
    muraqaba,
    suite,
)
from src.models.depth import DepthStepName

# Current prompt pack version — bump on any prompt change
PROMPT_PACK_VERSION = "mvp9_v1"


@dataclass(frozen=True)
class PromptPack:
    """Versioned collection of prompt builders for all 5 depth steps.

    Immutable by design: once created, the version and builders cannot
    change. This ensures audit metadata accurately reflects which prompts
    produced a given artifact.

    Usage::

        pack = PromptPack.current()
        prompt = pack.build(DepthStepName.KHAWATIR, context)
        print(pack.version)  # "mvp9_v1"
    """

    version: str
    builders: dict[DepthStepName, Callable[[dict], str]]

    def build(self, step: DepthStepName, context: dict) -> str:
        """Build the prompt for a given step and context.

        Raises KeyError if step is not in this pack.
        """
        builder = self.builders[step]
        return builder(context)

    def has_step(self, step: DepthStepName) -> bool:
        """Check if this pack has a builder for the given step."""
        return step in self.builders

    @classmethod
    def current(cls) -> "PromptPack":
        """Get the current prompt pack with all 5 step builders."""
        return cls(
            version=PROMPT_PACK_VERSION,
            builders={
                DepthStepName.KHAWATIR: khawatir.build_prompt,
                DepthStepName.MURAQABA: muraqaba.build_prompt,
                DepthStepName.MUJAHADA: mujahada.build_prompt,
                DepthStepName.MUHASABA: muhasaba.build_prompt,
                DepthStepName.SUITE_PLANNING: suite.build_prompt,
            },
        )
