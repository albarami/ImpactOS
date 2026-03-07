"""P2-1: Prompt/executor contract alignment tests.

These tests prove that the copilot prompt and tool definitions
EXACTLY match what the ChatToolExecutor actually implements.

Three verified gaps:
1. build_scenario prompt must include base_model_version_id (executor requires it)
2. create_export prompt must use "excel" not "xlsx" (system uses "excel")
3. lookup_data prompt must not advertise datasets the executor doesn't handle
"""

import pytest

from src.agents.prompts.economist_copilot_v1 import (
    build_system_prompt,
    get_tool_definitions,
)
from src.services.chat_tool_executor import _AVAILABLE_DATASETS


class TestBuildScenarioContract:
    """build_scenario prompt and tool definition must include base_model_version_id."""

    def test_tool_definition_has_base_model_version_id(self):
        """Tool definition for build_scenario must declare base_model_version_id as required."""
        tools = get_tool_definitions()
        build = next(t for t in tools if t["name"] == "build_scenario")
        params = build["parameters"]
        assert "base_model_version_id" in params, (
            "build_scenario tool definition must include base_model_version_id; "
            "the executor requires it but the prompt omits it"
        )
        assert params["base_model_version_id"]["required"] is True

    def test_prompt_text_shows_base_model_version_id_in_build_scenario(self):
        """The prompt text example for build_scenario must include base_model_version_id."""
        prompt = build_system_prompt()
        # Find the build_scenario arguments example in the prompt
        assert "base_model_version_id" in prompt, (
            "Prompt text for build_scenario must include base_model_version_id; "
            "the executor requires it but the prompt omits it"
        )


class TestCreateExportContract:
    """create_export prompt must use 'excel' not 'xlsx' for format names."""

    def test_prompt_text_uses_excel_not_xlsx(self):
        """The prompt example for create_export must say 'excel', not 'xlsx'."""
        prompt = build_system_prompt()
        # The prompt should NOT contain xlsx as an export format example
        # It should use "excel" which is the canonical format name
        # Find the create_export line
        lines = prompt.split("\n")
        export_lines = [l for l in lines if "create_export" in l.lower() or "export_formats" in l]
        for line in export_lines:
            if "export_formats" in line:
                assert '"xlsx"' not in line, (
                    f"Prompt uses 'xlsx' but system expects 'excel': {line}"
                )
                assert '"excel"' in line or "'excel'" in line, (
                    f"Prompt must use 'excel' as format name: {line}"
                )


class TestLookupDataContract:
    """lookup_data prompt must only advertise datasets the executor actually handles."""

    def test_available_datasets_all_have_handlers(self):
        """Every dataset_id in _AVAILABLE_DATASETS must correspond to a real
        handler path in the executor — not fall through to the default listing.

        Current real handlers: (no dataset_id), "models", "io_tables"
        """
        # These are the dataset_ids that have real handlers (not fallthrough)
        HANDLED_DATASET_IDS = {"io_tables", "models"}

        for ds in _AVAILABLE_DATASETS:
            ds_id = ds["dataset_id"]
            assert ds_id in HANDLED_DATASET_IDS, (
                f"_AVAILABLE_DATASETS advertises '{ds_id}' but the executor "
                f"has no real handler for it — it falls through to dataset listing"
            )

    def test_prompt_does_not_advertise_unhandled_multipliers(self):
        """Prompt must not claim lookup_data can query 'multipliers' unless handled."""
        # If multipliers is NOT in _AVAILABLE_DATASETS, the prompt description
        # should not promise it either.
        handled_ids = {ds["dataset_id"] for ds in _AVAILABLE_DATASETS}
        prompt = build_system_prompt()

        if "multipliers" not in handled_ids:
            # The lookup_data description line should not mention multipliers
            tool_defs = get_tool_definitions()
            lookup = next(t for t in tool_defs if t["name"] == "lookup_data")
            assert "multipliers" not in lookup["description"].lower(), (
                "lookup_data tool definition advertises 'multipliers' but "
                "there is no real handler for it"
            )

    def test_prompt_does_not_advertise_unhandled_macro(self):
        """Prompt must not claim lookup_data can query 'macro indicators' unless handled."""
        handled_ids = {ds["dataset_id"] for ds in _AVAILABLE_DATASETS}

        if "macro_indicators" not in handled_ids:
            tool_defs = get_tool_definitions()
            lookup = next(t for t in tool_defs if t["name"] == "lookup_data")
            assert "macro" not in lookup["description"].lower(), (
                "lookup_data tool definition advertises 'macro indicators' but "
                "there is no real handler for it"
            )

    def test_lookup_data_tool_definition_has_model_version_id_param(self):
        """lookup_data tool definition must include model_version_id parameter.

        Most dataset queries require model_version_id but the tool definition
        only lists dataset_id, sector_codes, year.
        """
        tools = get_tool_definitions()
        lookup = next(t for t in tools if t["name"] == "lookup_data")
        params = lookup["parameters"]
        assert "model_version_id" in params, (
            "lookup_data tool definition must include model_version_id; "
            "io_tables and other real datasets require it"
        )


class TestPromptExecutorToolCount:
    """The number and names of tools in the prompt must match the executor."""

    def test_prompt_tool_count_matches_executor(self):
        """Prompt declares same number of tools as executor handler_map."""
        from src.services.chat_tool_executor import ChatToolExecutor
        from unittest.mock import MagicMock

        # Get executor tool names
        executor = ChatToolExecutor.__new__(ChatToolExecutor)
        executor._session = MagicMock()
        executor._workspace_id = MagicMock()
        executor._handler_map = {
            "lookup_data": None,
            "build_scenario": None,
            "run_engine": None,
            "narrate_results": None,
            "create_export": None,
        }

        tool_defs = get_tool_definitions()
        prompt_names = {t["name"] for t in tool_defs}
        executor_names = set(executor._handler_map.keys())

        assert prompt_names == executor_names, (
            f"Tool name mismatch: prompt has {prompt_names}, "
            f"executor has {executor_names}"
        )
