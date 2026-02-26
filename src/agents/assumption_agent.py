"""Assumption drafting agent — MVP-8.

Given a residual bucket or ambiguous mapping, draft an Assumption with
value, range, units, and justification. Human must approve — agent
drafts only.

CRITICAL: Agent drafts assumptions — NEVER computes economic results.
All outputs are DRAFT status and require human approval.
"""

from pydantic import BaseModel, Field

from src.models.common import AssumptionStatus, AssumptionType
from src.models.governance import Assumption, AssumptionRange


# ---------------------------------------------------------------------------
# Input context
# ---------------------------------------------------------------------------


class ResidualContext(BaseModel):
    """Context describing a residual bucket or ambiguous mapping."""

    sector_code: str
    description: str
    total_value: float = 0.0
    currency: str = "SAR"
    coverage_pct: float = Field(default=1.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Draft output
# ---------------------------------------------------------------------------


class AssumptionDraft(BaseModel):
    """Draft assumption proposed by the agent — requires human approval."""

    assumption_type: AssumptionType
    value: float
    range_min: float | None = None
    range_max: float | None = None
    units: str
    justification: str
    status: AssumptionStatus = AssumptionStatus.DRAFT

    def to_assumption(self) -> Assumption:
        """Convert to a governed Assumption model."""
        assumption_range = None
        if self.range_min is not None and self.range_max is not None:
            assumption_range = AssumptionRange(
                min=self.range_min,
                max=self.range_max,
            )
        return Assumption(
            type=self.assumption_type,
            value=self.value,
            range=assumption_range,
            units=self.units,
            justification=self.justification,
            status=AssumptionStatus.DRAFT,
        )


# ---------------------------------------------------------------------------
# Assumption drafting agent
# ---------------------------------------------------------------------------

_DEFAULT_RANGE_PCT = 0.15  # ±15% default sensitivity range


class AssumptionDraftAgent:
    """Draft assumptions for residual buckets and ambiguous mappings."""

    def draft_import_share(
        self,
        *,
        context: ResidualContext,
        default_domestic: float,
    ) -> AssumptionDraft:
        """Draft an import share assumption from a domestic share default."""
        import_share = round(1.0 - default_domestic, 4)
        range_min = max(0.0, import_share - _DEFAULT_RANGE_PCT)
        range_max = min(1.0, import_share + _DEFAULT_RANGE_PCT)

        return AssumptionDraft(
            assumption_type=AssumptionType.IMPORT_SHARE,
            value=import_share,
            range_min=round(range_min, 4),
            range_max=round(range_max, 4),
            units="share",
            justification=(
                f"Import share assumption for sector {context.sector_code}: "
                f"{context.description}. "
                f"BoQ coverage is {context.coverage_pct:.0%}. "
                f"Default domestic share {default_domestic:.0%} implies "
                f"import share of {import_share:.0%}. "
                f"Range ±{_DEFAULT_RANGE_PCT:.0%} for sensitivity analysis."
            ),
        )

    def draft_phasing(
        self,
        *,
        context: ResidualContext,
        years: list[int],
    ) -> AssumptionDraft:
        """Draft a phasing profile assumption."""
        n_years = len(years)
        return AssumptionDraft(
            assumption_type=AssumptionType.PHASING,
            value=float(n_years),
            range_min=max(1.0, n_years - 1.0),
            range_max=n_years + 1.0,
            units="profile",
            justification=(
                f"Phasing assumption for sector {context.sector_code}: "
                f"even distribution across {n_years} years "
                f"({years[0]}–{years[-1]}). "
                f"Sensitivity range: {max(1, n_years - 1)} to {n_years + 1} years."
            ),
        )

    def draft_generic(
        self,
        *,
        assumption_type: AssumptionType,
        value: float,
        units: str,
        justification: str,
        range_pct: float = _DEFAULT_RANGE_PCT,
    ) -> AssumptionDraft:
        """Draft a generic assumption with configurable range."""
        range_min = value * (1.0 - range_pct)
        range_max = value * (1.0 + range_pct)

        return AssumptionDraft(
            assumption_type=assumption_type,
            value=value,
            range_min=range_min,
            range_max=range_max,
            units=units,
            justification=justification,
        )

    def build_assumption_prompt(self, context: ResidualContext) -> str:
        """Build a prompt for LLM-assisted assumption drafting."""
        lines = [
            "You are an economic analyst drafting assumptions for impact modeling.",
            "Draft an assumption for the following residual/uncovered spend bucket.",
            "",
            f"Sector: {context.sector_code}",
            f"Description: {context.description}",
            f"Total value: {context.total_value:,.0f} {context.currency}",
            f"BoQ coverage: {context.coverage_pct:.0%}",
            "",
            "Respond with JSON:",
            '{"assumption_type": "IMPORT_SHARE|PHASING|...", "value": X.XX, '
            '"range_min": X.XX, "range_max": X.XX, "units": "...", '
            '"justification": "..."}',
        ]
        return "\n".join(lines)
