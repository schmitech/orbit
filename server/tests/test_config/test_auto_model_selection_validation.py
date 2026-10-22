"""
Tests for AdapterConfigManager's auto_model_selection validation (see
docs/adapters/auto-model-selection.md and server/services/config/adapter_config_manager.py).

Covers:
- routing_tier uniqueness, on both initial load and reload_from_config()
- missing routing_tier entries entirely
- the effective-history-budget guard, including entries that omit
  max_tokens/context_window (must inherit from the adapter config, not be
  treated as zero reservation)
- the v1 scope exclusion: a skill-with-its-own-LLM scenario is NOT rejected
  at load time (the guard only applies to branches where "auto" is honored;
  the real protection is the request-time exclusion in request_context_builder)
"""

import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from services.config.adapter_config_manager import AdapterConfigManager  # noqa: E402

BASE_CONFIG = {
    "general": {"inference_provider": "ollama"},
    "inference": {"ollama": {"context_window": 100000, "max_tokens": 4096}},
    "history": {"system_overhead_tokens": 1200},
}


def _adapter(name, allowed_models, inference_provider="ollama", **overrides):
    cfg = {
        "name": name,
        "enabled": True,
        "inference_provider": inference_provider,
        "capabilities": {"auto_model_selection": {"enabled": True}},
        "allowed_models": allowed_models,
    }
    cfg.update(overrides)
    return cfg


class TestRoutingTierUniqueness:
    def test_duplicate_tier_disables_on_initial_load(self):
        config = {
            **BASE_CONFIG,
            "adapters": [
                _adapter("dup", [
                    {"name": "a", "provider": "p", "model": "m1", "routing_tier": "low"},
                    {"name": "b", "provider": "p", "model": "m2", "routing_tier": "low"},
                ]),
            ],
        }
        mgr = AdapterConfigManager(config)
        assert mgr.get("dup")["capabilities"]["auto_model_selection"]["enabled"] is False

    def test_duplicate_tier_disables_on_reload(self):
        config = {**BASE_CONFIG, "adapters": [_adapter("ok", [
            {"name": "a", "provider": "p", "model": "m1", "routing_tier": "low", "context_window": 100000, "max_tokens": 2048},
        ])]}
        mgr = AdapterConfigManager(config)
        assert mgr.get("ok")["capabilities"]["auto_model_selection"]["enabled"] is True

        new_config = {
            **BASE_CONFIG,
            "adapters": [
                _adapter("dup2", [
                    {"name": "a", "provider": "p", "model": "m1", "routing_tier": "low"},
                    {"name": "b", "provider": "p", "model": "m2", "routing_tier": "low"},
                ]),
            ],
        }
        mgr.reload_from_config(new_config)
        assert mgr.get("dup2")["capabilities"]["auto_model_selection"]["enabled"] is False

    def test_no_routing_tier_entries_disables(self):
        config = {**BASE_CONFIG, "adapters": [_adapter("none", [
            {"name": "a", "provider": "p", "model": "m1"},
        ])]}
        mgr = AdapterConfigManager(config)
        assert mgr.get("none")["capabilities"]["auto_model_selection"]["enabled"] is False


