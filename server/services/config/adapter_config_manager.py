"""
Adapter Configuration Manager for loading and managing adapter configurations.

Provides centralized configuration management for adapters.
"""

import logging
from typing import Any, Iterable, Optional

from adapters.capabilities import AdapterCapabilities
from services.provider_metadata import get_provider_context_window_info

from .config_change_detector import ConfigChangeDetector

logger = logging.getLogger(__name__)

# Config keys through which one adapter names another by name. These are resolved
# through the adapter manager at runtime, so a dangling name breaks the referring
# adapter rather than the deleted one (composite adapters fail to initialize,
# realtime adapters lose grounding). Skill lists are the third way and live under
# `capabilities`. Centralized here, not in the admin route layer, so a new
# reference-style field is a schema change in one place, not a second list a
# route has to remember to keep in sync.
ADAPTER_REF_LIST_KEYS = ("child_adapters",)
ADAPTER_REF_SCALAR_KEYS = ("grounding_adapter",)


def _adapter_reference_kinds(entry: dict[str, Any], name: str) -> list[str]:
    """Which of `entry`'s reference fields point at `name`."""
    kinds = []

    caps = entry.get("capabilities") or {}
    if name in (caps.get("available_skills") or []) or name in (caps.get("auto_routable_skills") or []):
        kinds.append("skills")

    config = entry.get("config") or {}
    if not isinstance(config, dict):
        return kinds
    for key in ADAPTER_REF_LIST_KEYS:
        if name in (config.get(key) or []):
            kinds.append(key)
    for key in ADAPTER_REF_SCALAR_KEYS:
        if config.get(key) == name:
            kinds.append(key)

    return kinds


def find_references(entries: Iterable[dict[str, Any]], name: str) -> list[tuple[str, str]]:
    """`(referring_adapter_name, kind)` for every entry in `entries` that
    references `name` — as a skill or as a runtime dependency. `name`'s own
    entry is excluded. `entries` is a list of raw adapter config dicts (the
    `adapters:` list from a config file, or `AdapterConfigManager.
    get_all_configs().values()`)."""
    referrers = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("name") == name:
            continue
        for kind in _adapter_reference_kinds(entry, name):
            referrers.append((entry.get("name"), kind))
    return referrers


def _resolve_preset(provider: str, provider_config: dict[str, Any], global_config: dict[str, Any]) -> dict[str, Any]:
    """Merge preset values (e.g. llama_cpp use_preset) into provider_config, adapter/override keys winning."""
    use_preset = provider_config.get('use_preset')
    if not use_preset:
        return provider_config
    preset = global_config.get(f"{provider}_presets", {}).get(use_preset, {})
    if not preset:
        return provider_config
    return {**preset, **{k: v for k, v in provider_config.items() if k != 'use_preset'}}


def _effective_history_budget(
    provider_name: Optional[str],
    overrides: dict[str, Any],
    adapter_config: dict[str, Any],
    global_config: dict[str, Any],
) -> int:
    """
    Mirror ChatHistoryService._calculate_max_token_budget()'s reserved-token math,
    without instantiating ChatHistoryService (which would open a database
    connection) — used only to validate auto_model_selection's routing_tier
    entries at config-load time (see docs/adapters/auto-model-selection.md).

    Layering, matching the real request path (runtime > adapter > inference.yaml,
    same as DynamicAdapterManager.get_overridden_provider()): `overrides` (a
    routing_tier entry's own context_window/max_tokens, or {} for the adapter's
    own baseline) wins over `adapter_config`'s own settings, which win over the
    provider's inference.yaml/preset defaults.
    """
    provider_name = provider_name or adapter_config.get('inference_provider') or \
        global_config.get('general', {}).get('inference_provider', 'ollama')
    inference_config = dict(global_config.get('inference', {}).get(provider_name, {}))
    inference_config = _resolve_preset(provider_name, inference_config, global_config)

    provider_info = get_provider_context_window_info(provider_name)
    for source in (adapter_config, overrides):
        if source.get('context_window') is not None:
            inference_config['context_window'] = source['context_window']
            if provider_info.context_window_param != 'context_window':
                inference_config[provider_info.context_window_param] = source['context_window']
        if source.get('max_tokens') is not None:
            inference_config['max_tokens'] = source['max_tokens']

    context_window = (
        inference_config.get(provider_info.context_window_param)
        or inference_config.get('context_window')
        or inference_config.get('max_context_length')
        or inference_config.get('context_length')
        or provider_info.default_context_window
    )
    max_output_tokens = (
        inference_config.get('max_tokens')
        or inference_config.get('num_predict')
        or 1024
    )
    overhead_tokens = global_config.get('history', {}).get('system_overhead_tokens', 1200)
    return max(0, context_window - (max_output_tokens + overhead_tokens))


