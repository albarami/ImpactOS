"""Tests for dashboard data service (MVP-7).

Covers: aggregate metrics across engagements — scenario throughput trends,
average cycle time, NFF compliance rates, library growth.
"""

import pytest
from uuid_extensions import uuid7

from src.observability.dashboard import DashboardService, DashboardSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engagement_data() -> list[dict]:
    return [
        {
            "engagement_id": str(uuid7()),
            "name": "NEOM Logistics",
            "scenarios_count": 8,
            "cycle_time_hours": 48.0,
            "nff_passed": True,
            "claims_total": 20,
            "claims_supported": 18,
        },
        {
            "engagement_id": str(uuid7()),
            "name": "Jeddah Tower",
            "scenarios_count": 5,
            "cycle_time_hours": 72.0,
            "nff_passed": True,
            "claims_total": 15,
            "claims_supported": 12,
        },
        {
            "engagement_id": str(uuid7()),
            "name": "Red Sea Tourism",
            "scenarios_count": 12,
            "cycle_time_hours": 36.0,
            "nff_passed": False,
            "claims_total": 25,
            "claims_supported": 20,
        },
    ]


def _make_library_data() -> dict:
    return {
        "mappings_count": 150,
        "assumptions_count": 45,
        "patterns_count": 20,
    }


# ===================================================================
# Dashboard summary
# ===================================================================


class TestDashboardSummary:
    """Aggregate metrics across engagements."""

    def test_total_engagements(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert summary.total_engagements == 3

    def test_total_scenarios(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert summary.total_scenarios == 25  # 8 + 5 + 12

    def test_average_scenarios_per_engagement(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert summary.avg_scenarios_per_engagement == pytest.approx(25 / 3)

    def test_average_cycle_time(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        expected = (48.0 + 72.0 + 36.0) / 3
        assert summary.avg_cycle_time_hours == pytest.approx(expected)

    def test_nff_compliance_rate(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert summary.nff_compliance_rate == pytest.approx(2 / 3)

    def test_library_growth(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert summary.library_mappings == 150
        assert summary.library_assumptions == 45
        assert summary.library_patterns == 20


# ===================================================================
# Throughput trends
# ===================================================================


class TestThroughputTrends:
    """Scenario throughput trends."""

    def test_throughput_list(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        assert len(summary.scenario_throughput) == 3
        assert summary.scenario_throughput[0] == 8

    def test_claim_support_rate(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        # (18+12+20) / (20+15+25) = 50/60
        assert summary.avg_claim_support_rate == pytest.approx(50 / 60)


# ===================================================================
# Empty data
# ===================================================================


class TestEmptyData:
    """Handle no engagements gracefully."""

    def test_empty_engagements(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=[],
            library=_make_library_data(),
        )
        assert summary.total_engagements == 0
        assert summary.avg_cycle_time_hours == 0.0
        assert summary.nff_compliance_rate == 0.0

    def test_to_dict(self) -> None:
        svc = DashboardService()
        summary = svc.compute_summary(
            engagements=_make_engagement_data(),
            library=_make_library_data(),
        )
        d = summary.to_dict()
        assert isinstance(d, dict)
        assert "total_engagements" in d
        assert "avg_cycle_time_hours" in d
