"""Tests for governed nowcasting service (Task 8, Amendment 8).

Covers: NowcastingService lifecycle (draft/approve/reject),
TargetTotalProvenance, NowcastResult model, structural change
magnitude, quality warnings, and ModelStore integration.

Deterministic -- no LLM calls.
"""

from uuid import UUID

import numpy as np
import pytest

from src.engine.model_store import ModelStore
from src.quality.models import (
    NowcastStatus,
    QualityDimension,
    QualitySeverity,
)
from src.quality.nowcast import (
    NowcastingService,
    NowcastResult,
    TargetTotalProvenance,
)


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture()
def store_and_mv() -> tuple:
    """Create a ModelStore with a small base model and return (store, mv)."""
    store = ModelStore()
    Z = np.array([[10.0, 5.0], [3.0, 8.0]])
    x = np.array([30.0, 20.0])
    mv = store.register(
        Z=Z, x=x, sector_codes=["S1", "S2"], base_year=2021, source="test"
    )
    return store, mv


@pytest.fixture()
def service_and_mv(store_and_mv: tuple) -> tuple:
    """Create a NowcastingService and return (service, store, mv)."""
    store, mv = store_and_mv
    svc = NowcastingService(model_store=store)
    return svc, store, mv


@pytest.fixture()
def draft_result(service_and_mv: tuple) -> tuple:
    """Create a DRAFT nowcast and return (result, service, store, mv)."""
    svc, store, mv = service_and_mv
    provenance = [
        TargetTotalProvenance(
            sector_code="S1",
            target_value=35.0,
            source="GASTAT 2023",
            evidence_refs=["ev-001"],
        ),
        TargetTotalProvenance(
            sector_code="S2",
            target_value=22.0,
            source="GASTAT 2023",
            evidence_refs=["ev-002"],
        ),
    ]
    result = svc.create_nowcast(
        base_model_version_id=mv.model_version_id,
        target_row_totals=np.array([35.0, 22.0]),
        target_col_totals=np.array([35.0, 22.0]),
        target_year=2023,
        provenance=provenance,
    )
    return result, svc, store, mv


# ===================================================================
# TargetTotalProvenance model tests
# ===================================================================


class TestTargetTotalProvenance:
    """TargetTotalProvenance stores sector-level provenance metadata."""

    def test_creation(self) -> None:
        p = TargetTotalProvenance(
            sector_code="S1",
            target_value=100.0,
            source="GASTAT 2023",
            evidence_refs=["ev-001", "ev-002"],
        )
        assert p.sector_code == "S1"
        assert p.target_value == 100.0
        assert p.source == "GASTAT 2023"
        assert p.evidence_refs == ["ev-001", "ev-002"]

    def test_default_evidence_refs(self) -> None:
        p = TargetTotalProvenance(
            sector_code="S2",
            target_value=50.0,
            source="Expert estimate",
        )
        assert p.evidence_refs == []


# ===================================================================
# NowcastResult model tests
# ===================================================================


class TestNowcastResult:
    """NowcastResult captures the full nowcast result metadata."""

    def test_creation_with_defaults(self) -> None:
        from uuid import uuid4

        r = NowcastResult(
            candidate_model_version_id=uuid4(),
            candidate_status=NowcastStatus.DRAFT,
            base_model_version_id=uuid4(),
            target_year=2023,
            converged=True,
            iterations=15,
            final_error=1e-10,
            structural_change_magnitude=0.12,
        )
        assert isinstance(r.nowcast_id, UUID)
        assert r.candidate_status == NowcastStatus.DRAFT
        assert r.target_year == 2023
        assert r.converged is True
        assert r.iterations == 15
        assert r.target_provenance == []
        assert r.quality_warnings == []


# ===================================================================
# create_nowcast tests
# ===================================================================


