"""Portfolio optimization engine — deterministic binary knapsack.

Pure deterministic solver. No LLM calls, no external solver dependencies.
Given the same inputs, ALWAYS produces the same outputs.
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base for all portfolio optimization domain errors."""


class PortfolioConfigError(PortfolioError):
    """Invalid portfolio optimization configuration."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INVALID_CONFIG") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)


class PortfolioInfeasibleError(PortfolioError):
    """No feasible subset exists under given constraints."""

    def __init__(self, message: str, *, reason_code: str = "PORTFOLIO_INFEASIBLE") -> None:
        self.message = message
        self.reason_code = reason_code
        super().__init__(message)
