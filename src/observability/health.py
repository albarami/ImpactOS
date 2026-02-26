"""Health and readiness checks — MVP-7.

Comprehensive system health beyond basic /health — database connectivity,
object storage accessibility, required model versions loaded, minimum
library sizes for pilot readiness.

Deterministic — no LLM calls.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Thresholds for pilot readiness
# ---------------------------------------------------------------------------

MIN_MODEL_VERSIONS = 1
MIN_MAPPING_LIBRARY = 10
MIN_ASSUMPTION_LIBRARY = 5
MIN_PATTERN_LIBRARY = 3


@dataclass
class ComponentStatus:
    """Status of a single infrastructure component."""

    name: str
    healthy: bool
    detail: str = ""


@dataclass
class HealthReport:
    """Overall system health report."""

    overall_status: str  # "healthy" | "unhealthy"
    components: list[ComponentStatus] = field(default_factory=list)


@dataclass
class PilotReadiness:
    """Pilot readiness assessment."""

    ready: bool
    blocking_reasons: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "blocking_reasons": self.blocking_reasons,
            "checks": self.checks,
        }


class HealthChecker:
    """Evaluate system health and pilot readiness."""

    def check(self, deps: dict) -> HealthReport:
        """Run comprehensive health check against dependency status."""
        components: list[ComponentStatus] = []

        db_ok = deps.get("database", False)
        components.append(ComponentStatus(
            name="database",
            healthy=db_ok,
            detail="" if db_ok else "database unreachable",
        ))

        storage_ok = deps.get("object_storage", False)
        components.append(ComponentStatus(
            name="object_storage",
            healthy=storage_ok,
            detail="" if storage_ok else "object storage unreachable",
        ))

        overall = "healthy" if all(c.healthy for c in components) else "unhealthy"

        return HealthReport(overall_status=overall, components=components)

    def pilot_readiness(self, deps: dict) -> PilotReadiness:
        """Assess whether system meets minimum pilot requirements."""
        blocking: list[str] = []
        checks: dict[str, bool] = {}

        # Infrastructure
        db_ok = deps.get("database", False)
        checks["database"] = db_ok
        if not db_ok:
            blocking.append("Database is not connected")

        storage_ok = deps.get("object_storage", False)
        checks["object_storage"] = storage_ok
        if not storage_ok:
            blocking.append("Object storage is not accessible")

        # Model versions
        models = deps.get("model_versions_loaded", 0)
        models_ok = models >= MIN_MODEL_VERSIONS
        checks["model_versions"] = models_ok
        if not models_ok:
            blocking.append(
                f"Insufficient model versions: {models} < {MIN_MODEL_VERSIONS}"
            )

        # Library sizes
        mappings = deps.get("mapping_library_size", 0)
        mappings_ok = mappings >= MIN_MAPPING_LIBRARY
        checks["mapping_library"] = mappings_ok
        if not mappings_ok:
            blocking.append(
                f"Mapping library too small: {mappings} < {MIN_MAPPING_LIBRARY}"
            )

        assumptions = deps.get("assumption_library_size", 0)
        assumptions_ok = assumptions >= MIN_ASSUMPTION_LIBRARY
        checks["assumption_library"] = assumptions_ok
        if not assumptions_ok:
            blocking.append(
                f"Assumption library too small: {assumptions} < {MIN_ASSUMPTION_LIBRARY}"
            )

        patterns = deps.get("pattern_library_size", 0)
        patterns_ok = patterns >= MIN_PATTERN_LIBRARY
        checks["pattern_library"] = patterns_ok
        if not patterns_ok:
            blocking.append(
                f"Pattern library too small: {patterns} < {MIN_PATTERN_LIBRARY}"
            )

        ready = len(blocking) == 0

        return PilotReadiness(
            ready=ready,
            blocking_reasons=blocking,
            checks=checks,
        )
