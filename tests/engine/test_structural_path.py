"""Tests for Structural Path Analysis decomposition engine.

Covers: power series expansion A^0 + A^1 + ... + A^k, path contributions,
chokepoint scoring (Rasmussen), depth contributions, coverage ratio.
Deterministic — no LLM calls.
"""

import numpy as np
import pytest

from src.engine.structural_path import (
    ChokePointScore,
    DepthContrib,
    PathContribution,
    SPAConfigError,
    SPADimensionError,
    SPAResult,
    compute_spa,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def model_2x2() -> dict:
    """2x2 toy model: A, B = (I-A)^{-1}, delta_d, sector_codes."""
    A = np.array([[0.2, 0.3], [0.1, 0.4]])
    I = np.eye(2)
    B = np.linalg.inv(I - A)
    delta_d = np.array([100.0, 0.0])
    sector_codes = ["S1", "S2"]
    return {"A": A, "B": B, "delta_d": delta_d, "sector_codes": sector_codes}


@pytest.fixture()
def model_2x2_fast_converge() -> dict:
    """2x2 model with low spectral radius (~0.07) for identity convergence tests.

    At max_depth=10, the power series residual is < 1e-12, enabling
    1e-10 identity checks.
    """
    A = np.array([[0.05, 0.03], [0.02, 0.04]])
    I = np.eye(2)
    B = np.linalg.inv(I - A)
    delta_d = np.array([100.0, 0.0])
    sector_codes = ["S1", "S2"]
    return {"A": A, "B": B, "delta_d": delta_d, "sector_codes": sector_codes}


@pytest.fixture()
def model_3x3() -> dict:
    """3x3 model designed so at least one sector has both normalised linkages > 1.

    A is chosen so that the Leontief inverse B has strong cross-sector linkages.
    Sector 1 (index 1) is designed to be a chokepoint.
    """
    A = np.array(
        [
            [0.10, 0.25, 0.05],
            [0.20, 0.15, 0.30],
            [0.05, 0.20, 0.10],
        ]
    )
    I = np.eye(3)
    B = np.linalg.inv(I - A)
    delta_d = np.array([100.0, 50.0, 0.0])
    sector_codes = ["Agr", "Mfg", "Svc"]
    return {"A": A, "B": B, "delta_d": delta_d, "sector_codes": sector_codes}


# ===================================================================
# Depth and coverage tests
# ===================================================================


class TestDepthAndCoverage:
    """Power series truncation at different depths."""

    def test_2x2_depth_0_direct_only(self, model_2x2: dict) -> None:
        """max_depth=0 gives identity (A^0 = I) contributions only."""
        m = model_2x2
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=0,
            top_k=20,
        )
        assert result.max_depth == 0
        # A^0 = I, so only diagonal entries (i==j) contribute.
        # With delta_d = [100, 0], only (0,0) at depth 0 has nonzero contribution.
        for p in result.top_paths:
            assert p.depth == 0
            assert p.source_sector == p.target_sector  # identity only

        # The single nonzero path: (i=0, j=0, k=0) contribution = I[0,0]*100 = 100
        nonzero = [p for p in result.top_paths if p.contribution != 0.0]
        assert len(nonzero) == 1
        assert nonzero[0].contribution == pytest.approx(100.0)

    def test_2x2_depth_1_first_round(self, model_2x2: dict) -> None:
        """max_depth=1 captures direct (A^0) + first indirect (A^1)."""
        m = model_2x2
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=1,
            top_k=20,
        )
        assert result.max_depth == 1
        depths_present = {p.depth for p in result.top_paths}
        assert depths_present <= {0, 1}
        # Depth 1 contributions: A^1 * delta_d column broadcast.
        # A[0,0]=0.2, A[1,0]=0.1 with delta_d[0]=100 -> contributions 20.0, 10.0
        depth1 = [p for p in result.top_paths if p.depth == 1]
        contribs = sorted([p.contribution for p in depth1], reverse=True)
        assert contribs[0] == pytest.approx(20.0)
        assert contribs[1] == pytest.approx(10.0)

    def test_2x2_full_depth_coverage_high(self, model_2x2: dict) -> None:
        """max_depth=10 gives coverage_ratio > 0.99."""
        m = model_2x2
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=10,
            top_k=20,
        )
        assert result.coverage_ratio > 0.99


# ===================================================================
# Identity invariants
# ===================================================================


