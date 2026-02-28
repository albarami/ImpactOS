"""Constraint schema — Pydantic models for feasibility constraints.

Reuses ConstraintConfidence from src/models/common.py (HARD/ESTIMATED/ASSUMED).

Amendments applied:
1. ConstraintBoundScope — ABSOLUTE_TOTAL vs DELTA_ONLY
2. BUDGET removed from solver (pre-solve only)
3. ConstraintScope — richer than bare sector_code
4. Economy-wide allocation rules
5. SAUDIZATION = compliance diagnostic only
6. ConstraintUnit typed enum
7. Ramp = base-to-target growth cap (not YoY sequential)
9. ConstraintConfidenceSummary in results
12. Rich ConstraintSet.validate()
"""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.models.common import (
    ConstraintConfidence,
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ConstraintType(StrEnum):
    """Categories of feasibility constraints."""

    CAPACITY_CAP = "CAPACITY_CAP"     # Max absolute output per sector
    RAMP = "RAMP"                      # Max growth rate relative to base
    LABOR = "LABOR"                    # Max jobs by sector/skill group
    IMPORT = "IMPORT"                  # Max imported inputs growth
    BUDGET = "BUDGET"                  # Budget ceiling (PRE-SOLVE only)
    SAUDIZATION = "SAUDIZATION"        # Min Saudi share (DIAGNOSTIC only)
    OTHER = "OTHER"


# Amendment 2: constraints that are pre-solve (before Leontief) vs post-solve
PRE_SOLVE_TYPES: frozenset[ConstraintType] = frozenset({
    ConstraintType.BUDGET,
})

# Amendment 5: constraints that are compliance diagnostics (don't clip output)
DIAGNOSTIC_ONLY_TYPES: frozenset[ConstraintType] = frozenset({
    ConstraintType.SAUDIZATION,
})

# Post-solve clipping types
POST_SOLVE_CLIPPING_TYPES: frozenset[ConstraintType] = frozenset({
    ConstraintType.CAPACITY_CAP,
    ConstraintType.RAMP,
    ConstraintType.LABOR,
    ConstraintType.IMPORT,
})


class ConstraintBoundScope(StrEnum):
    """Whether the bound applies to total output or the change only.

    Amendment 1: explicit bound scope.
    """

    ABSOLUTE_TOTAL = "ABSOLUTE_TOTAL"  # Cap on base_x + delta_x
    DELTA_ONLY = "DELTA_ONLY"          # Cap on delta_x itself


class ConstraintUnit(StrEnum):
    """Typed unit for constraint values.

    Amendment 6: replaces free-form ``unit: str``.
    """

    SAR = "SAR"
    SAR_THOUSANDS = "SAR_THOUSANDS"
    SAR_MILLIONS = "SAR_MILLIONS"
    JOBS = "JOBS"
    FRACTION = "FRACTION"
    GROWTH_RATE = "GROWTH_RATE"


# ---------------------------------------------------------------------------
# Amendment 3: Richer constraint scope
# ---------------------------------------------------------------------------


class ConstraintScope(ImpactOSBase):
    """What a constraint applies to.

    Amendment 3: replaces bare ``sector_code: str | None``.

    - sector: applies to a single sector
    - group: applies to a group of sectors jointly
    - all: economy-wide, needs allocation_rule (Amendment 4)
    """

    scope_type: Literal["sector", "group", "all"]
    scope_values: list[str] | None = None  # Sector codes or group ids
    allocation_rule: Literal["proportional", "equal", "priority"] | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> "ConstraintScope":
        if self.scope_type == "sector":
            if not self.scope_values or len(self.scope_values) != 1:
                raise ValueError(
                    "scope_type='sector' requires exactly one scope_values entry."
                )
        elif self.scope_type == "group":
            if not self.scope_values or len(self.scope_values) < 2:
                raise ValueError(
                    "scope_type='group' requires at least two scope_values entries."
                )
        elif self.scope_type == "all":
            if self.scope_values is not None:
                raise ValueError(
                    "scope_type='all' must have scope_values=None."
                )
        return self


# Default bound scopes per constraint type
_DEFAULT_BOUND_SCOPE: dict[ConstraintType, ConstraintBoundScope] = {
    ConstraintType.CAPACITY_CAP: ConstraintBoundScope.ABSOLUTE_TOTAL,
    ConstraintType.RAMP: ConstraintBoundScope.ABSOLUTE_TOTAL,
    ConstraintType.LABOR: ConstraintBoundScope.ABSOLUTE_TOTAL,
    ConstraintType.IMPORT: ConstraintBoundScope.ABSOLUTE_TOTAL,
    ConstraintType.BUDGET: ConstraintBoundScope.DELTA_ONLY,
    ConstraintType.SAUDIZATION: ConstraintBoundScope.ABSOLUTE_TOTAL,
    ConstraintType.OTHER: ConstraintBoundScope.DELTA_ONLY,
}


# ---------------------------------------------------------------------------
# Core Constraint model
# ---------------------------------------------------------------------------


class Constraint(ImpactOSBase):
    """A single feasibility constraint.

    Matches the data build pack schema (Section 3.4).
    """

    constraint_id: UUIDv7 = Field(default_factory=new_uuid7)
    constraint_type: ConstraintType
    scope: ConstraintScope
    description: str

    # Bound definition — at least one must be set
    upper_bound: float | None = None
    lower_bound: float | None = None
    max_growth_rate: float | None = None  # e.g. 0.12 = 12%

    # Amendment 1: explicit bound scope
    bound_scope: ConstraintBoundScope | None = None

    # Amendment 6: typed unit
    unit: ConstraintUnit

    # Time scope
    time_window: tuple[int, int] | None = None  # (start_year, end_year)

    # Governance metadata
    confidence: ConstraintConfidence
    evidence_refs: list[UUID] | None = None
    owner: str | None = None  # "client" or "steward"
    notes: str | None = None

    @model_validator(mode="after")
    def _validate_bounds(self) -> "Constraint":
        """At least one bound must be set; lower cannot exceed upper."""
        has_bound = (
            self.upper_bound is not None
            or self.lower_bound is not None
            or self.max_growth_rate is not None
        )
        if not has_bound:
            raise ValueError(
                "At least one of upper_bound, lower_bound, or "
                "max_growth_rate must be set."
            )
        if (
            self.upper_bound is not None
            and self.lower_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError(
                f"lower_bound ({self.lower_bound}) > upper_bound "
                f"({self.upper_bound}) — invalid constraint."
            )
        return self

    @property
    def effective_bound_scope(self) -> ConstraintBoundScope:
        """Return bound_scope, falling back to the type default."""
        if self.bound_scope is not None:
            return self.bound_scope
        return _DEFAULT_BOUND_SCOPE.get(
            self.constraint_type, ConstraintBoundScope.DELTA_ONLY,
        )

    @property
    def is_pre_solve(self) -> bool:
        """Whether this constraint applies before Leontief (Amendment 2)."""
        return self.constraint_type in PRE_SOLVE_TYPES

    @property
    def is_diagnostic_only(self) -> bool:
        """Whether this constraint is diagnostic-only (Amendment 5)."""
        return self.constraint_type in DIAGNOSTIC_ONLY_TYPES

    @property
    def is_post_solve_clipping(self) -> bool:
        """Whether this constraint clips output in the solver."""
        return self.constraint_type in POST_SOLVE_CLIPPING_TYPES

    def applies_to_sector(self, sector_code: str) -> bool:
        """Check if this constraint applies to a given sector."""
        if self.scope.scope_type == "all":
            return True
        if self.scope.scope_values is None:
            return False
        return sector_code in self.scope.scope_values

    def applies_in_year(self, year: int | None) -> bool:
        """Check if this constraint is active in the given year."""
        if year is None or self.time_window is None:
            return True
        start, end = self.time_window
        return start <= year <= end


# ---------------------------------------------------------------------------
# ConstraintSet — versioned collection
# ---------------------------------------------------------------------------


class ConstraintSet(ImpactOSBase):
    """A versioned collection of constraints for a scenario run."""

    constraint_set_id: UUIDv7 = Field(default_factory=new_uuid7)
    workspace_id: UUID
    model_version_id: UUID
    name: str
    constraints: list[Constraint] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: UTCTimestamp = Field(default_factory=utc_now)

    def get_constraints_for_sector(
        self,
        sector_code: str,
        *,
        year: int | None = None,
    ) -> list[Constraint]:
        """Get all constraints that apply to a sector (sector-specific + economy-wide)."""
        return [
            c for c in self.constraints
            if c.applies_to_sector(sector_code) and c.applies_in_year(year)
        ]

    def get_constraints_by_type(
        self,
        constraint_type: ConstraintType,
    ) -> list[Constraint]:
        """Get all constraints of a given type."""
        return [
            c for c in self.constraints
            if c.constraint_type == constraint_type
        ]

    def get_post_solve_constraints(
        self,
        *,
        year: int | None = None,
    ) -> list[Constraint]:
        """Get only post-solve clipping constraints active in the given year."""
        return [
            c for c in self.constraints
            if c.is_post_solve_clipping and c.applies_in_year(year)
        ]

    def get_diagnostic_constraints(
        self,
        *,
        year: int | None = None,
    ) -> list[Constraint]:
        """Get only diagnostic (non-clipping) constraints."""
        return [
            c for c in self.constraints
            if c.is_diagnostic_only and c.applies_in_year(year)
        ]

    def get_pre_solve_constraints(self) -> list[Constraint]:
        """Get only pre-solve constraints (Amendment 2)."""
        return [c for c in self.constraints if c.is_pre_solve]

    def validate(self) -> list[str]:
        """Check for conflicts and issues (Amendment 12).

        Returns a list of warning/error messages. Empty list = valid.
        """
        issues: list[str] = []

        # Check lower > upper on same constraint
        for c in self.constraints:
            if (
                c.upper_bound is not None
                and c.lower_bound is not None
                and c.lower_bound > c.upper_bound
            ):
                issues.append(
                    f"Constraint {c.constraint_id}: lower_bound "
                    f"({c.lower_bound}) > upper_bound ({c.upper_bound})"
                )

        # Check for duplicate constraints on same scope + type + time window
        seen: dict[tuple, list[UUID]] = {}
        for c in self.constraints:
            scope_key = (
                c.constraint_type.value,
                c.scope.scope_type,
                tuple(c.scope.scope_values) if c.scope.scope_values else (),
                c.time_window,
            )
            if scope_key not in seen:
                seen[scope_key] = []
            seen[scope_key].append(c.constraint_id)

        for key, ids in seen.items():
            if len(ids) > 1:
                issues.append(
                    f"Duplicate constraints on {key[0]} / "
                    f"{key[1]}={key[2]}: {len(ids)} entries"
                )

        # Economy-wide constraints should have allocation_rule
        for c in self.constraints:
            if c.scope.scope_type == "all" and c.is_post_solve_clipping:
                if c.scope.allocation_rule is None:
                    issues.append(
                        f"Constraint {c.constraint_id}: economy-wide "
                        f"{c.constraint_type.value} missing allocation_rule"
                    )

        # Unsupported allocation rules for v1
        for c in self.constraints:
            if (
                c.scope.allocation_rule is not None
                and c.scope.allocation_rule not in ("proportional",)
            ):
                issues.append(
                    f"Constraint {c.constraint_id}: allocation_rule "
                    f"'{c.scope.allocation_rule}' not implemented in v1 "
                    f"(only 'proportional' supported)"
                )

        return issues
