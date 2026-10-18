"""Tests for cross-worker reload propagation state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import adapter_reload_state


class TestAdapterConfigReloadPropagation:
    @pytest.mark.asyncio
    async def test_apply_adapter_reload_updates_app_state_config(self):
        """A sibling worker's propagated reload must refresh app_state.config too —
        not just the adapter manager — so request-time reads of app_state.config
        (e.g. the answer-options skill picker) see the applied config, not the
        stale snapshot from this worker's own startup or last local reload.
        """
        app_state = SimpleNamespace(
            config={"adapters": ["stale"]},
            config_path="config/config.yaml",
            adapter_manager=MagicMock(reload_adapter_configs=AsyncMock(return_value={"reloaded": 1})),
        )
        new_config = {"adapters": ["fresh"]}

        with patch(
            "config.config_manager.reload_adapters_config", return_value=new_config
        ), patch("services.mcp_auth_policy.apply_mcp_auth_policy") as apply_policy:
            assert await adapter_reload_state._apply_reload(app_state, "adapter_config")

        assert app_state.config == new_config
        app_state.adapter_manager.reload_adapter_configs.assert_awaited_once_with(new_config, None)
        apply_policy.assert_called_once_with(app_state, new_config)

    @pytest.mark.asyncio
    async def test_apply_adapter_reload_fails_without_adapter_manager(self):
        app_state = SimpleNamespace(config={"adapters": ["stale"]}, config_path="config/config.yaml",
                                     adapter_manager=None)
        assert not await adapter_reload_state._apply_reload(app_state, "adapter_config")
        assert app_state.config == {"adapters": ["stale"]}


class TestMcpReloadPropagation:
    @pytest.mark.asyncio
    async def test_apply_mcp_reload_rebuilds_manager_and_refreshes_tools(self):
        app_state = SimpleNamespace(
            config={"mcp_clients": {"enabled": True, "servers": []}},
            config_path="config/config.yaml",
        )
        new_mcp_config = {"enabled": True, "tool_timeout": 99, "servers": []}
        manager = MagicMock()
        manager.refresh_tool_cache = AsyncMock()

        with patch(
            "config.config_manager.reload_adapters_config",
            return_value={"mcp_clients": new_mcp_config, "adapters": ["unchanged"]},
        ), patch(
            "services.mcp_client_service.reload_mcp_client_manager",
            new=AsyncMock(return_value=manager),
        ) as reload_manager:
            assert await adapter_reload_state._apply_reload(app_state, "mcp_config")

        assert app_state.config == {"mcp_clients": new_mcp_config}
        reload_manager.assert_awaited_once_with(app_state.config)
        manager.refresh_tool_cache.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_apply_mcp_reload_succeeds_when_mcp_is_disabled(self):
        app_state = SimpleNamespace(config={}, config_path="config/config.yaml")

        with patch(
            "config.config_manager.reload_adapters_config",
            return_value={"mcp_clients": {"enabled": False}},
        ), patch(
            "services.mcp_client_service.reload_mcp_client_manager",
            new=AsyncMock(return_value=None),
        ) as reload_manager:
            assert await adapter_reload_state._apply_reload(app_state, "mcp_config")

        assert app_state.config["mcp_clients"] == {"enabled": False}
        reload_manager.assert_awaited_once_with(app_state.config)

    @pytest.mark.asyncio
    async def test_apply_mcp_reload_failure_is_reported_for_poll_retry(self):
        app_state = SimpleNamespace(config={}, config_path="config/config.yaml")

        with patch(
            "config.config_manager.reload_adapters_config",
            side_effect=RuntimeError("invalid config"),
        ):
            assert not await adapter_reload_state._apply_reload(app_state, "mcp_config")


class TestToolSkillsReloadPropagation:
    @pytest.mark.asyncio
    async def test_apply_tool_skills_reload_refreshes_registry(self):
        app_state = SimpleNamespace(config={"tool_skills": {}}, tool_skill_service=MagicMock())

        with patch(
            "services.tool_skill_service.refresh_tool_skill_registry_db",
            new=AsyncMock(),
        ) as refresh:
            assert await adapter_reload_state._apply_reload(app_state, "tool_skills")

        refresh.assert_awaited_once_with(app_state.config, app_state.tool_skill_service)

    @pytest.mark.asyncio
    async def test_apply_tool_skills_reload_fails_without_service(self):
        app_state = SimpleNamespace(config={}, tool_skill_service=None)
        assert not await adapter_reload_state._apply_reload(app_state, "tool_skills")

    def test_tool_skills_is_a_known_reload_kind(self):
        assert "tool_skills" in adapter_reload_state._KINDS