class TestCreateNowcast:
    """create_nowcast produces a DRAFT NowcastResult."""

    def test_produces_draft_status(self, draft_result: tuple) -> None:
        result, *_ = draft_result
        assert result.candidate_status == NowcastStatus.DRAFT

    def test_converges_for_reasonable_inputs(self, draft_result: tuple) -> None:
        result, *_ = draft_result
        assert result.converged is True

    def test_stores_structural_change_magnitude(
        self, draft_result: tuple
    ) -> None:
        result, *_ = draft_result
        assert result.structural_change_magnitude >= 0.0
        assert isinstance(result.structural_change_magnitude, float)

    def test_does_not_register_with_model_store(
        self, draft_result: tuple
    ) -> None:
        result, _svc, store, _mv = draft_result
        # The candidate_model_version_id should NOT be in the store yet
        with pytest.raises(KeyError):
            store.get(result.candidate_model_version_id)

    def test_provenance_stored_in_result(self, draft_result: tuple) -> None:
        result, *_ = draft_result
        assert len(result.target_provenance) == 2
        assert result.target_provenance[0].sector_code == "S1"
        assert result.target_provenance[0].target_value == 35.0
        assert result.target_provenance[0].source == "GASTAT 2023"
        assert result.target_provenance[1].sector_code == "S2"

    def test_nowcast_id_is_uuid(self, draft_result: tuple) -> None:
        result, *_ = draft_result
        assert isinstance(result.nowcast_id, UUID)

    def test_base_model_version_id_matches(self, draft_result: tuple) -> None:
        result, _svc, _store, mv = draft_result
        assert result.base_model_version_id == mv.model_version_id

    def test_target_year_stored(self, draft_result: tuple) -> None:
        result, *_ = draft_result
        assert result.target_year == 2023


# ===================================================================
# Warning generation tests
# ===================================================================


class TestNowcastWarnings:
    """Warnings generated for convergence failure and high structural change."""

    def test_warning_when_convergence_fails(
        self, service_and_mv: tuple
    ) -> None:
        svc, store, mv = service_and_mv
        # Use mismatched totals that won't converge in 1 iteration
        # with extremely low max_iterations via a modified balancer
        # Instead, set up a scenario that fundamentally cannot converge:
        # row totals and col totals don't sum to same value
        # Actually, RAS will still iterate; let's force non-convergence
        # by providing very aggressive targets that differ from Z0 structure
        # Use the service but with an extreme tolerance
        # We can't change tolerance via service, so let's use a Z0 with zeros
        # that prevents convergence.
        # The simplest approach: register a model where Z has all zeros
        # except diagonal, then ask for off-diagonal totals
        Z = np.array([[10.0, 0.0], [0.0, 8.0]])
        x = np.array([30.0, 20.0])
        mv2 = store.register(
            Z=Z, x=x, sector_codes=["S1", "S2"], base_year=2021, source="test2"
        )
        # Row totals include off-diagonal that Z can't produce
        # RAS preserves structural zeros, so it can never match
        # row_totals=[15, 15] when Z has zeros off-diagonal
        result = svc.create_nowcast(
            base_model_version_id=mv2.model_version_id,
            target_row_totals=np.array([15.0, 15.0]),
            target_col_totals=np.array([15.0, 15.0]),
            target_year=2023,
            provenance=[],
        )
        # RAS preserves zeros so it converges (diagonal only), but
        # the error might be zero because row/col sums of diagonal
        # matrix match if targets equal diagonal values.
        # Let's actually check: Z = diag(10,8), row_totals=[15,15]
        # After row scaling: diag(15,15), col_totals=[15,15] -> matches.
        # That converges. Let's use asymmetric totals instead.
        # Actually for a diagonal matrix with row_totals=[15,15] and
        # col_totals=[15,15], row scaling gives diag(15,15) and
        # col scaling keeps it. So it converges.
        # We need truly incompatible targets with structural zeros.
        # Z = [[10, 0], [0, 8]], target_row = [10, 10], target_col = [8, 12]
        # Row scale: diag(10, 10), col scale: col sums = [10, 10],
        # want [8, 12] -> scale [0.8, 1.2] -> diag(8, 12),
        # row sums = [8, 12], want [10, 10] -> won't converge easily.
        # With structural zeros, RAS can only scale diag entries, so
        # it's trying to satisfy row_i = col_i for each i, which
        # is impossible when row[0]=10,col[0]=8 differ.
        result2 = svc.create_nowcast(
            base_model_version_id=mv2.model_version_id,
            target_row_totals=np.array([10.0, 10.0]),
            target_col_totals=np.array([8.0, 12.0]),
            target_year=2023,
            provenance=[],
        )
        assert result2.converged is False
        # Should have a CRITICAL warning about convergence
        critical_warnings = [
            w
            for w in result2.quality_warnings
            if w.severity == QualitySeverity.CRITICAL
        ]
        assert len(critical_warnings) >= 1
        assert any("converg" in w.message.lower() for w in critical_warnings)

    def test_warning_for_high_structural_change(
        self, service_and_mv: tuple
    ) -> None:
        svc, store, mv = service_and_mv
        # Use very different target totals to produce high structural change
        result = svc.create_nowcast(
            base_model_version_id=mv.model_version_id,
            target_row_totals=np.array([100.0, 100.0]),
            target_col_totals=np.array([100.0, 100.0]),
            target_year=2023,
            provenance=[],
        )
        # structural_change_magnitude should be > 0.5
        assert result.structural_change_magnitude > 0.5
        warn_warnings = [
            w
            for w in result.quality_warnings
            if w.severity == QualitySeverity.WARNING
        ]
        assert len(warn_warnings) >= 1
        assert any("structural" in w.message.lower() for w in warn_warnings)


