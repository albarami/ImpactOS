"""Tests for health and readiness checks (MVP-7).

Covers: comprehensive system health — database, object storage, model
versions, minimum library sizes for pilot readiness.
"""

import pytest
from uuid_extensions import uuid7

from src.observability.health import (
    ComponentStatus,
    HealthChecker,
    HealthReport,
    PilotReadiness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _healthy_deps() -> dict:
    return {
        "database": True,
        "object_storage": True,
        "model_versions_loaded": 3,
        "mapping_library_size": 100,
        "assumption_library_size": 30,
        "pattern_library_size": 15,
    }


def _unhealthy_deps() -> dict:
    return {
        "database": False,
        "object_storage": True,
        "model_versions_loaded": 0,
        "mapping_library_size": 5,
        "assumption_library_size": 2,
        "pattern_library_size": 0,
    }


# ===================================================================
# Health report
# ===================================================================


class TestHealthReport:
    """Comprehensive health check."""

    def test_all_healthy(self) -> None:
        checker = HealthChecker()
        report = checker.check(_healthy_deps())
        assert report.overall_status == "healthy"

    def test_database_down(self) -> None:
        deps = _healthy_deps()
        deps["database"] = False
        checker = HealthChecker()
        report = checker.check(deps)
        assert report.overall_status == "unhealthy"

    def test_storage_down(self) -> None:
        deps = _healthy_deps()
        deps["object_storage"] = False
        checker = HealthChecker()
        report = checker.check(deps)
        assert report.overall_status == "unhealthy"

    def test_report_has_components(self) -> None:
        checker = HealthChecker()
        report = checker.check(_healthy_deps())
        assert len(report.components) >= 2

    def test_component_status_fields(self) -> None:
        checker = HealthChecker()
        report = checker.check(_healthy_deps())
        for comp in report.components:
            assert isinstance(comp, ComponentStatus)
            assert comp.name is not None
            assert comp.healthy is not None


# ===================================================================
# Pilot readiness
# ===================================================================


class TestPilotReadiness:
    """Minimum requirements for pilot readiness."""

    def test_ready_when_all_met(self) -> None:
        checker = HealthChecker()
        readiness = checker.pilot_readiness(_healthy_deps())
        assert readiness.ready is True

    def test_not_ready_no_models(self) -> None:
        deps = _healthy_deps()
        deps["model_versions_loaded"] = 0
        checker = HealthChecker()
        readiness = checker.pilot_readiness(deps)
        assert readiness.ready is False

    def test_not_ready_small_library(self) -> None:
        deps = _healthy_deps()
        deps["mapping_library_size"] = 5
        checker = HealthChecker()
        readiness = checker.pilot_readiness(deps)
        assert readiness.ready is False

    def test_blocking_reasons_listed(self) -> None:
        checker = HealthChecker()
        readiness = checker.pilot_readiness(_unhealthy_deps())
        assert len(readiness.blocking_reasons) >= 1

    def test_no_blocking_when_ready(self) -> None:
        checker = HealthChecker()
        readiness = checker.pilot_readiness(_healthy_deps())
        assert len(readiness.blocking_reasons) == 0

    def test_readiness_to_dict(self) -> None:
        checker = HealthChecker()
        readiness = checker.pilot_readiness(_healthy_deps())
        d = readiness.to_dict()
        assert "ready" in d
        assert "blocking_reasons" in d
        assert "checks" in d
