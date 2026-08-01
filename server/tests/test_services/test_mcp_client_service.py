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

import asyncio
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


class _FakeClock:
    """Stand-in for time.monotonic with an explicitly advanced value."""

    def __init__(self, now=1000.0):
        self._now = now

    def __call__(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds


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

    async def test_failed_discovery_is_retried_after_retry_interval(self):
        tool = _FakeMCPTool(
            "recovered_tool", "Available after recovery", {"type": "object", "properties": {}}
        )
        mgr = MCPClientManager({
            "servers": [{"name": "remote", "transport": "http", "url": "http://example.test/mcp"}],
            "discovery_retry_interval": 30,
        })
        mgr._list_tools_on_server = AsyncMock(side_effect=[RuntimeError("server unavailable"), [tool]])

        clock = _FakeClock()
        with patch("services.mcp_client_service.time.monotonic", clock):
            assert await mgr.get_all_tools() == []
            assert mgr._failed_discovery_servers == {"remote"}

            # Inside the retry interval, an unavailable server is not re-dialed.
            clock.advance(29)
            assert await mgr.get_all_tools() == []
            assert mgr._list_tools_on_server.await_count == 1

            # Once the interval has elapsed, the recovered endpoint is rediscovered.
            clock.advance(2)
            tools = await mgr.get_all_tools()

        assert [tool_["function"]["name"] for tool_ in tools] == ["remote__recovered_tool"]
        assert mgr._failed_discovery_servers == set()

    async def test_retry_interval_measured_from_end_of_dial_loop(self):
        """A server that hangs until discovery_timeout must still be throttled."""
        mgr = MCPClientManager({
            "servers": [{"name": "remote", "transport": "http", "url": "http://example.test/mcp"}],
            "discovery_timeout": 30,
            "discovery_retry_interval": 30,
        })
        clock = _FakeClock()

        async def _hang(_server_config):
            # Simulate a black-holed connection burning the whole discovery_timeout.
            clock.advance(30)
            raise RuntimeError("timed out")

        mgr._list_tools_on_server = AsyncMock(side_effect=_hang)

        with patch("services.mcp_client_service.time.monotonic", clock):
            assert await mgr.get_all_tools() == []
            assert mgr._list_tools_on_server.await_count == 1

            # The next request must not immediately re-dial (and stall again).
            assert await mgr.get_all_tools() == []
            assert mgr._list_tools_on_server.await_count == 1

    async def test_unreachable_servers_are_dialed_concurrently(self):
        """N unreachable servers must cost one discovery_timeout, not N."""
        mgr = MCPClientManager({
            "servers": [
                {"name": f"remote{i}", "transport": "http", "url": "http://example.test/mcp"}
                for i in range(3)
            ],
        })
        # Sub-second budget: the config value is coerced to int, so set it directly.
        mgr._defaults["discovery_timeout"] = 0.05
        async def _hang(_server_config):
            # Never resolves, so each dial can only end via wait_for's timeout.
            await asyncio.Event().wait()

        mgr._list_tools_on_server = AsyncMock(side_effect=_hang)

        loop = asyncio.get_running_loop()
        started = loop.time()
        assert await mgr.get_all_tools() == []
        elapsed = loop.time() - started

        assert mgr._failed_discovery_servers == {"remote0", "remote1", "remote2"}
        # Serial dials would take ~0.15s; concurrent ones ~0.05s.
        assert elapsed < 0.12, f"dials appear serial ({elapsed:.3f}s)"

    async def test_healthy_server_cache_survives_another_servers_outage(self):
        healthy_tool = _FakeMCPTool("ok", "Healthy", {"type": "object", "properties": {}})
        mgr = MCPClientManager({
            "servers": [
                {"name": "healthy", "command": "noop", "enabled": True},
                {"name": "broken", "command": "noop", "enabled": True},
            ],
            "discovery_retry_interval": 30,
        })

        async def _list(server_config):
            if server_config["name"] == "healthy":
                return [healthy_tool]
            raise RuntimeError("server unavailable")

        mgr._list_tools_on_server = AsyncMock(side_effect=_list)

        clock = _FakeClock()
        with patch("services.mcp_client_service.time.monotonic", clock):
            tools = await mgr.get_all_tools()
            assert [t["function"]["name"] for t in tools] == ["healthy__ok"]
            assert mgr._failed_discovery_servers == {"broken"}

            # The retry pass only re-dials 'broken' and leaves the healthy cache intact.
            clock.advance(31)
            tools = await mgr.get_all_tools()

        assert [t["function"]["name"] for t in tools] == ["healthy__ok"]
        assert [c.args[0]["name"] for c in mgr._list_tools_on_server.await_args_list] == [
            "healthy",
            "broken",
            "broken",
        ]


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


class TestPerServerSettings:
    """mcp_clients-level values are defaults; server entries override them."""

    def _mgr(self):
        return MCPClientManager({
            "tool_timeout": 30,
            "max_tool_iterations": 5,
            "allow_opportunistic": False,
            "tool_result_max_chars": 8000,
            "servers": [
                {"name": "fast", "command": "noop"},
                {
                    "name": "slow",
                    "command": "noop",
                    "tool_timeout": 90,
                    "max_tool_iterations": 9,
                    "allow_opportunistic": True,
                    "tool_result_max_chars": 100,
                },
            ],
        })

    def test_server_override_wins_over_default(self):
        mgr = self._mgr()
        assert mgr.setting("fast", "tool_timeout") == 30
        assert mgr.setting("slow", "tool_timeout") == 90

    def test_falls_back_to_hardcoded_default_when_unset_everywhere(self):
        mgr = MCPClientManager({"servers": [{"name": "s", "command": "noop"}]})
        assert mgr.setting("s", "discovery_timeout") == 5
        assert mgr.setting("s", "allow_opportunistic") is False

    def test_invalid_value_falls_back_to_hardcoded_default(self):
        mgr = MCPClientManager({
            "servers": [{"name": "s", "command": "noop", "tool_timeout": "abc"}],
        })
        assert mgr.setting("s", "tool_timeout") == 30

    def test_invalid_override_falls_back_to_configured_default_not_hardcoded(self):
        """An unusable per-server value must not skip past the admin's
        mcp_clients-level value down to the hardcoded default."""
        mgr = MCPClientManager({
            "tool_timeout": 45,
            "servers": [{"name": "s", "command": "noop", "tool_timeout": "abc"}],
        })
        assert mgr.setting("s", "tool_timeout") == 45

    def test_invalid_top_level_default_falls_back_to_hardcoded(self):
        mgr = MCPClientManager({
            "tool_timeout": "nonsense",
            "servers": [{"name": "s", "command": "noop"}],
        })
        assert mgr.setting("s", "tool_timeout") == 30

    def test_opportunistic_servers_filters_by_optin_and_allowlist(self):
        mgr = self._mgr()
        assert mgr.opportunistic_servers() == ["slow"]
        assert mgr.opportunistic_servers(["fast"]) == []
        assert mgr.opportunistic_servers(["fast", "slow"]) == ["slow"]

    def test_max_tool_iterations_takes_most_permissive(self):
        mgr = self._mgr()
        assert mgr.max_tool_iterations_for(["fast"]) == 5
        assert mgr.max_tool_iterations_for(["fast", "slow"]) == 9
        # No known server → the mcp_clients-level default.
        assert mgr.max_tool_iterations_for([]) == 5
        assert mgr.max_tool_iterations_for(["unknown"]) == 5

    def test_servers_in_tools_derives_names_from_namespacing(self):
        tools = [
            {"function": {"name": "fast__a"}},
            {"function": {"name": "slow__b"}},
            {"function": {"name": "not_namespaced"}},
        ]
        assert MCPClientManager.servers_in_tools(tools) == {"fast", "slow"}

    async def test_per_server_tool_result_cap(self):
        mgr = self._mgr()
        mgr._cache_populated = True
        mgr._call_tool_on_server = AsyncMock(return_value="x" * 500)

        slow = await mgr.call_tool("slow__t", {})
        assert slow.endswith("[...result truncated]")
        assert len(slow) <= 100 + len("\n[...result truncated]")

        fast = await mgr.call_tool("fast__t", {})
        assert fast == "x" * 500  # under the 8000 default

    async def test_per_server_tool_timeout_applied(self):
        """The per-server budget, not the global default, is what wait_for gets."""
        mgr = self._mgr()
        mgr._cache_populated = True
        mgr._call_tool_on_server = AsyncMock(return_value="ok")

        seen = []
        real_wait_for = asyncio.wait_for

        async def _spy(awaitable, timeout):
            seen.append(timeout)
            return await real_wait_for(awaitable, timeout)

        with patch("services.mcp_client_service.asyncio.wait_for", _spy):
            await mgr.call_tool("slow__t", {})
            await mgr.call_tool("fast__t", {})

        assert seen == [90, 30]

    async def test_timeout_message_reports_per_server_budget(self):
        mgr = self._mgr()
        mgr._cache_populated = True
        mgr._server_configs["slow"]["tool_timeout"] = 0  # fires immediately

        async def _hang(*_args, **_kwargs):
            await asyncio.Event().wait()

        mgr._call_tool_on_server = AsyncMock(side_effect=_hang)
        with pytest.raises(RuntimeError, match="timed out after 0s"):
            await mgr.call_tool("slow__t", {})

    async def test_opportunistic_only_filters_get_all_tools(self):
        mgr = self._mgr()
        mgr._tools_cache = {
            "fast": [{"function": {"name": "fast__a"}}],
            "slow": [{"function": {"name": "slow__b"}}],
        }
        mgr._cache_populated = True
        tools = await mgr.get_all_tools(opportunistic_only=True)
        assert [t["function"]["name"] for t in tools] == ["slow__b"]
        assert len(await mgr.get_all_tools()) == 2

    async def test_per_server_discovery_retry_intervals_are_independent(self):
        mgr = MCPClientManager({
            "discovery_retry_interval": 30,
            "servers": [
                {"name": "quick", "command": "noop", "discovery_retry_interval": 5},
                {"name": "patient", "command": "noop"},
            ],
        })
        mgr._list_tools_on_server = AsyncMock(side_effect=RuntimeError("down"))

        clock = _FakeClock()
        with patch("services.mcp_client_service.time.monotonic", clock):
            await mgr.get_all_tools()
            assert mgr._failed_discovery_servers == {"quick", "patient"}

            # After 6s only 'quick' is due for a retry.
            clock.advance(6)
            await mgr.get_all_tools()
            dialed = [c.args[0]["name"] for c in mgr._list_tools_on_server.await_args_list]
            assert dialed.count("quick") == 2 and dialed.count("patient") == 1

            # After the full 30s, 'patient' is retried too.
            clock.advance(25)
            await mgr.get_all_tools()

        dialed = [c.args[0]["name"] for c in mgr._list_tools_on_server.await_args_list]
        assert dialed.count("quick") == 3 and dialed.count("patient") == 2


class TestSingletonGate:
    def test_disabled_returns_none(self):
        import services.mcp_client_service as mod
        mod._instance = None
        assert get_mcp_client_manager({"mcp_clients": {"enabled": False}}) is None

    def test_enabled_returns_manager(self):
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})
        assert isinstance(mgr, MCPClientManager)
        # idempotent — same instance on second call
        assert get_mcp_client_manager({"mcp_clients": {"enabled": True}}) is mgr
        mod._instance = None


