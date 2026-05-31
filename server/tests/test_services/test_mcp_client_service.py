#!/usr/bin/env python3
"""
Unit tests for MCPClientManager (server/services/mcp_client_service.py).

Covers the logic that does not require a live MCP server:
  - tool namespacing / OpenAI schema conversion
  - the server allowlist in get_all_tools
  - pre-call argument validation against the cached schema
  - the namespaced-name split and unknown-server handling in call_tool
  - the tool-result size cap

The actual transport (_call_tool_on_server / _list_tools_on_server) is mocked
so no subprocess is spawned.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from services.mcp_client_service import MCPClientManager, get_mcp_client_manager


class _FakeMCPTool:
    """Mimics the attributes of mcp.types.Tool used by _to_openai_tool."""

    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.inputSchema = input_schema


def _manager_with_cache():
    """Build a manager with one server config and a pre-populated tool cache."""
    mgr = MCPClientManager(
        {
            "servers": [
                {"name": "filesystem", "command": "noop", "enabled": True},
                {"name": "github", "command": "noop", "enabled": True},
            ],
            "tool_result_max_chars": 50,
        }
    )
    mgr._tools_cache = {
        "filesystem": [
            MCPClientManager._to_openai_tool(
                "filesystem",
                _FakeMCPTool(
                    "read_file",
                    "Read a file",
                    {
                        "type": "object",
                        "properties": {"path": {"type": "string", "description": "abs path"}},
                        "required": ["path"],
                    },
                ),
            )
        ],
        "github": [
            MCPClientManager._to_openai_tool(
                "github",
                _FakeMCPTool("list_issues", "List issues", {"type": "object", "properties": {}}),
            )
        ],
    }
    mgr._cache_populated = True
    return mgr


class TestToOpenAITool:
    def test_namespacing_and_shape(self):
        tool = MCPClientManager._to_openai_tool(
            "filesystem",
            _FakeMCPTool("read_file", "Read a file", {"type": "object", "properties": {}}),
        )
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "filesystem__read_file"
        assert tool["function"]["description"] == "Read a file"
        assert tool["function"]["parameters"] == {"type": "object", "properties": {}}

    def test_missing_input_schema_defaults_to_empty_object(self):
        tool = MCPClientManager._to_openai_tool(
            "srv", _FakeMCPTool("t", "", None)
        )
        assert tool["function"]["parameters"] == {"type": "object", "properties": {}}


class TestGetAllTools:
    async def test_allowlist_filters_servers(self):
        mgr = _manager_with_cache()

        all_tools = await mgr.get_all_tools()
        names = {t["function"]["name"] for t in all_tools}
        assert names == {"filesystem__read_file", "github__list_issues"}

        only_fs = await mgr.get_all_tools(allowed_servers=["filesystem"])
        names = {t["function"]["name"] for t in only_fs}
        assert names == {"filesystem__read_file"}

    async def test_empty_allowlist_returns_all(self):
        # None == "all"; an explicit empty list is falsy and also means "no filter"
        mgr = _manager_with_cache()
        tools = await mgr.get_all_tools(allowed_servers=None)
        assert len(tools) == 2


class TestValidateArguments:
    def test_missing_required_param_reported(self):
        mgr = _manager_with_cache()
        err = mgr._validate_arguments("filesystem__read_file", {})
        assert err is not None
        assert "path" in err
        assert "Missing required parameter" in err

    def test_none_value_counts_as_missing(self):
        mgr = _manager_with_cache()
        err = mgr._validate_arguments("filesystem__read_file", {"path": None})
        assert err is not None and "path" in err

    def test_valid_args_pass(self):
        mgr = _manager_with_cache()
        assert mgr._validate_arguments("filesystem__read_file", {"path": "/tmp/x"}) is None

    def test_uncached_schema_skips_validation(self):
        mgr = _manager_with_cache()
        # Tool not present in cache → let the server validate (returns None)
        assert mgr._validate_arguments("filesystem__unknown_tool", {}) is None


class TestCallTool:
    async def test_rejects_unnamespaced_name(self):
        mgr = _manager_with_cache()
        with pytest.raises(ValueError, match="Expected '<server>__<tool>'"):
            await mgr.call_tool("read_file", {"path": "/tmp/x"})

    async def test_unknown_server_raises(self):
        mgr = _manager_with_cache()
        with pytest.raises(ValueError, match="Unknown MCP server"):
            await mgr.call_tool("nope__read_file", {})

    async def test_validation_error_returned_without_calling_server(self):
        mgr = _manager_with_cache()
        mgr._call_tool_on_server = AsyncMock()  # must NOT be called
        result = await mgr.call_tool("filesystem__read_file", {})
        assert result.startswith("Tool error:")
        assert "path" in result
        mgr._call_tool_on_server.assert_not_called()

    async def test_result_truncated_to_cap(self):
        mgr = _manager_with_cache()  # cap = 50
        mgr._call_tool_on_server = AsyncMock(return_value="x" * 500)
        result = await mgr.call_tool("filesystem__read_file", {"path": "/tmp/x"})
        assert result.endswith("[...result truncated]")
        assert len(result) <= 50 + len("\n[...result truncated]")

    async def test_short_result_passed_through(self):
        mgr = _manager_with_cache()
        mgr._call_tool_on_server = AsyncMock(return_value="hello")
        result = await mgr.call_tool("filesystem__read_file", {"path": "/tmp/x"})
        assert result == "hello"


class TestSingletonGate:
    def test_disabled_returns_none(self):
        import services.mcp_client_service as mod
        mod._instance = None
        assert get_mcp_client_manager({"mcp_client": {"enabled": False}}) is None

    def test_enabled_returns_manager(self):
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({"mcp_client": {"enabled": True, "servers": []}})
        assert isinstance(mgr, MCPClientManager)
        # idempotent — same instance on second call
        assert get_mcp_client_manager({"mcp_client": {"enabled": True}}) is mgr
        mod._instance = None
