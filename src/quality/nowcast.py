"""Governed Nowcasting Service (Task 8, Amendment 8).

Wraps the RAS balancer with a draft/approve/reject lifecycle so that
nowcast candidates are reviewed before being published as ModelVersions.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from uuid import UUID

import numpy as np
from pydantic import Field

from src.engine.model_store import ModelStore
from src.engine.ras import RASBalancer
from src.models.common import ImpactOSBase, UUIDv7, new_uuid7
from src.models.model_version import ModelVersion
from src.quality.models import (
    NowcastStatus,
    QualityDimension,
    QualitySeverity,
    QualityWarning,
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TargetTotalProvenance(ImpactOSBase):
    """Rich provenance for each target total in a nowcast (Amendment 8)."""

    sector_code: str
    target_value: float
    source: str
    evidence_refs: list[str] = Field(default_factory=list)


class NowcastResult(ImpactOSBase):
    """Result of creating a nowcast candidate."""

    nowcast_id: UUIDv7 = Field(default_factory=new_uuid7)
    candidate_model_version_id: UUID
    candidate_status: NowcastStatus
    base_model_version_id: UUID
    target_year: int
    converged: bool
    iterations: int
    final_error: float
    structural_change_magnitude: float
    target_provenance: list[TargetTotalProvenance] = Field(default_factory=list)
    quality_warnings: list[QualityWarning] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NowcastingService:
    """Governed nowcasting with draft/approve/reject lifecycle.

    Wraps the deterministic RAS balancer, holding balanced candidates
    in an internal buffer until explicitly approved (registered with
    ModelStore) or rejected.
    """

    def __init__(self, model_store: ModelStore) -> None:
        self._store = model_store
        self._balancer = RASBalancer()
        self._candidates: dict[UUID, NowcastResult] = {}
        self._candidate_data: dict[
            UUID, tuple[np.ndarray, np.ndarray, list[str], int]
        ] = {}

    # ---- create ----

    def create_nowcast(
        self,
        base_model_version_id: UUID,
        target_row_totals: np.ndarray,
        target_col_totals: np.ndarray,
        target_year: int,
        provenance: list[TargetTotalProvenance],
    ) -> NowcastResult:
        """Create a DRAFT nowcast candidate without publishing.

        Loads the base model, runs RAS balancing, computes structural
        change magnitude and quality warnings, and stores the candidate
        data internally.  The candidate is NOT registered with the
        ModelStore until :meth:`approve_nowcast` is called.

        Args:
            base_model_version_id: ID of the base ModelVersion to update.
            target_row_totals: New row totals (gross output by sector).
            target_col_totals: New column totals (intermediate demand).
            target_year: The year the nowcast targets.
            provenance: Per-sector provenance for each target total.

        Returns:
            NowcastResult with status DRAFT.
        """
        # Load base model
        loaded = self._store.get(base_model_version_id)

        # Run RAS balancing
        ras_result = self._balancer.balance(
            Z0=loaded.Z,
            target_row_totals=np.asarray(target_row_totals, dtype=np.float64),
            target_col_totals=np.asarray(target_col_totals, dtype=np.float64),
        )

        # Compute structural change magnitude
        z_orig_sum = float(np.sum(np.abs(loaded.Z)))
        structural_change_magnitude = float(
            np.sum(np.abs(ras_result.Z_balanced - loaded.Z))
            / (z_orig_sum + 1e-10)
        )

        # x_new = target_row_totals (row totals = gross output)
        x_new = np.asarray(target_row_totals, dtype=np.float64)

        # Generate quality warnings
        warnings: list[QualityWarning] = []

        if not ras_result.converged:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.FRESHNESS,
                    severity=QualitySeverity.CRITICAL,
                    message="RAS balancing did not converge.",
                    detail=(
                        f"Final error {ras_result.final_error:.6e} after "
                        f"{ras_result.iterations} iterations."
                    ),
                    recommendation="Review target totals for consistency.",
                )
            )

        if structural_change_magnitude > 0.5:
            warnings.append(
                QualityWarning(
                    dimension=QualityDimension.FRESHNESS,
                    severity=QualitySeverity.WARNING,
                    message=(
                        f"High structural change magnitude: "
                        f"{structural_change_magnitude:.4f}."
                    ),
                    detail=(
                        "The balanced matrix differs substantially from "
                        "the base model. Manual review is recommended."
                    ),
                    recommendation=(
                        "Compare sector-level changes and validate "
                        "against external benchmarks."
                    ),
                )
            )

        # Build a placeholder candidate_model_version_id (not yet registered)
        candidate_mvid = new_uuid7()

        result = NowcastResult(
            candidate_model_version_id=candidate_mvid,
            candidate_status=NowcastStatus.DRAFT,
            base_model_version_id=base_model_version_id,
            target_year=target_year,
            converged=ras_result.converged,
            iterations=ras_result.iterations,
            final_error=ras_result.final_error,
            structural_change_magnitude=structural_change_magnitude,
            target_provenance=provenance,
            quality_warnings=warnings,
        )

        # Store internally -- NOT in ModelStore
        self._candidates[result.nowcast_id] = result
        self._candidate_data[result.nowcast_id] = (
            ras_result.Z_balanced,
            x_new,
            loaded.sector_codes,
            target_year,
        )

        return result

    # ---- approve ----

    def approve_nowcast(self, nowcast_id: UUID) -> ModelVersion:
        """Approve a DRAFT nowcast and register it as a ModelVersion.

        Args:
            nowcast_id: ID of the nowcast candidate to approve.

        Returns:
            The newly registered ModelVersion.

        Raises:
            ValueError: If not found or not in DRAFT status.
        """
        if nowcast_id not in self._candidates:
            msg = f"Nowcast {nowcast_id} not found."
            raise ValueError(msg)

        current = self._candidates[nowcast_id]
        if current.candidate_status != NowcastStatus.DRAFT:
            msg = "already approved/rejected"
            raise ValueError(msg)

        Z_balanced, x_new, sector_codes, target_year = self._candidate_data[
            nowcast_id
        ]

        # Register with ModelStore
        mv = self._store.register(
            Z=Z_balanced,
            x=x_new,
            sector_codes=sector_codes,
            base_year=target_year,
            source="balanced-nowcast",
        )

        # Update status (create new NowcastResult since Pydantic is immutable-ish)
        self._candidates[nowcast_id] = NowcastResult(
            nowcast_id=current.nowcast_id,
            candidate_model_version_id=mv.model_version_id,
            candidate_status=NowcastStatus.APPROVED,
            base_model_version_id=current.base_model_version_id,
            target_year=current.target_year,
            converged=current.converged,
            iterations=current.iterations,
            final_error=current.final_error,
            structural_change_magnitude=current.structural_change_magnitude,
            target_provenance=current.target_provenance,
            quality_warnings=current.quality_warnings,
        )

        return mv

    # ---- reject ----

    def reject_nowcast(self, nowcast_id: UUID) -> None:
        """Reject a DRAFT nowcast candidate.

        Args:
            nowcast_id: ID of the nowcast candidate to reject.

        Raises:
            ValueError: If not found or not in DRAFT status.
        """
        if nowcast_id not in self._candidates:
            msg = f"Nowcast {nowcast_id} not found."
            raise ValueError(msg)

        current = self._candidates[nowcast_id]
        if current.candidate_status != NowcastStatus.DRAFT:
            msg = "already approved/rejected"
            raise ValueError(msg)

        self._candidates[nowcast_id] = NowcastResult(
            nowcast_id=current.nowcast_id,
            candidate_model_version_id=current.candidate_model_version_id,
            candidate_status=NowcastStatus.REJECTED,
            base_model_version_id=current.base_model_version_id,
            target_year=current.target_year,
            converged=current.converged,
            iterations=current.iterations,
            final_error=current.final_error,
            structural_change_magnitude=current.structural_change_magnitude,
            target_provenance=current.target_provenance,
            quality_warnings=current.quality_warnings,
        )

    # ---- status ----

    def get_status(self, nowcast_id: UUID) -> NowcastStatus:
        """Return the current lifecycle status of a nowcast candidate.

        Args:
            nowcast_id: ID of the nowcast candidate.

        Returns:
            Current NowcastStatus.

        Raises:
            KeyError: If nowcast_id is not found.
        """
        if nowcast_id not in self._candidates:
            msg = f"Nowcast {nowcast_id} not found."
            raise KeyError(msg)
        return self._candidates[nowcast_id].candidate_status