class TestReloadMcpClientManager:
    def test_reload_rebuilds_with_new_settings(self):
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({
            "mcp_clients": {"enabled": True, "tool_timeout": 30, "servers": []},
        })
        new_mgr = mod.reload_mcp_client_manager({
            "mcp_clients": {"enabled": True, "tool_timeout": 99, "servers": []},
        })
        assert new_mgr is not mgr
        assert new_mgr.setting("anything", "tool_timeout") == 99
        assert mod._instance is new_mgr
        mod._instance = None

    def test_reload_disabling_returns_none(self):
        import services.mcp_client_service as mod
        mod._instance = None
        get_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})
        result = mod.reload_mcp_client_manager({"mcp_clients": {"enabled": False}})
        assert result is None
        assert mod._instance is None
        assert get_mcp_client_manager({"mcp_clients": {"enabled": False}}) is None

    def test_reload_enabling_builds_manager(self):
        import services.mcp_client_service as mod
        mod._instance = None
        result = mod.reload_mcp_client_manager({
            "mcp_clients": {"enabled": True, "servers": []},
        })
        assert isinstance(result, MCPClientManager)
        mod._instance = None


class TestRefreshToolCache:
    @pytest.mark.asyncio
    async def test_refresh_clears_failures_and_redials(self):
        mgr = MCPClientManager({
            "servers": [{"name": "flaky", "transport": "stdio", "command": "x"}],
        })
        mgr._list_tools_on_server = AsyncMock(side_effect=RuntimeError("down"))
        await mgr.get_all_tools()
        assert mgr._failed_discovery_servers == {"flaky"}

        mgr._list_tools_on_server = AsyncMock(return_value=[])
        await mgr.refresh_tool_cache()
        assert mgr._failed_discovery_servers == set()
        assert mgr._cache_populated is True
        mgr._list_tools_on_server.assert_awaited()

    @pytest.mark.asyncio
    async def test_scoped_refresh_only_redials_named_servers(self):
        mgr = MCPClientManager({
            "servers": [
                {"name": "a", "transport": "stdio", "command": "x"},
                {"name": "b", "transport": "stdio", "command": "y"},
            ],
        })
        mgr._list_tools_on_server = AsyncMock(return_value=[])
        await mgr.get_all_tools()
        assert set(mgr._tools_cache) == {"a", "b"}

        # 'b' fails, then a scoped refresh of only 'a' must not touch 'b'.
        mgr._failed_discovery_servers.add("b")
        mgr._tools_cache["b"] = []
        redial = AsyncMock(return_value=[])
        mgr._list_tools_on_server = redial
        await mgr.refresh_tool_cache(["a"])

        assert redial.await_count == 1
        assert redial.await_args.args[0]["name"] == "a"
        assert "b" in mgr._failed_discovery_servers

    @pytest.mark.asyncio
    async def test_scoped_refresh_ignores_unknown_server(self):
        mgr = MCPClientManager({
            "servers": [{"name": "a", "transport": "stdio", "command": "x"}],
        })
        mgr._list_tools_on_server = AsyncMock(return_value=[])
        await mgr.refresh_tool_cache(["does-not-exist"])
        mgr._list_tools_on_server.assert_not_awaited()