class TestIdentityInvariants:
    """Critical identities: SPA must reconstruct B @ delta_d.

    Uses a fast-converging model (spectral radius ~0.07) so that
    max_depth=10 gives power series residual < 1e-12, enabling 1e-10
    identity checks.
    """

    def test_scalar_identity(self, model_2x2_fast_converge: dict) -> None:
        """sum(depth_contributions[k].signed) ~= sum(B @ delta_d)."""
        m = model_2x2_fast_converge
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=10,
            top_k=100,
        )
        total_from_depth = sum(dc.signed for dc in result.depth_contributions.values())
        expected_total = float(np.sum(m["B"] @ m["delta_d"]))
        assert total_from_depth == pytest.approx(expected_total, abs=1e-10)

    def test_vector_identity(self, model_2x2_fast_converge: dict) -> None:
        """Per-sector reconstruction from top_paths matches (B @ delta_d)[i].

        Uses top_k large enough to include ALL (i,j,k) tuples.
        """
        m = model_2x2_fast_converge
        n = m["A"].shape[0]
        max_depth = 10
        # top_k large enough for all paths: n*n*(max_depth+1) = 2*2*11 = 44
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=max_depth,
            top_k=100,
        )
        expected = m["B"] @ m["delta_d"]
        for i in range(n):
            sector_sum = sum(p.contribution for p in result.top_paths if p.target_sector == i)
            assert sector_sum == pytest.approx(expected[i], abs=1e-10)


# ===================================================================
# top_k and ranking
# ===================================================================


class TestTopKRanking:
    """Ordering and limiting of top_paths."""

    def test_top_k_ranking_deterministic(self, model_2x2: dict) -> None:
        """Tie-break: |contribution| DESC, k ASC, i ASC, j ASC."""
        m = model_2x2
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=6,
            top_k=100,
        )
        paths = result.top_paths
        for a, b in zip(paths, paths[1:]):
            abs_a, abs_b = abs(a.contribution), abs(b.contribution)
            if abs_a == pytest.approx(abs_b, abs=1e-15):
                if a.depth == b.depth:
                    if a.target_sector == b.target_sector:
                        assert a.source_sector <= b.source_sector
                    else:
                        assert a.target_sector < b.target_sector
                else:
                    assert a.depth < b.depth
            else:
                assert abs_a >= abs_b

    def test_top_k_limits_output(self, model_2x2: dict) -> None:
        """len(top_paths) <= top_k."""
        m = model_2x2
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=6,
            top_k=3,
        )
        assert len(result.top_paths) <= 3


# ===================================================================
# Zero-shock edge case
# ===================================================================


class TestZeroShock:
    """All-zero demand shock."""

    def test_zero_shock(self, model_2x2: dict) -> None:
        """All contributions zero, top_paths empty."""
        m = model_2x2
        zero_d = np.zeros(2)
        result = compute_spa(
            m["A"],
            m["B"],
            zero_d,
            m["sector_codes"],
            max_depth=6,
            top_k=20,
        )
        assert result.top_paths == []
        for dc in result.depth_contributions.values():
            assert dc.signed == pytest.approx(0.0)
            assert dc.absolute == pytest.approx(0.0)


# ===================================================================
# Depth contributions
# ===================================================================


class TestDepthContributions:
    """Signed and absolute depth rollups."""

    def test_depth_contributions_signed_and_absolute(self, model_2x2: dict) -> None:
        """Both fields are present and numerically correct."""
        m = model_2x2
        A = m["A"]
        delta_d = m["delta_d"]
        result = compute_spa(
            A,
            m["B"],
            delta_d,
            m["sector_codes"],
            max_depth=3,
            top_k=100,
        )
        # Manually compute depth-0: C_0 = I * delta_d broadcast = diag(delta_d)
        # signed_0 = sum(diag(delta_d)) = 100 + 0 = 100
        assert result.depth_contributions[0].signed == pytest.approx(100.0)
        assert result.depth_contributions[0].absolute == pytest.approx(100.0)

        # Depth 1: C_1 = A * delta_d broadcast
        C1 = A * delta_d[np.newaxis, :]
        assert result.depth_contributions[1].signed == pytest.approx(float(np.sum(C1)))
        assert result.depth_contributions[1].absolute == pytest.approx(float(np.sum(np.abs(C1))))


# ===================================================================
# Chokepoint analysis (3x3 model)
# ===================================================================


