"""Default Saudi constraint templates for the Feasibility Layer.

Provides sector-specific defaults based on D-3/D-4 research that
analysts can customize per engagement. All defaults are confidence: ASSUMED
with explicit rationale in notes.

These are starting points. The Knowledge Flywheel (MVP-12) refines them
per engagement.
"""

from uuid import UUID

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence, new_uuid7

# ---------------------------------------------------------------------------
# Sector-specific ramp rate defaults (max YoY growth relative to base)
# ---------------------------------------------------------------------------

# ISIC Rev 4 section codes → max growth rate
_SECTOR_MAX_GROWTH: dict[str, tuple[float, str]] = {
    "F": (0.15, "Construction: giga-project absorption bottleneck limits growth to ~15% pa"),
    "B": (0.08, "Mining/quarrying: extraction capacity expansion is capital-intensive, ~8% pa"),
    "C": (0.12, "Manufacturing: industrial diversification capacity ~12% pa"),
    "D": (0.10, "Utilities: grid/generation expansion ~10% pa"),
    "E": (0.10, "Water/waste: infrastructure-bound ~10% pa"),
    "G": (0.20, "Wholesale/retail: relatively flexible, ~20% pa"),
    "H": (0.15, "Transport/storage: fleet and infrastructure limits ~15% pa"),
    "I": (0.20, "Accommodation/food: tourism absorption ~20% pa"),
    "J": (0.25, "ICT: high scalability but talent-constrained ~25% pa"),
    "K": (0.15, "Financial services: regulatory and talent limits ~15% pa"),
    "L": (0.10, "Real estate: supply pipeline limits ~10% pa"),
    "M": (0.20, "Professional services: talent-constrained ~20% pa"),
    "N": (0.20, "Administrative services: ~20% pa"),
}

# General ramp limit for sectors without specific data
_DEFAULT_MAX_GROWTH = 0.25  # No sector can exceed 25% pa


def build_default_saudi_constraints(
    sector_codes: list[str],
    *,
    workspace_id: UUID | None = None,
    model_version_id: UUID | None = None,
) -> ConstraintSet:
    """Build a default constraint set based on Saudi economic structure.

    Defaults based on D-3/D-4 research:
    - Sector-specific max YoY growth rates (ramp constraints)
    - General cap: no sector can exceed 25% YoY growth
    - Labor: sector employment cannot exceed 2x current level

    All defaults marked confidence: ASSUMED with explicit rationale.

    Args:
        sector_codes: ISIC section codes to generate constraints for.
        workspace_id: Optional workspace binding.
        model_version_id: Optional model version binding.
    """
    ws_id = workspace_id or new_uuid7()
    mv_id = model_version_id or new_uuid7()
    constraints: list[Constraint] = []

    for code in sector_codes:
        growth_info = _SECTOR_MAX_GROWTH.get(code)
        if growth_info is not None:
            rate, rationale = growth_info
        else:
            rate = _DEFAULT_MAX_GROWTH
            rationale = (
                f"Sector {code}: no sector-specific data, "
                f"using general limit of {_DEFAULT_MAX_GROWTH:.0%} pa"
            )

        # Ramp constraint (Amendment 7: base-to-target growth cap)
        constraints.append(Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=[code]),
            description=f"Max growth rate for sector {code}",
            max_growth_rate=rate,
            bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
            notes=rationale,
        ))

    # Economy-wide general ramp limit
    constraints.append(Constraint(
        constraint_type=ConstraintType.RAMP,
        scope=ConstraintScope(
            scope_type="all",
            allocation_rule="proportional",
        ),
        description="General economy-wide growth cap: no sector exceeds 25% pa",
        max_growth_rate=_DEFAULT_MAX_GROWTH,
        bound_scope=ConstraintBoundScope.ABSOLUTE_TOTAL,
        unit=ConstraintUnit.GROWTH_RATE,
        confidence=ConstraintConfidence.ASSUMED,
        notes="General limit: no sector can grow faster than 25% in a single period",
    ))

    return ConstraintSet(
        workspace_id=ws_id,
        model_version_id=mv_id,
        name="Saudi default constraints (ASSUMED)",
        constraints=constraints,
        metadata={
            "source": "D-3/D-4 research defaults",
            "version": "mvp10_v1",
        },
    )
