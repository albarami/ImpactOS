"""ModelVersion management — MVP-3 Sections 7.1, 7.2, 7.6.

Load/store ModelVersion with Z matrix and x vector, compute and cache
technical coefficients A and Leontief inverse B=(I-A)^-1, validate
productivity conditions.

This is deterministic — no LLM calls, pure functions.
"""

import hashlib
from uuid import UUID

import numpy as np
from scipy import linalg as scipy_linalg

from src.models.model_version import ModelVersion


class LoadedModel:
    """In-memory representation of a registered I-O model.

    Holds raw data (Z, x) and lazily computes / caches A and B.
    """

    def __init__(
        self,
        *,
        model_version: ModelVersion,
        Z: np.ndarray,
        x: np.ndarray,
        sector_codes: list[str],
    ) -> None:
        self._model_version = model_version
        self._Z = Z.copy()
        self._Z.flags.writeable = False
        self._x = x.copy()
        self._x.flags.writeable = False
        self._sector_codes = list(sector_codes)
        self._A: np.ndarray | None = None
        self._B: np.ndarray | None = None

    @property
    def model_version(self) -> ModelVersion:
        return self._model_version

    @property
    def Z(self) -> np.ndarray:
        return self._Z

    @property
    def x(self) -> np.ndarray:
        return self._x

    @property
    def sector_codes(self) -> list[str]:
        return list(self._sector_codes)

    @property
    def n(self) -> int:
        return len(self._x)

    @property
    def A(self) -> np.ndarray:
        """Technical coefficients: A = Z · diag(x)^{-1}."""
        if self._A is None:
            self._A = self._Z / self._x[np.newaxis, :]
            self._A.flags.writeable = False
        return self._A

    @property
    def B(self) -> np.ndarray:
        """Leontief inverse: B = (I - A)^{-1}.

        Uses scipy LU-based solver for numerical stability (Section 7.6).
        Cached per model — same object on repeated access.
        """
        if self._B is None:
            I_minus_A = np.eye(self.n) - self.A
            # Solve (I-A) · B = I  ⟹  B = (I-A)^{-1}
            # Using scipy solve for stability over explicit inversion
            B = scipy_linalg.solve(I_minus_A, np.eye(self.n))
            B = np.asarray(B)
            B.flags.writeable = False
            self._B = B
        return self._B


class ModelStore:
    """In-memory store for I-O model versions.

    Production would use PostgreSQL + object storage; this in-memory
    implementation is for MVP and testing.
    """

    def __init__(self) -> None:
        self._models: dict[UUID, LoadedModel] = {}

    def register(
        self,
        *,
        Z: np.ndarray,
        x: np.ndarray,
        sector_codes: list[str],
        base_year: int,
        source: str,
    ) -> ModelVersion:
        """Validate, store, and return an immutable ModelVersion.

        Validates:
        - Dimension consistency (Z is n×n, x is n, sector_codes has n entries)
        - Non-negativity of Z
        - No zero-output sectors in x
        - Spectral radius of A < 1 (productivity condition)

        Returns:
            Immutable ModelVersion with computed checksum.

        Raises:
            ValueError: If any validation fails.
        """
        Z = np.asarray(Z, dtype=np.float64)
        x = np.asarray(x, dtype=np.float64)
        n = len(x)

        # --- Validation ---
        if Z.ndim != 2 or Z.shape[0] != Z.shape[1]:
            msg = "Z must be a square matrix."
            raise ValueError(msg)

        if Z.shape[0] != n:
            msg = f"dimension mismatch: Z is {Z.shape[0]}×{Z.shape[1]} but x has {n} elements."
            raise ValueError(msg)

        if len(sector_codes) != n:
            msg = f"sector_codes length ({len(sector_codes)}) must match dimension ({n})."
            raise ValueError(msg)

        if np.any(Z < 0):
            msg = "Z must be non-negative (all entries >= 0)."
            raise ValueError(msg)

        if np.any(x <= 0):
            msg = "x must have no zero or negative output sectors."
            raise ValueError(msg)

        # Compute A and check spectral radius
        A = Z / x[np.newaxis, :]
        eigenvalues = np.linalg.eigvals(A)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        if spectral_radius >= 1.0:
            msg = (
                f"spectral radius of A is {spectral_radius:.4f} (must be < 1). "
                "The economy is not productive."
            )
            raise ValueError(msg)

        # Compute checksum over Z and x
        hasher = hashlib.sha256()
        hasher.update(Z.tobytes())
        hasher.update(x.tobytes())
        checksum = f"sha256:{hasher.hexdigest()}"

        mv = ModelVersion(
            base_year=base_year,
            source=source,
            sector_count=n,
            checksum=checksum,
        )

        loaded = LoadedModel(
            model_version=mv,
            Z=Z,
            x=x,
            sector_codes=sector_codes,
        )
        self._models[mv.model_version_id] = loaded

        return mv

    def get(self, model_version_id: UUID) -> LoadedModel:
        """Retrieve a loaded model by version ID.

        Raises:
            KeyError: If version not found.
        """
        if model_version_id not in self._models:
            msg = f"ModelVersion {model_version_id} not found."
            raise KeyError(msg)
        return self._models[model_version_id]

    def store_loaded_model(self, loaded: LoadedModel) -> None:
        """Store an externally-created LoadedModel (e.g. from RAS balancing)."""
        self._models[loaded.model_version.model_version_id] = loaded