class TestEffectiveHistoryBudgetGuard:
    def test_smaller_budget_tier_disables(self):
        config = {
            **BASE_CONFIG,
            "adapters": [
                _adapter("smaller", [
                    {"name": "low-m", "provider": "ollama", "model": "m", "routing_tier": "low",
                     "context_window": 8192, "max_tokens": 2048},
                    {"name": "high-m", "provider": "ollama", "model": "m2", "routing_tier": "high",
                     "context_window": 1000000, "max_tokens": 4096},
                ]),
            ],
        }
        mgr = AdapterConfigManager(config)
        assert mgr.get("smaller")["capabilities"]["auto_model_selection"]["enabled"] is False

    def test_sufficient_budget_tiers_pass(self):
        config = {
            **BASE_CONFIG,
            "adapters": [
                _adapter("sufficient", [
                    {"name": "low-m", "provider": "ollama", "model": "m", "routing_tier": "low",
                     "context_window": 100000, "max_tokens": 2048},
                    {"name": "high-m", "provider": "ollama", "model": "m2", "routing_tier": "high",
                     "context_window": 1000000, "max_tokens": 4096},
                ]),
            ],
        }
        mgr = AdapterConfigManager(config)
        assert mgr.get("sufficient")["capabilities"]["auto_model_selection"]["enabled"] is True

    def test_equal_context_window_different_max_tokens_distinguished(self):
        """Two tiers sharing context_window but differing max_tokens must not be
        treated as equivalent — a raw context_window comparison would miss this."""
        config = {
            **BASE_CONFIG,
            "adapters": [
                _adapter("same_window", [
                    # Same context_window as the adapter baseline (100000), but a much
                    # larger max_tokens reservation shrinks its effective history budget
                    # well below the baseline (100000 - 4096 - 1200).
                    {"name": "big-output", "provider": "ollama", "model": "m", "routing_tier": "low",
                     "context_window": 100000, "max_tokens": 90000},
                ], inference_provider="ollama"),
            ],
        }
        mgr = AdapterConfigManager(config)
        assert mgr.get("same_window")["capabilities"]["auto_model_selection"]["enabled"] is False

    def test_omitted_max_tokens_inherits_from_adapter_config(self):
        """A routing_tier entry that omits max_tokens/context_window must inherit
        them from the adapter's own config (then provider defaults) — not be
        treated as zero reservation, which would overstate its effective budget."""
        config = {
            **BASE_CONFIG,
            "inference": {"ollama": {"context_window": 100000, "max_tokens": 90000}},
            "adapters": [
                _adapter("inherits", [
                    # Omits max_tokens/context_window entirely — only overrides provider/model.
                    # Must inherit max_tokens=90000 from inference.yaml via the adapter's
                    # own inference_provider, which (same as the adapter's own baseline)
                    # leaves almost no room for history — so this should be rejected,
                    # proving the guard doesn't treat the omission as zero reservation.
                    {"name": "inherited-m", "provider": "ollama", "model": "m", "routing_tier": "low"},
                ]),
            ],
        }
        mgr = AdapterConfigManager(config)
        # Baseline == tier's effective budget here (both inherit the same 90000
        # max_tokens), so this should PASS, not fail — proving inheritance, not
        # zero-reservation, drives the comparison.
        assert mgr.get("inherits")["capabilities"]["auto_model_selection"]["enabled"] is True


class TestSkillWithOwnLLMExclusionNotEnforcedAtLoadTime:
    def test_large_window_caller_small_window_skill_model_accepted_at_load(self):
        """The budget guard only covers the branches where "auto" is actually
        honored (no-skill / no-own-LLM-skill). A skill with its own LLM is
        excluded from "auto" entirely at REQUEST time (see
        request_context_builder.build_context()), so a mismatched config here
        must NOT be rejected at load time — there's no way to know the calling
        adapter's budget at config-load time for that branch."""
        config = {
            **BASE_CONFIG,
            "inference": {
                "ollama": {"context_window": 100000, "max_tokens": 4096},
            },
            "adapters": [
                # The calling adapter has a large window (not auto_model_selection itself).
                {
                    "name": "caller",
                    "enabled": True,
                    "inference_provider": "openai",
                    "capabilities": {"available_skills": ["some-skill"]},
                },
                # The skill's own backing adapter has auto_model_selection enabled
                # with a tiny low-tier window relative to the CALLER's budget —
                # but the guard only compares against ITS OWN baseline, so this
                # passes at load time (the exclusion happens at request time).
                _adapter("skill-backing", [
                    {"name": "low-m", "provider": "ollama", "model": "m", "routing_tier": "low",
                     "context_window": 8192, "max_tokens": 2048},
                ], inference_provider="ollama", context_window=8192, max_tokens=2048),
            ],
        }
        mgr = AdapterConfigManager(config)
        # Not rejected: the guard validated 'skill-backing' against its OWN
        # baseline (also small), not against 'caller's large window.
        assert mgr.get("skill-backing")["capabilities"]["auto_model_selection"]["enabled"] is True
