"""Tests for Issue #17: fail-closed guard + structured ProviderUnavailableError."""

import pytest

from src.agents.guards import require_llm_backing
from src.agents.llm_client import ProviderUnavailableError


class TestProviderUnavailableErrorStructured:
    """ProviderUnavailableError carries structured reason_code, agent_name, environment."""

    def test_default_fields(self) -> None:
        err = ProviderUnavailableError("some message")
        assert str(err) == "some message"
        assert err.reason_code == "PROVIDER_UNAVAILABLE"
        assert err.agent_name == ""
        assert err.environment == ""

    def test_custom_fields(self) -> None:
        err = ProviderUnavailableError(
            "split has no LLM",
            reason_code="SPLIT_NO_LLM_BACKING",
            agent_name="SplitAgent",
            environment="staging",
        )
        assert err.reason_code == "SPLIT_NO_LLM_BACKING"
        assert err.agent_name == "SplitAgent"
        assert err.environment == "staging"

    def test_backward_compatible_positional(self) -> None:
        """Existing raise sites use positional message only."""
        err = ProviderUnavailableError("no key")
        assert str(err) == "no key"
        assert err.reason_code == "PROVIDER_UNAVAILABLE"


class TestRequireLlmBacking:
    """Guard function: non-dev raises, dev warns."""

    def test_non_dev_staging_raises(self) -> None:
        with pytest.raises(ProviderUnavailableError) as exc_info:
            require_llm_backing(
                agent_name="SplitAgent",
                environment="staging",
                has_llm=False,
                reason_code="SPLIT_NO_LLM_BACKING",
            )
        assert exc_info.value.reason_code == "SPLIT_NO_LLM_BACKING"
        assert exc_info.value.agent_name == "SplitAgent"
        assert exc_info.value.environment == "staging"

    def test_non_dev_prod_raises(self) -> None:
        with pytest.raises(ProviderUnavailableError) as exc_info:
            require_llm_backing(
                agent_name="AssumptionDraftAgent",
                environment="prod",
                has_llm=False,
                reason_code="ASSUMPTION_NO_LLM_BACKING",
            )
        assert exc_info.value.reason_code == "ASSUMPTION_NO_LLM_BACKING"

    def test_dev_does_not_raise(self) -> None:
        require_llm_backing(
            agent_name="SplitAgent",
            environment="dev",
            has_llm=False,
            reason_code="SPLIT_NO_LLM_BACKING",
        )

    def test_has_llm_true_does_not_raise(self) -> None:
        require_llm_backing(
            agent_name="SplitAgent",
            environment="staging",
            has_llm=True,
            reason_code="SPLIT_NO_LLM_BACKING",
        )

    def test_error_message_no_secrets(self) -> None:
        """Error message must not contain tokens/keys."""
        with pytest.raises(ProviderUnavailableError) as exc_info:
            require_llm_backing(
                agent_name="SplitAgent",
                environment="staging",
                has_llm=False,
                reason_code="SPLIT_NO_LLM_BACKING",
            )
        msg = str(exc_info.value)
        assert "key" not in msg.lower() or "api" not in msg.lower()
        assert "token" not in msg.lower()
        assert "SplitAgent" in msg
        assert "SPLIT_NO_LLM_BACKING" in msg