# ===================================================================
# approve_nowcast tests
# ===================================================================


class TestApproveNowcast:
    """approve_nowcast registers with ModelStore and updates status."""

    def test_registers_with_model_store(self, draft_result: tuple) -> None:
        result, svc, store, _mv = draft_result
        new_mv = svc.approve_nowcast(result.nowcast_id)
        # The model should now be retrievable from the store
        loaded = store.get(new_mv.model_version_id)
        assert loaded is not None
        assert loaded.model_version.source == "balanced-nowcast"

    def test_returns_valid_model_version(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        new_mv = svc.approve_nowcast(result.nowcast_id)
        assert isinstance(new_mv, ModelVersion)
        assert new_mv.sector_count == 2
        assert new_mv.base_year == 2023

    def test_changes_status_to_approved(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.approve_nowcast(result.nowcast_id)
        assert svc.get_status(result.nowcast_id) == NowcastStatus.APPROVED

    def test_updates_candidate_model_version_id(
        self, draft_result: tuple
    ) -> None:
        result, svc, store, _mv = draft_result
        new_mv = svc.approve_nowcast(result.nowcast_id)
        # The approved result should have the registered model version id
        approved = svc._candidates[result.nowcast_id]
        assert approved.candidate_model_version_id == new_mv.model_version_id


# ===================================================================
# reject_nowcast tests
# ===================================================================


class TestRejectNowcast:
    """reject_nowcast changes status to REJECTED."""

    def test_changes_status_to_rejected(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.reject_nowcast(result.nowcast_id)
        assert svc.get_status(result.nowcast_id) == NowcastStatus.REJECTED

    def test_reject_unknown_raises_value_error(
        self, service_and_mv: tuple
    ) -> None:
        svc, _store, _mv = service_and_mv
        from uuid import uuid4

        with pytest.raises(ValueError):
            svc.reject_nowcast(uuid4())


# ===================================================================
# Double-transition error tests
# ===================================================================


class TestDoubleTransition:
    """Invalid state transitions raise ValueError."""

    def test_double_approve_raises(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.approve_nowcast(result.nowcast_id)
        with pytest.raises(ValueError, match="already approved/rejected"):
            svc.approve_nowcast(result.nowcast_id)

    def test_approve_after_reject_raises(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.reject_nowcast(result.nowcast_id)
        with pytest.raises(ValueError, match="already approved/rejected"):
            svc.approve_nowcast(result.nowcast_id)

    def test_reject_after_approve_raises(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.approve_nowcast(result.nowcast_id)
        with pytest.raises(ValueError, match="already approved/rejected"):
            svc.reject_nowcast(result.nowcast_id)


# ===================================================================
# get_status tests
# ===================================================================


class TestGetStatus:
    """get_status returns correct status for all states."""

    def test_draft_status(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        assert svc.get_status(result.nowcast_id) == NowcastStatus.DRAFT

    def test_approved_status(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.approve_nowcast(result.nowcast_id)
        assert svc.get_status(result.nowcast_id) == NowcastStatus.APPROVED

    def test_rejected_status(self, draft_result: tuple) -> None:
        result, svc, _store, _mv = draft_result
        svc.reject_nowcast(result.nowcast_id)
        assert svc.get_status(result.nowcast_id) == NowcastStatus.REJECTED

    def test_unknown_id_raises_key_error(self, service_and_mv: tuple) -> None:
        svc, _store, _mv = service_and_mv
        from uuid import uuid4

        with pytest.raises(KeyError):
            svc.get_status(uuid4())


# ===================================================================
# Import test (needed for approve return type assertion)
# ===================================================================

from src.models.model_version import ModelVersion  # noqa: E402
