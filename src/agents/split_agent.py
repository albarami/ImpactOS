"""Domestic/import split agent — MVP-8.

Given a mapped line item + sector, propose domestic_share and import_share
based on trade data patterns and sector norms. Output as structured JSON
with assumption rationale. Falls back to library defaults if LLM unavailable.

CRITICAL: Agent proposes splits only — NEVER computes economic results.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

# Global fallback when no sector-specific default exists
_GLOBAL_DOMESTIC_DEFAULT = 0.50
_GLOBAL_IMPORT_DEFAULT = 0.50


class SplitDefaults(BaseModel):
    """Default domestic/import split for a sector from reference data."""

    sector_code: str
    domestic_share: float = Field(ge=0.0, le=1.0)
    import_share: float = Field(ge=0.0, le=1.0)
    source: str = ""


class SplitProposal(BaseModel):
    """A proposed domestic/import split for a line item."""

    sector_code: str
    domestic_share: float = Field(ge=0.0, le=1.0)
    import_share: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    source: str


# ---------------------------------------------------------------------------
# Split agent
# ---------------------------------------------------------------------------


class SplitAgent:
    """Propose domestic/import splits for mapped line items."""

    def __init__(self, defaults: list[SplitDefaults] | None = None) -> None:
        self._defaults_map: dict[str, SplitDefaults] = {}
        if defaults:
            for d in defaults:
                self._defaults_map[d.sector_code] = d

    def propose_split(
        self,
        *,
        sector_code: str,
        line_item_text: str,
    ) -> SplitProposal:
        """Propose domestic/import split for a single line item."""
        default = self._defaults_map.get(sector_code)

        if default:
            return SplitProposal(
                sector_code=sector_code,
                domestic_share=default.domestic_share,
                import_share=default.import_share,
                confidence=0.75,
                rationale=(
                    f"Based on sector {sector_code} trade data default: "
                    f"{default.domestic_share:.0%} domestic, "
                    f"{default.import_share:.0%} import."
                ),
                source=default.source or "sector defaults",
            )

        # Global fallback
        return SplitProposal(
            sector_code=sector_code,
            domestic_share=_GLOBAL_DOMESTIC_DEFAULT,
            import_share=_GLOBAL_IMPORT_DEFAULT,
            confidence=0.3,
            rationale=(
                f"No sector-specific default for {sector_code}; "
                f"using global fallback 50/50 split."
            ),
            source="global fallback",
        )

    def propose_batch(
        self,
        items: list[tuple[str, str]],
    ) -> list[SplitProposal]:
        """Propose splits for a batch of (sector_code, line_item_text) pairs."""
        return [
            self.propose_split(sector_code=sector, line_item_text=text)
            for sector, text in items
        ]

    def build_split_prompt(
        self,
        *,
        sector_code: str,
        line_item_text: str,
    ) -> str:
        """Build a prompt for LLM-assisted split estimation."""
        lines = [
            "You are an economic analyst estimating domestic vs import shares.",
            "Given a procurement line item and its mapped sector, propose the",
            "likely domestic_share and import_share (must sum to 1.0).",
            "",
            f"Sector code: {sector_code}",
            f"Line item: \"{line_item_text}\"",
        ]

        default = self._defaults_map.get(sector_code)
        if default:
            lines.append("")
            lines.append(
                f"Reference default for sector {sector_code}: "
                f"domestic={default.domestic_share}, import={default.import_share} "
                f"(source: {default.source})"
            )

        lines.append("")
        lines.append(
            "Respond with JSON: "
            '{"domestic_share": 0.XX, "import_share": 0.XX, "rationale": "..."}'
        )

        return "\n".join(lines)
