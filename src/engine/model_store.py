"""ModelVersion management — MVP-3 Sections 7.1, 7.2, 7.6.

Load/store ModelVersion with Z matrix and x vector, compute and cache
technical coefficients A and Leontief inverse B=(I-A)^-1, validate
productivity conditions.

This is deterministic — no LLM calls, pure functions.
"""

import hashlib
import json
from uuid import UUID

import numpy as np
from scipy import linalg as scipy_linalg

from src.models.model_version import ModelVersion


def compute_model_checksum(
    Z: np.ndarray,
    x: np.ndarray,
    artifact_payload: dict[str, object] | None = None,
) -> str:
    """Compute deterministic checksum for base model matrices and optional artifacts.

    Legacy compatibility: if no non-null artifact fields are provided, checksum
    remains based on Z and x only.
    """
    hasher = hashlib.sha256()
    hasher.update(np.asarray(Z, dtype=np.float64).tobytes())
    hasher.update(np.asarray(x, dtype=np.float64).tobytes())

    if artifact_payload:
        normalized = {
            k: v for k, v in artifact_payload.items()
            if v is not None
        }
        if normalized:
            def _default(value: object) -> object:
                if isinstance(value, np.ndarray):
                    return value.tolist()
                if isinstance(value, np.integer | np.floating):
                    return value.item()
                return value

            canonical = json.dumps(
                normalized,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=_default,
            )
            hasher.update(canonical.encode("utf-8"))

    return f"sha256:{hasher.hexdigest()}"


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
    def has_type_ii_prerequisites(self) -> bool:
        """Whether this model has compensation and household share data for Type II."""
        mv = self._model_version
        return (
            mv.compensation_of_employees is not None
            and mv.household_consumption_shares is not None
        )

    @property
    def compensation_of_employees_array(self) -> np.ndarray | None:
        """Compensation of employees as numpy array, or None if not available."""
        data = self._model_version.compensation_of_employees
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    @property
    def household_consumption_shares_array(self) -> np.ndarray | None:
        """Household consumption shares as numpy array, or None if not available."""
        data = self._model_version.household_consumption_shares
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    @property
    def gross_operating_surplus_array(self) -> np.ndarray | None:
        """Gross operating surplus as numpy array, or None if not available."""
        data = self._model_version.gross_operating_surplus
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    @property
    def taxes_less_subsidies_array(self) -> np.ndarray | None:
        """Net taxes less subsidies as numpy array, or None if not available."""
        data = self._model_version.taxes_less_subsidies
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    @property
    def final_demand_f_array(self) -> np.ndarray | None:
        """Final demand matrix F as numpy array (n, k), or None if not available."""
        data = self._model_version.final_demand_f
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    @property
    def imports_vector_array(self) -> np.ndarray | None:
        """Imports vector as numpy array, or None if not available."""
        data = self._model_version.imports_vector
        if data is None:
            return None
        return np.asarray(data, dtype=np.float64)

    def deflator_for_year(self, year: int) -> float | None:
        """Return deflator for a specific year, or None if not available."""
        series = self._model_version.deflator_series
        if series is None:
            return None
        return series.get(year)

    @property
    def has_value_measures_prerequisites(self) -> bool:
        """Whether this model has minimum artifacts for value measures."""
        mv = self._model_version
        return (
            mv.gross_operating_surplus is not None
            and mv.taxes_less_subsidies is not None
            and mv.final_demand_f is not None
            and mv.imports_vector is not None
        )

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
        artifact_payload: dict[str, object] | None = None,
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

        checksum = compute_model_checksum(Z, x, artifact_payload)

        model_kwargs: dict[str, object] = {}
        if artifact_payload:
            key_map = {
                "final_demand_F": "final_demand_f",
                "imports_vector": "imports_vector",
                "compensation_of_employees": "compensation_of_employees",
                "gross_operating_surplus": "gross_operating_surplus",
                "taxes_less_subsidies": "taxes_less_subsidies",
                "household_consumption_shares": "household_consumption_shares",
                "deflator_series": "deflator_series",
            }
            for source_key, target_key in key_map.items():
                if artifact_payload.get(source_key) is not None:
                    model_kwargs[target_key] = artifact_payload[source_key]

        mv = ModelVersion(
            base_year=base_year,
            source=source,
            sector_count=n,
            checksum=checksum,
            **model_kwargs,
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

    def cache_prevalidated(self, loaded: LoadedModel) -> None:
        """Cache a LoadedModel that was previously validated and loaded from DB.

        Unlike register(), this skips validation (data was validated at
        original registration time and integrity verified via checksum).
        """
        self._models[loaded.model_version.model_version_id] = loaded