class TestChokepoints:
    """Rasmussen-convention chokepoint scoring."""

    def test_chokepoint_forward_backward_linkage(self, model_3x3: dict) -> None:
        """Hand-verified forward and backward linkages on 3x3 model."""
        m = model_3x3
        B = m["B"]
        result = compute_spa(
            m["A"],
            B,
            m["delta_d"],
            m["sector_codes"],
            max_depth=6,
            top_k=20,
        )
        # Rasmussen convention:
        # backward_linkage[j] = sum_i(B[i,j])  (column sum)
        # forward_linkage[i] = sum_j(B[i,j])   (row sum)
        n = B.shape[0]
        bl = np.sum(B, axis=0)  # column sums
        fl = np.sum(B, axis=1)  # row sums

        # Build lookup by sector_index
        cp_map = {cp.sector_index: cp for cp in result.chokepoints}
        for s in range(n):
            assert cp_map[s].backward_linkage == pytest.approx(bl[s], rel=1e-10)
            assert cp_map[s].forward_linkage == pytest.approx(fl[s], rel=1e-10)

    def test_chokepoint_score_formula(self, model_3x3: dict) -> None:
        """chokepoint_score = sqrt(norm_forward * norm_backward)."""
        m = model_3x3
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=6,
            top_k=20,
        )
        for cp in result.chokepoints:
            expected = np.sqrt(cp.norm_forward * cp.norm_backward)
            assert cp.chokepoint_score == pytest.approx(expected, rel=1e-10)

    def test_chokepoint_flag_both_above_one(self, model_3x3: dict) -> None:
        """is_chokepoint True only when BOTH normalised linkages > 1.0."""
        m = model_3x3
        result = compute_spa(
            m["A"],
            m["B"],
            m["delta_d"],
            m["sector_codes"],
            max_depth=6,
            top_k=20,
        )
        for cp in result.chokepoints:
            if cp.is_chokepoint:
                assert cp.norm_forward > 1.0
                assert cp.norm_backward > 1.0
            else:
                assert cp.norm_forward <= 1.0 or cp.norm_backward <= 1.0

        # Verify at least one sector IS a chokepoint in this model
        assert any(cp.is_chokepoint for cp in result.chokepoints)


# ===================================================================
# Degenerate case: single sector
# ===================================================================


class TestDegenerate:
    """Edge cases with degenerate models."""

    def test_single_sector_degenerate(self) -> None:
        """n=1, A=[[0.1]], B=[[1/(1-0.1)]] = [[1.1111...]].

        Uses a=0.1 so spectral radius is small enough for max_depth=12
        to converge within 1e-10 (0.1^13 ~ 1e-13).
        """
        a = 0.1
        A = np.array([[a]])
        B = np.array([[1.0 / (1.0 - a)]])
        delta_d = np.array([10.0])
        sector_codes = ["Only"]

        result = compute_spa(A, B, delta_d, sector_codes, max_depth=12, top_k=20)

        # Should produce valid result
        assert isinstance(result, SPAResult)
        # coverage should be very high
        assert result.coverage_ratio > 0.9999

        # Scalar identity check
        total_from_depth = sum(dc.signed for dc in result.depth_contributions.values())
        expected = float(np.sum(B @ delta_d))  # ~11.111...
        assert total_from_depth == pytest.approx(expected, abs=1e-10)

        # Chokepoint: only 1 sector, normalised linkages are both 1.0 exactly
        assert len(result.chokepoints) == 1
        cp = result.chokepoints[0]
        assert cp.norm_forward == pytest.approx(1.0)
        assert cp.norm_backward == pytest.approx(1.0)
        # Both == 1.0, not > 1.0 => not a chokepoint
        assert cp.is_chokepoint is False


# ===================================================================
# Error handling
# ===================================================================


class TestValidation:
    """Input validation — dimension mismatches and config bounds."""

    def test_dimension_mismatch_raises(self, model_2x2: dict) -> None:
        """Wrong shapes raise SPADimensionError."""
        m = model_2x2
        # A wrong shape
        with pytest.raises(SPADimensionError):
            compute_spa(
                np.eye(3),
                m["B"],
                m["delta_d"],
                m["sector_codes"],
                max_depth=6,
                top_k=20,
            )
        # B wrong shape
        with pytest.raises(SPADimensionError):
            compute_spa(
                m["A"],
                np.eye(3),
                m["delta_d"],
                m["sector_codes"],
                max_depth=6,
                top_k=20,
            )
        # delta_d wrong shape
        with pytest.raises(SPADimensionError):
            compute_spa(
                m["A"],
                m["B"],
                np.array([1.0, 2.0, 3.0]),
                m["sector_codes"],
                max_depth=6,
                top_k=20,
            )
        # sector_codes wrong length
        with pytest.raises(SPADimensionError):
            compute_spa(
                m["A"],
                m["B"],
                m["delta_d"],
                ["S1", "S2", "S3"],
                max_depth=6,
                top_k=20,
            )

    def test_config_out_of_bounds_raises(self, model_2x2: dict) -> None:
        """max_depth=13 or top_k=0 raises SPAConfigError."""
        m = model_2x2
        with pytest.raises(SPAConfigError):
            compute_spa(
                m["A"],
                m["B"],
                m["delta_d"],
                m["sector_codes"],
                max_depth=13,
                top_k=20,
            )
        with pytest.raises(SPAConfigError):
            compute_spa(
                m["A"],
                m["B"],
                m["delta_d"],
                m["sector_codes"],
                max_depth=6,
                top_k=0,
            )
        with pytest.raises(SPAConfigError):
            compute_spa(
                m["A"],
                m["B"],
                m["delta_d"],
                m["sector_codes"],
                max_depth=-1,
                top_k=20,
            )
        with pytest.raises(SPAConfigError):
            compute_spa(
                m["A"],
                m["B"],
                m["delta_d"],
                m["sector_codes"],
                max_depth=6,
                top_k=101,
            )
