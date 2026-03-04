"""Structural Path Analysis -- domain errors.

Math implementation added in Task 2.
"""


class SPAError(Exception):
    """Base for all SPA domain errors."""


class SPAConfigError(SPAError):
    """Invalid SPA configuration (max_depth/top_k out of bounds)."""

    def __init__(self, message: str, *, reason_code: str = "SPA_INVALID_CONFIG") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


class SPADimensionError(SPAError):
    """Matrix/vector dimension mismatch."""

    def __init__(self, message: str, *, reason_code: str = "SPA_DIMENSION_MISMATCH") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)