class AdapterConfigManager:
    """
    Manages adapter configurations.

    Responsibilities:
    - Load and validate adapter configurations
    - Track enabled/disabled adapters
    - Provide config comparison utilities
    - Detect configuration changes
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the adapter config manager.

        Args:
            config: Application configuration containing adapter configs
        """
        self.config = config
        self._adapter_configs: dict[str, dict[str, Any]] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load adapter configurations from config."""
        adapter_configs = self.config.get('adapters', [])

        enabled_count = 0
        disabled_count = 0

        for adapter_config in adapter_configs:
            adapter_name = adapter_config.get('name')
            if adapter_name:
                is_enabled = adapter_config.get('enabled', True)

                if is_enabled:
                    self._adapter_configs[adapter_name] = adapter_config
                    enabled_count += 1
                    inference_provider = adapter_config.get('inference_provider')
                    log_message = f"Loaded adapter config: {adapter_name} (enabled)"
                    if inference_provider:
                        log_message += f" with inference provider override: {inference_provider}"
                    logger.debug(log_message)
                else:
                    disabled_count += 1
                    logger.debug(f"Skipping disabled adapter: {adapter_name}")

        logger.debug(f"Loaded {enabled_count} enabled adapter configurations ({disabled_count} disabled)")

        self._validate_auto_model_selection(self._adapter_configs)

    def _validate_auto_model_selection(self, adapter_configs: dict[str, dict[str, Any]]) -> None:
        """
        Validate auto_model_selection's routing_tier invariants (see
        docs/adapters/auto-model-selection.md) for every adapter in
        `adapter_configs`, disabling the capability in place (never raising —
        auto_model_selection is an optional, best-effort feature) when:
          - two allowed_models entries share the same routing_tier, or
          - no allowed_models entry carries a routing_tier at all, or
          - a routing_tier entry's effective history budget is smaller than
            the adapter's own baseline (would overflow the selected model's
            real context window, since history is sized before routing runs).

        Called from both _load_configs() and reload_from_config() since they
        don't share a code path.
        """
        for adapter_name, adapter_config in adapter_configs.items():
            capabilities = adapter_config.get('capabilities') or {}
            auto_cfg = capabilities.get('auto_model_selection')
            if not auto_cfg or not auto_cfg.get('enabled'):
                continue

            allowed_models = adapter_config.get('allowed_models') or []
            tiered = [m for m in allowed_models if m.get('routing_tier')]

            seen_tiers: dict[str, str] = {}
            duplicate = None
            for entry in tiered:
                tier = entry['routing_tier']
                if tier in seen_tiers:
                    duplicate = tier
                    break
                seen_tiers[tier] = entry.get('name', '<unnamed>')

            if not tiered:
                logger.error(
                    f"Disabling auto_model_selection for adapter '{adapter_name}': "
                    f"no allowed_models entry declares a routing_tier"
                )
                auto_cfg['enabled'] = False
                continue

            if duplicate:
                logger.error(
                    f"Disabling auto_model_selection for adapter '{adapter_name}': "
                    f"more than one allowed_models entry declares routing_tier '{duplicate}'"
                )
                auto_cfg['enabled'] = False
                continue

            try:
                baseline = _effective_history_budget(None, {}, adapter_config, self.config)
                violation = next(
                    (
                        entry for entry in tiered
                        if _effective_history_budget(
                            entry.get('provider'), entry, adapter_config, self.config,
                        ) < baseline
                    ),
                    None,
                )
            except Exception as e:  # noqa: BLE001 - validation itself must never break adapter loading
                logger.warning(f"Could not validate auto_model_selection budget for '{adapter_name}': {e}")
                violation = None

            if violation:
                logger.error(
                    f"Disabling auto_model_selection for adapter '{adapter_name}': "
                    f"routing_tier '{violation.get('routing_tier')}' entry "
                    f"'{violation.get('name')}' has a smaller effective history budget "
                    f"than the adapter's own baseline — conversation history is fetched "
                    f"before routing runs, so this could overflow the selected model's "
                    f"real context window"
                )
                auto_cfg['enabled'] = False

    def get(self, adapter_name: str) -> Optional[dict[str, Any]]:
        """
        Get the configuration for a specific adapter.

        Args:
            adapter_name: The name of the adapter

        Returns:
            The adapter configuration dictionary or None if not found
        """
        return self._adapter_configs.get(adapter_name)

    def contains(self, adapter_name: str) -> bool:
        """
        Check if an adapter configuration exists.

        Args:
            adapter_name: The name of the adapter

        Returns:
            True if configuration exists, False otherwise
        """
        return adapter_name in self._adapter_configs

    def put(self, adapter_name: str, config: dict[str, Any]) -> None:
        """
        Set the configuration for an adapter.

        Args:
            adapter_name: The name of the adapter
            config: The adapter configuration
        """
        self._adapter_configs[adapter_name] = config

    def remove(self, adapter_name: str) -> Optional[dict[str, Any]]:
        """
        Remove an adapter configuration.

        Args:
            adapter_name: The name of the adapter

        Returns:
            The removed configuration or None if not found
        """
        return self._adapter_configs.pop(adapter_name, None)

    def get_available_adapters(self) -> list[str]:
        """
        Get list of available adapter names.

        Returns:
            List of adapter names that can be loaded
        """
        return list(self._adapter_configs.keys())

    def get_adapter_count(self) -> int:
        """
        Get the number of configured adapters.

        Returns:
            Number of configured adapters
        """
        return len(self._adapter_configs)

    def reload_from_config(self, new_config: dict[str, Any]) -> dict[str, list[str]]:
        """
        Reload configurations from new config and identify changes.

        Args:
            new_config: The new configuration dictionary

        Returns:
            Dictionary with lists of added, removed, and updated adapter names
        """
        # Update internal config reference
        self.config = new_config

        # Extract new adapter configs
        new_adapter_configs_list = new_config.get('adapters', [])
        new_adapter_configs = {}

        for adapter_config in new_adapter_configs_list:
            name = adapter_config.get('name')
            if name and adapter_config.get('enabled', True):
                new_adapter_configs[name] = adapter_config

        added = []
        removed = []
        updated = []
        unchanged = []

        # Find added and updated adapters
        for name, new_cfg in new_adapter_configs.items():
            if name not in self._adapter_configs:
                added.append(name)
            elif ConfigChangeDetector.configs_differ(self._adapter_configs[name], new_cfg):
                updated.append(name)
            else:
                unchanged.append(name)

        # Find removed adapters
        for name in list(self._adapter_configs.keys()):
            if name not in new_adapter_configs:
                removed.append(name)

        self._validate_auto_model_selection(new_adapter_configs)

        # Update the internal config store
        self._adapter_configs = new_adapter_configs

        logger.info(
            f"Config reload: {len(added)} added, {len(removed)} removed, "
            f"{len(updated)} updated, {len(unchanged)} unchanged"
        )

        return {
            'added': added,
            'removed': removed,
            'updated': updated,
            'unchanged': unchanged
        }

    def get_all_configs(self) -> dict[str, dict[str, Any]]:
        """
        Get all adapter configurations.

        Returns:
            Dictionary of all adapter configurations
        """
        return self._adapter_configs.copy()

    def get_skill_adapter(self, skill_name: str) -> Optional[str]:
        """Return the adapter_name whose skill_name matches, or None."""
        for name, cfg in self._adapter_configs.items():
            caps = AdapterCapabilities.from_config(cfg)
            if caps.expose_as_skill and caps.skill_name == skill_name:
                return name
        return None

    def get_all_skills(self) -> list[dict[str, Any]]:
        """Return metadata for all adapters marked as skills."""
        skills = []
        for name, cfg in self._adapter_configs.items():
            caps = AdapterCapabilities.from_config(cfg)
            if not caps.expose_as_skill:
                continue
            skills.append({
                'name': caps.skill_name or name,
                'description': caps.skill_description or '',
                'adapter_name': name,
                'enabled': cfg.get('enabled', True),
            })
        return skills

    def find_adapter_in_config_list(
        self,
        adapter_name: str,
        config_list: list[dict[str, Any]]
    ) -> Optional[dict[str, Any]]:
        """
        Find an adapter configuration in a list of configs.

        Args:
            adapter_name: Name of the adapter to find
            config_list: List of adapter configurations

        Returns:
            The adapter configuration or None if not found
        """
        for adapter_config in config_list:
            if adapter_config.get('name') == adapter_name:
                return adapter_config
        return None
