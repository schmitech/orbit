"""
Tests for decision service registration (ai_services.registry.register_decision_services)
and the DecisionCacheManager / DynamicAdapterManager lifecycle wiring.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from ai_services import registry  # noqa: E402
from ai_services.base import ServiceType  # noqa: E402
from services.dynamic_adapter_manager import DynamicAdapterManager  # noqa: E402


def _registered(config):
    with patch.object(registry.AIServiceFactory, "register_service") as register:
        registry.register_decision_services(config)
    return {call.args[1]: call.args[2] for call in register.call_args_list if call.args[0] == ServiceType.DECISION}


def _config(enabled=True, ollama=True, typesafe=True):
    return {
        "decision": {"enabled": enabled, "provider": "ollama"},
        "decision_models": {"ollama": {"enabled": ollama}, "typesafe": {"enabled": typesafe}},
    }


def test_registers_both_providers_when_enabled():
    registered = _registered(_config())
    assert registered["ollama"].__name__ == "OllamaDecisionService"
    assert registered["typesafe"].__name__ == "TypeSafeDecisionService"


def test_globally_disabled_registers_nothing():
    assert _registered(_config(enabled=False)) == {}


def test_disabled_provider_is_skipped():
    assert set(_registered(_config(typesafe=False))) == {"ollama"}


def test_missing_sdk_skips_typesafe_but_keeps_ollama(monkeypatch):
    package = "ai_services.implementations.decision"
    for name in list(sys.modules):
        if name.startswith(package):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "typesafe_sdk", None)  # makes `import typesafe_sdk` raise ImportError
    try:
        assert set(_registered(_config())) == {"ollama"}
    finally:
        monkeypatch.undo()
        importlib.import_module(package)


async def test_adapter_manager_close_closes_media_and_decision_caches():
    with patch.object(DynamicAdapterManager, "_init_cache_managers", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_config_manager", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_loader", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_reloader", lambda self: None), \
         patch("services.dynamic_adapter_manager.ThreadPoolExecutor", return_value=MagicMock()):
        manager = DynamicAdapterManager({})

    for name in ("provider_cache", "embedding_cache", "reranker_cache", "vision_cache", "audio_cache",
                 "image_cache", "video_cache", "decision_cache"):
        cache = MagicMock()
        cache.close = AsyncMock()
        setattr(manager, name, cache)
    manager.adapter_cache = MagicMock(clear=AsyncMock())
    manager._thread_pool = MagicMock()

    await manager.close()

    manager.image_cache.close.assert_awaited_once()
    manager.video_cache.close.assert_awaited_once()
    manager.decision_cache.close.assert_awaited_once()


async def test_get_decision_service_uses_decision_cache():
    with patch.object(DynamicAdapterManager, "_init_cache_managers", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_config_manager", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_loader", lambda self: None), \
         patch.object(DynamicAdapterManager, "_init_reloader", lambda self: None), \
         patch("services.dynamic_adapter_manager.ThreadPoolExecutor", return_value=MagicMock()):
        manager = DynamicAdapterManager({})
    service = object()
    manager.decision_cache = MagicMock(create_service=AsyncMock(return_value=service))

    assert await manager.get_decision_service("ollama", "ticket-triage") is service
    manager.decision_cache.create_service.assert_awaited_once_with("ollama", "ticket-triage")