class TestUpdateServer:
    @pytest.mark.asyncio
    async def test_update_server_adds_new_entry(self):
        mgr = MCPClientManager({"servers": []})
        await mgr.update_server("new", {"name": "new", "transport": "stdio", "command": "x", "enabled": True})
        assert "new" in mgr._server_configs

    @pytest.mark.asyncio
    async def test_update_server_replaces_existing_entry(self):
        mgr = MCPClientManager({
            "servers": [{"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 10}],
        })
        await mgr.update_server("a", {"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 99})
        assert mgr.setting("a", "tool_timeout") == 99

    @pytest.mark.asyncio
    async def test_update_server_none_removes_and_clears_cache(self):
        mgr = MCPClientManager({
            "servers": [{"name": "a", "transport": "stdio", "command": "x"}],
        })
        mgr._tools_cache["a"] = [{"function": {"name": "a__tool"}}]
        mgr._failed_discovery_servers.add("a")
        await mgr.update_server("a", None)
        assert "a" not in mgr._server_configs
        assert "a" not in mgr._tools_cache
        assert "a" not in mgr._failed_discovery_servers

    @pytest.mark.asyncio
    async def test_update_server_disabled_entry_removes(self):
        mgr = MCPClientManager({
            "servers": [{"name": "a", "transport": "stdio", "command": "x"}],
        })
        await mgr.update_server("a", {"name": "a", "transport": "stdio", "command": "x", "enabled": False})
        assert "a" not in mgr._server_configs

    @pytest.mark.asyncio
    async def test_update_server_leaves_other_servers_untouched(self):
        mgr = MCPClientManager({
            "servers": [
                {"name": "a", "transport": "stdio", "command": "x"},
                {"name": "b", "transport": "stdio", "command": "y"},
            ],
        })
        mgr._tools_cache["b"] = [{"function": {"name": "b__tool"}}]
        await mgr.update_server("a", {"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 5})
        assert mgr._tools_cache["b"] == [{"function": {"name": "b__tool"}}]
        assert "b" in mgr._server_configs


class TestGetCurrentMcpClientManager:
    def test_returns_none_when_unset(self):
        import services.mcp_client_service as mod
        mod._instance = None
        assert mod.get_current_mcp_client_manager() is None

    def test_returns_existing_without_constructing(self):
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})
        assert mod.get_current_mcp_client_manager() is mgr
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
