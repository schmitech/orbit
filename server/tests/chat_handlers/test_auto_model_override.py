"""
Tests for resolve_runtime_model_override()'s handling of the reserved "auto"
model name (see docs/adapters/auto-model-selection.md).

"auto" must always resolve to a no-op override (None, None, None) and never
raise, regardless of whether auto_model_selection is enabled/present on the
adapter — the capability flag only controls whether ModelSelectionStep later
runs (via context.auto_select_requested), not whether "auto" is a valid
allowed_models value. Otherwise an adapter with auto_model_selection disabled
(e.g. by the config-load-time guard) or absent would reject model="auto"
instead of silently falling back to its default model.
"""

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from services.chat_handlers.request_context_builder import RequestContextBuilder  # noqa: E402


class _FakeAdapterManager:
    def __init__(self, configs):
        self.configs = configs

    def get_adapter_config(self, name):
        return self.configs.get(name)


def _builder(configs):
    return RequestContextBuilder(config={}, adapter_manager=_FakeAdapterManager(configs))


def test_auto_is_noop_when_capability_enabled():
    rcb = _builder({
        "adapter": {
            "allowed_models": [{"name": "m1", "provider": "p", "model": "m"}],
            "capabilities": {"auto_model_selection": {"enabled": True}},
        },
    })
    assert rcb.resolve_runtime_model_override("adapter", "auto") == (None, None, None)


def test_auto_is_noop_when_capability_disabled():
    rcb = _builder({
        "adapter": {
            "allowed_models": [{"name": "m1", "provider": "p", "model": "m"}],
            "capabilities": {"auto_model_selection": {"enabled": False}},
        },
    })
    assert rcb.resolve_runtime_model_override("adapter", "auto") == (None, None, None)


def test_auto_is_noop_when_capability_absent():
    rcb = _builder({
        "adapter": {
            "allowed_models": [{"name": "m1", "provider": "p", "model": "m"}],
            "capabilities": {},
        },
    })
    assert rcb.resolve_runtime_model_override("adapter", "auto") == (None, None, None)


def test_auto_is_noop_with_no_allowed_models_list():
    rcb = _builder({"adapter": {"capabilities": {}}})
    assert rcb.resolve_runtime_model_override("adapter", "auto") == (None, None, None)


def test_unrecognized_name_still_raises():
    """Only "auto" gets this leniency — a genuinely unknown name is still an error."""
    import pytest

    rcb = _builder({
        "adapter": {
            "allowed_models": [{"name": "m1", "provider": "p", "model": "m"}],
            "capabilities": {},
        },
    })
    with pytest.raises(ValueError):
        rcb.resolve_runtime_model_override("adapter", "not-a-real-model")
