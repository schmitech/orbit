#!/usr/bin/env python3
"""
Unit tests for MCPClientManager (server/services/mcp_client_service.py).

Covers the logic that does not require a live MCP server:
  - tool namespacing / OpenAI schema conversion
  - the server allowlist in get_all_tools
  - pre-call argument validation against the cached schema
  - the namespaced-name split and unknown-server handling in call_tool
  - the tool-result size cap
  - _expand_headers (explicit headers and env-var expansion)
  - transport selection: http uses streamable_http_client

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

import services.mcp_connection_pool as pool_mod
from services.mcp_client_service import MCPClientManager, get_mcp_client_manager


class _FakeMCPTool:
    """Mimics the attributes of mcp.types.Tool used by _to_openai_tool."""

    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.inputSchema = input_schema


def _stub_list_tools(mgr, fn):
    """Wrap an async `_list_tools_on_server` replacement so it also records
    its outcome on the server's breaker. These stubs bypass
    ServerConnectionPool.run() entirely (which is what records breaker
    outcomes in production), so the test must model that side effect itself
    rather than relying on the production call chain to produce it.
    """
    async def wrapped(server_config):
        breaker = mgr._pool_for(server_config["name"]).breaker
        try:
            result = await fn(server_config)
        except BaseException:
            # BaseException so a real wait_for-triggered CancelledError (not
            # just a plain Exception) still records the failure, mirroring
            # ServerConnectionPool.run()'s handling.
            breaker.record_failure()
            raise
        breaker.record_success()
        return result

    return AsyncMock(side_effect=wrapped)


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
        outcomes = [RuntimeError("server unavailable"), [tool]]

        async def fake(_server_config):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        mgr._list_tools_on_server = _stub_list_tools(mgr, fake)

        clock = _FakeClock()
        with patch("time.monotonic", clock):
            assert await mgr.get_all_tools() == []
            assert not mgr.is_reachable("remote")

            # Inside the retry interval, an unavailable server is not re-dialed.
            clock.advance(29)
            assert await mgr.get_all_tools() == []
            assert mgr._list_tools_on_server.await_count == 1

            # Once the interval has elapsed, the recovered endpoint is rediscovered.
            clock.advance(2)
            tools = await mgr.get_all_tools()

        assert [tool_["function"]["name"] for tool_ in tools] == ["remote__recovered_tool"]
        assert mgr.is_reachable("remote")

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

        mgr._list_tools_on_server = _stub_list_tools(mgr, _hang)

        with patch("time.monotonic", clock):
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

        mgr._list_tools_on_server = _stub_list_tools(mgr, _hang)

        loop = asyncio.get_running_loop()
        started = loop.time()
        assert await mgr.get_all_tools() == []
        elapsed = loop.time() - started

        assert all(not mgr.is_reachable(n) for n in ("remote0", "remote1", "remote2"))
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

        mgr._list_tools_on_server = _stub_list_tools(mgr, _list)

        clock = _FakeClock()
        with patch("time.monotonic", clock):
            tools = await mgr.get_all_tools()
            assert [t["function"]["name"] for t in tools] == ["healthy__ok"]
            assert mgr.is_reachable("healthy") and not mgr.is_reachable("broken")

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

    def test_null_servers_key_does_not_crash(self):
        # YAML parses a `servers:` key with every entry underneath it
        # commented out as `servers: null`, not `servers: []` — the shape
        # config/mcp_clients.yaml ships with before any server is added.
        mgr = MCPClientManager({"enabled": True, "servers": None})
        assert mgr._server_configs == {}

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
        async def _fail(_server_config):
            raise RuntimeError("down")

        mgr._list_tools_on_server = _stub_list_tools(mgr, _fail)

        clock = _FakeClock()
        with patch("time.monotonic", clock):
            await mgr.get_all_tools()
            assert not mgr.is_reachable("quick") and not mgr.is_reachable("patient")

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
    async def test_reload_rebuilds_with_new_settings(self):
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({
            "mcp_clients": {"enabled": True, "tool_timeout": 30, "servers": []},
        })
        new_mgr = await mod.reload_mcp_client_manager({
            "mcp_clients": {"enabled": True, "tool_timeout": 99, "servers": []},
        })
        assert new_mgr is not mgr
        assert new_mgr.setting("anything", "tool_timeout") == 99
        assert mod._instance is new_mgr
        mod._instance = None

    async def test_reload_disabling_returns_none(self):
        import services.mcp_client_service as mod
        mod._instance = None
        get_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})
        result = await mod.reload_mcp_client_manager({"mcp_clients": {"enabled": False}})
        assert result is None
        assert mod._instance is None
        assert get_mcp_client_manager({"mcp_clients": {"enabled": False}}) is None

    async def test_reload_enabling_builds_manager(self):
        import services.mcp_client_service as mod
        mod._instance = None
        result = await mod.reload_mcp_client_manager({
            "mcp_clients": {"enabled": True, "servers": []},
        })
        assert isinstance(result, MCPClientManager)
        mod._instance = None

    async def test_failed_drain_does_not_leave_closed_manager_as_singleton(self):
        import services.mcp_client_service as mod

        old_manager = MagicMock()
        old_manager.aclose = AsyncMock(side_effect=RuntimeError("close failed"))
        mod._instance = old_manager

        with pytest.raises(RuntimeError, match="close failed"):
            await mod.reload_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})

        assert mod._instance is None

    async def test_reload_drains_old_managers_pools(self):
        """The outgoing manager's pooled connections must be closed, not leaked."""
        import services.mcp_client_service as mod
        mod._instance = None
        mgr = get_mcp_client_manager({
            "mcp_clients": {"enabled": True, "servers": [{"name": "a", "command": "noop"}]},
        })
        closed = []
        fake_conn = pool_mod.MCPConnection(session=MagicMock(), stack=MagicMock())
        fake_conn.close = AsyncMock(side_effect=lambda: closed.append(True))
        pool = pool_mod.ServerConnectionPool(pool_size=2, idle_timeout=0, breaker_recovery_timeout=30)
        pool._idle = [fake_conn]
        pool._all = {fake_conn}
        mgr._pools["a"] = pool

        await mod.reload_mcp_client_manager({"mcp_clients": {"enabled": True, "servers": []}})
        assert closed == [True]


