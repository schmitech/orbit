#!/usr/bin/env python3
"""
Unit tests for MCPClientManager (server/services/mcp_client_service.py).

Covers the logic that does not require a live MCP server:
  - tool namespacing / OpenAI schema conversion
  - the server allowlist in get_all_tools
  - pre-call argument validation against the cached schema
  - the namespaced-name split and unknown-server handling in call_tool
  - the tool-result size cap
  - _expand_headers (token shorthand, explicit headers, env-var expansion)
  - transport selection: sse uses sse_client, http uses streamable_http_client

The actual transport (_call_tool_on_server / _list_tools_on_server) is mocked
so no subprocess is spawned.
"""

import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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


# ---------------------------------------------------------------------------
# _expand_headers
# ---------------------------------------------------------------------------

class TestExpandHeaders:
    def test_empty_config_returns_empty_dict(self):
        assert MCPClientManager._expand_headers({}) == {}

    def test_token_becomes_authorization_bearer(self):
        headers = MCPClientManager._expand_headers({"token": "abc123"})
        assert headers == {"Authorization": "Bearer abc123"}

    def test_explicit_headers_override_token(self):
        # If both token and an explicit Authorization header are present, the
        # explicit header wins (applied after token shorthand).
        headers = MCPClientManager._expand_headers({
            "token": "token-value",
            "headers": {"Authorization": "Bearer explicit-token", "X-Custom": "yes"},
        })
        assert headers["Authorization"] == "Bearer explicit-token"
        assert headers["X-Custom"] == "yes"

    def test_token_env_var_expanded(self, monkeypatch):
        monkeypatch.setenv("TEST_MCP_TOKEN", "secret-from-env")
        headers = MCPClientManager._expand_headers({"token": "${TEST_MCP_TOKEN}"})
        assert headers["Authorization"] == "Bearer secret-from-env"

    def test_header_values_env_var_expanded(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "key-value")
        headers = MCPClientManager._expand_headers({"headers": {"X-Key": "${MY_KEY}"}})
        assert headers["X-Key"] == "key-value"

    def test_non_string_header_value_converted(self):
        headers = MCPClientManager._expand_headers({"headers": {"X-Number": 42}})
        assert headers["X-Number"] == "42"

    def test_empty_token_is_ignored(self):
        headers = MCPClientManager._expand_headers({"token": ""})
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# Transport selection in _open_session
# ---------------------------------------------------------------------------

def _make_manager():
    return MCPClientManager({"servers": [], "tool_timeout": 5})


def _fake_session_cm():
    """Returns an async context manager that yields a mock ClientSession."""
    session = MagicMock()
    session.initialize = AsyncMock()

    @asynccontextmanager
    async def _cm(*args, **kwargs):
        yield session

    return _cm


class TestOpenSessionTransportSelection:
    async def test_sse_transport_uses_sse_client(self):
        mgr = _make_manager()
        server_cfg = {"transport": "sse", "url": "http://example.com/sse"}

        fake_read = MagicMock()
        fake_write = MagicMock()

        @asynccontextmanager
        async def fake_sse_client(url, headers=None):
            yield fake_read, fake_write

        @asynccontextmanager
        async def fake_client_session(read, write):
            s = MagicMock()
            s.initialize = AsyncMock()
            yield s

        with patch("mcp.client.sse.sse_client", fake_sse_client), \
             patch("mcp.client.session.ClientSession", fake_client_session):
            async with mgr._open_session(server_cfg) as session:
                assert session is not None

    async def test_http_transport_uses_streamable_http_client(self):
        mgr = _make_manager()
        server_cfg = {
            "transport": "http",
            "url": "http://example.com/mcp",
            "token": "mytoken",
        }

        @asynccontextmanager
        async def fake_streamable_http_client(url, http_client=None):
            yield MagicMock(), MagicMock(), MagicMock(return_value=None)

        @asynccontextmanager
        async def fake_create_mcp_http_client(headers=None, **kwargs):
            yield MagicMock()

        @asynccontextmanager
        async def fake_client_session(read, write):
            s = MagicMock()
            s.initialize = AsyncMock()
            yield s

        with patch("mcp.client.streamable_http.streamable_http_client", fake_streamable_http_client), \
             patch("mcp.shared._httpx_utils.create_mcp_http_client", fake_create_mcp_http_client), \
             patch("mcp.client.session.ClientSession", fake_client_session):
            async with mgr._open_session(server_cfg) as session:
                assert session is not None

    async def test_http_transport_sets_accept_header_by_default(self):
        mgr = _make_manager()
        server_cfg = {"transport": "http", "url": "http://example.com/mcp"}

        received_headers: dict = {}

        @asynccontextmanager
        async def fake_streamable_http_client(url, http_client=None):
            yield MagicMock(), MagicMock(), MagicMock()

        @asynccontextmanager
        async def fake_create_mcp_http_client(headers=None, **kwargs):
            received_headers.update(headers or {})
            yield MagicMock()

        @asynccontextmanager
        async def fake_client_session(read, write):
            s = MagicMock()
            s.initialize = AsyncMock()
            yield s

        with patch("mcp.client.streamable_http.streamable_http_client", fake_streamable_http_client), \
             patch("mcp.shared._httpx_utils.create_mcp_http_client", fake_create_mcp_http_client), \
             patch("mcp.client.session.ClientSession", fake_client_session):
            async with mgr._open_session(server_cfg):
                pass

        assert received_headers.get("Accept") == "application/json, text/event-stream"

    async def test_http_transport_token_becomes_authorization_header(self):
        mgr = _make_manager()
        server_cfg = {"transport": "http", "url": "http://example.com/mcp", "token": "tok-xyz"}

        received_headers: dict = {}

        @asynccontextmanager
        async def fake_streamable_http_client(url, http_client=None):
            yield MagicMock(), MagicMock(), MagicMock()

        @asynccontextmanager
        async def fake_create_mcp_http_client(headers=None, **kwargs):
            received_headers.update(headers or {})
            yield MagicMock()

        @asynccontextmanager
        async def fake_client_session(read, write):
            s = MagicMock()
            s.initialize = AsyncMock()
            yield s

        with patch("mcp.client.streamable_http.streamable_http_client", fake_streamable_http_client), \
             patch("mcp.shared._httpx_utils.create_mcp_http_client", fake_create_mcp_http_client), \
             patch("mcp.client.session.ClientSession", fake_client_session):
            async with mgr._open_session(server_cfg):
                pass

        assert received_headers.get("Authorization") == "Bearer tok-xyz"

    async def test_unsupported_transport_raises(self):
        mgr = _make_manager()
        with pytest.raises(ValueError, match="Unsupported MCP transport 'ws'"):
            async with mgr._open_session({"transport": "ws", "url": "ws://x"}):
                pass

    async def test_error_message_lists_all_valid_transports(self):
        mgr = _make_manager()
        try:
            async with mgr._open_session({"transport": "grpc"}):
                pass
        except ValueError as exc:
            assert "stdio" in str(exc)
            assert "sse" in str(exc)
            assert "http" in str(exc)
