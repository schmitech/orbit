"""
Unit tests for the MCP hot-reload wiring in admin_routes.py.

Verifies that _reload_mcp_clients rebuilds the MCPClientManager singleton from
the on-disk mcp_clients.yaml (via reload_adapters_config) and splices only the
mcp_clients key into the live app-state config, and that the PATCH endpoints
call it and report the outcome without ever raising.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import routes.admin_routes as admin_routes
import services.mcp_client_service as mcp_client_service


@pytest.fixture(autouse=True)
def _reset_mcp_singleton():
    mcp_client_service._instance = None
    yield
    mcp_client_service._instance = None


def _fake_request(config, config_path="config/config.yaml"):
    state = SimpleNamespace(config=config, config_path=config_path)
    return SimpleNamespace(app=SimpleNamespace(state=state))


class TestReloadMcpClients:
    @pytest.mark.asyncio
    async def test_reload_rebuilds_manager_and_splices_config(self):
        old_config = {"mcp_clients": {"enabled": True, "tool_timeout": 30, "servers": []}}
        request = _fake_request(old_config)

        old_manager = mcp_client_service.get_mcp_client_manager(old_config)
        assert old_manager is not None

        new_full_config = {
            "mcp_clients": {"enabled": True, "tool_timeout": 77, "servers": []},
            "adapters": [{"name": "unrelated"}],
        }
        with patch.object(admin_routes, "reload_adapters_config", return_value=new_full_config):
            summary = await admin_routes._reload_mcp_clients(request)

        assert summary["enabled"] is True
        # Only mcp_clients was spliced in — the rest of app.state.config is untouched.
        assert "adapters" not in request.app.state.config
        assert request.app.state.config["mcp_clients"]["tool_timeout"] == 77

        new_manager = mcp_client_service.get_mcp_client_manager(request.app.state.config)
        assert new_manager is not old_manager
        assert new_manager.setting("anything", "tool_timeout") == 77

    @pytest.mark.asyncio
    async def test_reload_disabling_clears_manager(self):
        config = {"mcp_clients": {"enabled": True, "servers": []}}
        request = _fake_request(config)
        assert mcp_client_service.get_mcp_client_manager(config) is not None

        disabled_config = {"mcp_clients": {"enabled": False}}
        with patch.object(admin_routes, "reload_adapters_config", return_value=disabled_config):
            summary = await admin_routes._reload_mcp_clients(request)

        assert summary == {"enabled": False, "servers": {}}
        assert mcp_client_service.get_mcp_client_manager(request.app.state.config) is None

    @pytest.mark.asyncio
    async def test_reload_missing_config_path_raises(self):
        request = _fake_request({}, config_path=None)
        with pytest.raises(RuntimeError):
            await admin_routes._reload_mcp_clients(request)

    @pytest.mark.asyncio
    async def test_reload_warms_discovery(self):
        config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [{"name": "srv", "transport": "stdio", "command": "x"}],
            },
        }
        request = _fake_request(config)
        with patch.object(admin_routes, "reload_adapters_config", return_value=config):
            with patch.object(
                mcp_client_service.MCPClientManager,
                "_list_tools_on_server",
                new=AsyncMock(return_value=[]),
            ):
                summary = await admin_routes._reload_mcp_clients(request)

        assert summary["enabled"] is True
        assert summary["servers"]["srv"]["reachable"] is True
        assert summary["servers"]["srv"]["tool_count"] == 0

    @pytest.mark.asyncio
    async def test_multi_worker_reload_bumps_mcp_generation_and_advances_local_baseline(self):
        config = {"mcp_clients": {"enabled": False}}
        request = _fake_request(config)
        request.app.state._adapter_reload_last_seen = {"mcp_config": 3}

        with patch.object(admin_routes, "reload_adapters_config", return_value=config), patch.dict(
            "os.environ", {"ORBIT_SUPERVISOR_PID": "123"}
        ), patch(
            "services.adapter_reload_state.bump_generation", new=AsyncMock(return_value=4)
        ) as bump_generation:
            await admin_routes._reload_mcp_clients(request)

        bump_generation.assert_awaited_once_with(request.app.state, "mcp_config")
        assert request.app.state._adapter_reload_last_seen["mcp_config"] == 4


class TestScopedReload:
    @pytest.mark.asyncio
    async def test_editing_one_server_does_not_redial_another(self):
        config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [
                    {"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 30},
                    {"name": "b", "transport": "stdio", "command": "y", "tool_timeout": 30},
                ],
            },
        }
        request = _fake_request(config)
        with patch.object(
            mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
        ):
            manager = mcp_client_service.get_mcp_client_manager(config)
            await manager.get_all_tools()
        assert set(manager._tools_cache) == {"a", "b"}

        new_config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [
                    {"name": "a", "transport": "stdio", "command": "x", "tool_timeout": 99},
                    {"name": "b", "transport": "stdio", "command": "y", "tool_timeout": 30},
                ],
            },
        }
        redial = AsyncMock(return_value=[])
        with patch.object(admin_routes, "reload_adapters_config", return_value=new_config):
            with patch.object(mcp_client_service.MCPClientManager, "_list_tools_on_server", new=redial):
                summary = await admin_routes._reload_mcp_clients(request, server_name="a")

        assert redial.await_count == 1
        assert redial.await_args.args[0]["name"] == "a"
        # Same manager instance reused — not rebuilt.
        assert mcp_client_service.get_current_mcp_client_manager() is manager
        assert manager.setting("a", "tool_timeout") == 99
        assert summary["servers"]["b"]["tool_count"] == 0  # untouched, still cached empty

    @pytest.mark.asyncio
    async def test_scoped_reload_removes_disabled_server(self):
        config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [{"name": "a", "transport": "stdio", "command": "x", "enabled": True}],
            },
        }
        request = _fake_request(config)
        with patch.object(
            mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
        ):
            manager = mcp_client_service.get_mcp_client_manager(config)
            await manager.get_all_tools()

        new_config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [{"name": "a", "transport": "stdio", "command": "x", "enabled": False}],
            },
        }
        with patch.object(admin_routes, "reload_adapters_config", return_value=new_config):
            summary = await admin_routes._reload_mcp_clients(request, server_name="a")

        assert "a" not in manager._server_configs
        assert "a" not in summary["servers"]

    @pytest.mark.asyncio
    async def test_no_existing_manager_falls_back_to_full_rebuild(self):
        config = {"mcp_clients": {"enabled": False}}
        request = _fake_request(config)
        new_config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [{"name": "a", "transport": "stdio", "command": "x"}],
            },
        }
        with patch.object(admin_routes, "reload_adapters_config", return_value=new_config):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                summary = await admin_routes._reload_mcp_clients(request, server_name="a")

        assert summary["enabled"] is True
        assert mcp_client_service.get_current_mcp_client_manager() is not None


class TestDiscoverMcpTools:
    @pytest.mark.asyncio
    async def test_does_not_reload_config_from_disk(self):
        """GET /mcp/tools must re-dial the live manager only — PATCH endpoints
        already apply config changes, so a disk reload here would rebuild the
        whole manager (and re-dial every server) on every 'Test connection'
        click, not just the server being tested."""
        config = {
            "mcp_clients": {
                "enabled": True,
                "servers": [{"name": "a", "transport": "stdio", "command": "x"}],
            },
        }
        request = _fake_request(config)
        with patch.object(
            mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
        ):
            manager = mcp_client_service.get_mcp_client_manager(config)

        reload_spy = AsyncMock()
        with patch.object(admin_routes, "_reload_mcp_clients", reload_spy):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.discover_mcp_tools(request)

        reload_spy.assert_not_awaited()
        assert result["available"] is True
        assert "a" in result["servers"]
        assert mcp_client_service.get_current_mcp_client_manager() is manager

    @pytest.mark.asyncio
    async def test_disabled_returns_unavailable_without_reload(self):
        config = {"mcp_clients": {"enabled": False}}
        request = _fake_request(config)
        reload_spy = AsyncMock()
        with patch.object(admin_routes, "_reload_mcp_clients", reload_spy):
            result = await admin_routes.discover_mcp_tools(request)

        assert result == {
            "available": False,
            "reason": "MCP is disabled. Set mcp_clients.enabled: true.",
            "servers": {},
        }
        reload_spy.assert_not_awaited()