class TestRefreshToolCache:
    @pytest.mark.asyncio
    async def test_refresh_rechecks_static_tool_skill_catalog(self, tmp_path):
        runtime_config = {
            "tool_skills": {"directory": str(tmp_path)},
            "adapters": [],
        }
        mgr = MCPClientManager(
            {"servers": [{"name": "a", "transport": "stdio", "command": "x"}]},
            runtime_config=runtime_config,
        )
        mgr._list_tools_on_server = AsyncMock(return_value=[])

        with patch("services.tool_skill_service.warn_catalog_overflow") as warn:
            await mgr.refresh_tool_cache()

        warn.assert_called_once()
        assert warn.call_args.args[0] is runtime_config
        assert warn.call_args.args[2] is mgr

    @pytest.mark.asyncio
    async def test_refresh_clears_failures_and_redials(self):
        mgr = MCPClientManager({
            "servers": [{"name": "flaky", "transport": "stdio", "command": "x"}],
        })
        async def _fail(_server_config):
            raise RuntimeError("down")

        mgr._list_tools_on_server = _stub_list_tools(mgr, _fail)
        await mgr.get_all_tools()
        assert not mgr.is_reachable("flaky")

        async def _succeed(_server_config):
            return []

        mgr._list_tools_on_server = _stub_list_tools(mgr, _succeed)
        await mgr.refresh_tool_cache()
        assert mgr.is_reachable("flaky")
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
        mgr._pool_for("b").breaker.record_failure()
        mgr._tools_cache["b"] = []
        redial = AsyncMock(return_value=[])
        mgr._list_tools_on_server = redial
        await mgr.refresh_tool_cache(["a"])

        assert redial.await_count == 1
        assert redial.await_args.args[0]["name"] == "a"
        assert not mgr.is_reachable("b")

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
        mgr._pool_for("a").breaker.record_failure()
        await mgr.update_server("a", None)
        assert "a" not in mgr._server_configs
        assert "a" not in mgr._tools_cache
        assert "a" not in mgr._pools

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

    def test_legacy_token_key_is_ignored(self):
        assert MCPClientManager._expand_headers({"token": "abc123"}) == {}

    def test_explicit_authorization_header_is_preserved(self):
        headers = MCPClientManager._expand_headers({
            "headers": {"Authorization": "Bearer explicit-token", "X-Custom": "yes"},
        })
        assert headers["Authorization"] == "Bearer explicit-token"
        assert headers["X-Custom"] == "yes"

    def test_authorization_env_var_expanded(self, monkeypatch):
        monkeypatch.setenv("TEST_MCP_TOKEN", "secret-from-env")
        headers = MCPClientManager._expand_headers({"headers": {"Authorization": "Bearer ${TEST_MCP_TOKEN}"}})
        assert headers["Authorization"] == "Bearer secret-from-env"

    def test_header_values_env_var_expanded(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "key-value")
        headers = MCPClientManager._expand_headers({"headers": {"X-Key": "${MY_KEY}"}})
        assert headers["X-Key"] == "key-value"

    def test_non_string_header_value_converted(self):
        headers = MCPClientManager._expand_headers({"headers": {"X-Number": 42}})
        assert headers["X-Number"] == "42"

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
    async def test_http_transport_uses_streamable_http_client(self):
        mgr = _make_manager()
        server_cfg = {
            "transport": "http",
            "url": "http://example.com/mcp",
            "headers": {"Authorization": "Bearer mytoken"},
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

    async def test_http_transport_passes_authorization_header(self):
        mgr = _make_manager()
        server_cfg = {"transport": "http", "url": "http://example.com/mcp", "headers": {"Authorization": "Bearer tok-xyz"}}

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
            assert "http" in str(exc)


# ---------------------------------------------------------------------------
# Connection pooling
# ---------------------------------------------------------------------------

def _fake_connection(mgr, fail=False):
    """Build a real MCPConnection wrapping a mock session, without touching
    a real transport (its stack is a no-op AsyncMock)."""
    session = MagicMock()
    if fail:
        session.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
        session.list_tools = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        result = MagicMock(isError=False)
        result.content = []
        session.call_tool = AsyncMock(return_value=result)
        session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    stack = MagicMock()
    stack.aclose = AsyncMock()
    return pool_mod.MCPConnection(session=session, stack=stack)


class TestConnectionPooling:
    def _pooled_manager(self, pool_size=2, pool_idle_timeout=300):
        return MCPClientManager({
            "servers": [{
                "name": "srv", "transport": "stdio", "command": "x",
                "pool_size": pool_size, "pool_idle_timeout": pool_idle_timeout,
            }],
        })

    async def test_pool_size_one_serializes_concurrent_calls(self):
        mgr = self._pooled_manager(pool_size=1)
        created = []

        async def build(server_config):
            conn = _fake_connection(mgr)
            created.append(conn)
            return conn

        mgr._create_connection = build
        mgr._cache_populated = True
        mgr._tools_cache["srv"] = []

        order = []

        async def call(i):
            order.append(("start", i))
            result = await mgr._call_tool_on_server({"name": "srv"}, "t", {})
            order.append(("end", i))
            return result

        await asyncio.gather(call(1), call(2))

        # Only one connection ever created — the second call reused it,
        # it did not open a second concurrent one.
        assert len(created) == 1
        # The first call's 'end' must precede the second call's 'start'
        # given a single-slot pool serializes access.
        assert order.index(("end", 1)) < order.index(("start", 2)) or \
            order.index(("end", 2)) < order.index(("start", 1))

    async def test_connection_reused_across_calls(self):
        mgr = self._pooled_manager(pool_size=2)
        created = []

        async def build(server_config):
            conn = _fake_connection(mgr)
            created.append(conn)
            return conn

        mgr._create_connection = build

        await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        assert len(created) == 1  # second call reused the idle connection

    async def test_reconnect_after_failure_retries_once(self):
        mgr = self._pooled_manager(pool_size=2)
        connections = [_fake_connection(mgr, fail=True), _fake_connection(mgr, fail=False)]

        async def build(server_config):
            return connections.pop(0)

        mgr._create_connection = build

        result = await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        assert not result.startswith("Tool error:")
        assert not connections  # both connections were consumed

    async def test_second_consecutive_failure_propagates_and_opens_breaker(self):
        mgr = self._pooled_manager(pool_size=2)

        async def build(server_config):
            return _fake_connection(mgr, fail=True)

        mgr._create_connection = build

        with pytest.raises(RuntimeError, match="boom"):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        assert not mgr.is_reachable("srv")

    async def test_shared_breaker_gates_discovery_and_pool(self):
        """A pooled call-tool failure must also block discovery for that
        server until the shared breaker's recovery window elapses."""
        mgr = self._pooled_manager(pool_size=2)
        mgr._server_configs["srv"]["discovery_retry_interval"] = 30

        async def build(server_config):
            return _fake_connection(mgr, fail=True)

        mgr._create_connection = build
        with pytest.raises(RuntimeError):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        mgr._cache_populated = True  # force the "retry only if due" path
        mgr._list_tools_on_server = AsyncMock(return_value=[])
        await mgr.get_all_tools()
        # Breaker still open (recovery_timeout not elapsed) — discovery skipped.
        mgr._list_tools_on_server.assert_not_awaited()

    async def test_cancelled_call_releases_connection_instead_of_leaking_permit(self):
        """A tool_timeout (asyncio.CancelledError) must not exhaust the pool."""
        mgr = self._pooled_manager(pool_size=1)
        conn = _fake_connection(mgr)
        conn.session.call_tool = AsyncMock(side_effect=asyncio.CancelledError())

        async def build(server_config):
            return conn

        mgr._create_connection = build

        with pytest.raises(asyncio.CancelledError):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        # The cancellation also (correctly) opened the breaker; reset it here
        # since this test is specifically about the pool permit, not breaker
        # semantics (covered separately below).
        mgr._pool_for("srv").reset_breaker()

        # The single permit must have been released, not leaked.
        conn2 = _fake_connection(mgr)

        async def build2(server_config):
            return conn2

        mgr._create_connection = build2
        result = await asyncio.wait_for(
            mgr._call_tool_on_server({"name": "srv"}, "t", {}), timeout=1
        )
        assert not result.startswith("Tool error:")

    async def test_connection_build_failure_retries_and_records_breaker_failure(self):
        """A failure while opening the replacement connection (not just after
        it's open) must still hit the retry/breaker path, not bypass it."""
        mgr = self._pooled_manager(pool_size=2)
        calls = []

        async def build(server_config):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("connect failed")
            return _fake_connection(mgr, fail=False)

        mgr._create_connection = build

        result = await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        assert not result.startswith("Tool error:")
        assert len(calls) == 2  # first build failed, second succeeded
        assert mgr.is_reachable("srv")  # recovered after the successful retry

    async def test_connection_build_failure_opens_breaker_after_final_attempt(self):
        mgr = self._pooled_manager(pool_size=2)

        async def build(server_config):
            raise RuntimeError("connect failed")

        mgr._create_connection = build

        with pytest.raises(RuntimeError, match="connect failed"):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        assert not mgr.is_reachable("srv")

    async def test_idle_timeout_evicts_stale_connection(self):
        mgr = self._pooled_manager(pool_size=2, pool_idle_timeout=10)
        created = []

        async def build(server_config):
            conn = _fake_connection(mgr)
            created.append(conn)
            return conn

        mgr._create_connection = build

        clock = _FakeClock()
        with patch("time.monotonic", clock):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})
            clock.advance(11)
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        assert len(created) == 2  # first connection discarded as stale

    async def test_pool_size_zero_opens_fresh_connection_each_call(self):
        mgr = self._pooled_manager(pool_size=0)
        created = []

        async def build(server_config):
            conn = _fake_connection(mgr)
            created.append(conn)
            return conn

        mgr._create_connection = build

        await mgr._call_tool_on_server({"name": "srv"}, "t", {})
        await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        assert len(created) == 2  # no reuse — a fresh connection every call
        assert all(c.stack.aclose.await_count == 1 for c in created)  # each torn down immediately

    async def test_scoped_drain_does_not_touch_other_servers_pool(self):
        mgr = MCPClientManager({
            "servers": [
                {"name": "a", "transport": "stdio", "command": "x"},
                {"name": "b", "transport": "stdio", "command": "y"},
            ],
        })
        conn_a = _fake_connection(mgr)
        conn_b = _fake_connection(mgr)
        pool_a = pool_mod.ServerConnectionPool(pool_size=2, idle_timeout=0, breaker_recovery_timeout=30)
        pool_a._idle = [conn_a]
        pool_a._all = {conn_a}
        pool_b = pool_mod.ServerConnectionPool(pool_size=2, idle_timeout=0, breaker_recovery_timeout=30)
        pool_b._idle = [conn_b]
        pool_b._all = {conn_b}
        mgr._pools["a"] = pool_a
        mgr._pools["b"] = pool_b

        await mgr.update_server("a", {"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 5})

        assert conn_a.stack.aclose.await_count == 1
        assert conn_b.stack.aclose.await_count == 0
        assert "b" in mgr._pools and mgr._pools["b"] is pool_b

    async def test_drain_closes_connection_built_by_a_late_acquirer(self):
        """A caller already waiting on the semaphore when drain() runs can
        still build a brand new connection afterward — that connection must
        not be handed out as reusable, since nothing will ever drain this
        pool again once it's dropped from the manager."""
        pool = pool_mod.ServerConnectionPool(pool_size=1, idle_timeout=0, breaker_recovery_timeout=30)
        # Saturate the only slot so the next acquire has to wait.
        holder = _fake_connection(None)

        async def build_holder():
            return holder

        held = await pool._acquire(build_holder)

        waiter_conn = _fake_connection(None)

        async def build_after_wait():
            return waiter_conn

        waiter_task = asyncio.create_task(pool._acquire(build_after_wait))
        await asyncio.sleep(0)  # let the waiter block on the semaphore

        await pool.drain()
        await pool._release(held, healthy=True)  # frees the slot for the waiter

        acquired = await waiter_task
        assert acquired is waiter_conn
        await pool._release(acquired, healthy=True)

        # A connection built after drain() must close on release, not sit
        # idle in a pool nothing will ever drain again.
        assert waiter_conn.closing is True
        assert waiter_conn.stack.aclose.await_count == 1
        assert pool._idle == []

    async def test_cancelled_call_opens_breaker(self):
        """A cancellation is a real outcome (e.g. our own timeout firing
        against a hanging server) and must still trip the breaker, or a
        hanging server would be redialed on every single request forever."""
        mgr = self._pooled_manager(pool_size=1)
        conn = _fake_connection(mgr)
        conn.session.call_tool = AsyncMock(side_effect=asyncio.CancelledError())

        async def build(server_config):
            return conn

        mgr._create_connection = build

        with pytest.raises(asyncio.CancelledError):
            await mgr._call_tool_on_server({"name": "srv"}, "t", {})

        assert not mgr.is_reachable("srv")
