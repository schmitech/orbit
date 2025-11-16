"""
Adapter Configuration Manager for loading and managing adapter configurations.

Provides centralized configuration management for adapters.
"""

import logging
from typing import Any, Dict, List, Optional

from .config_change_detector import ConfigChangeDetector

logger = logging.getLogger(__name__)


class AdapterConfigManager:
    """
    Manages adapter configurations.

    Responsibilities:
    - Load and validate adapter configurations
    - Track enabled/disabled adapters
    - Provide config comparison utilities
    - Detect configuration changes
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the adapter config manager.

        Args:
            config: Application configuration containing adapter configs
        """
        self.config = config
        self._adapter_configs: Dict[str, Dict[str, Any]] = {}
        self.verbose = config.get('general', {}).get('verbose', False)
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
                    if self.verbose:
                        inference_provider = adapter_config.get('inference_provider')
                        log_message = f"Loaded adapter config: {adapter_name} (enabled)"
                        if inference_provider:
                            log_message += f" with inference provider override: {inference_provider}"
                        logger.info(log_message)
                else:
                    disabled_count += 1
                    if self.verbose:
                        logger.info(f"Skipping disabled adapter: {adapter_name}")

        logger.info(f"Loaded {enabled_count} enabled adapter configurations ({disabled_count} disabled)")

    def get(self, adapter_name: str) -> Optional[Dict[str, Any]]:
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

    def put(self, adapter_name: str, config: Dict[str, Any]) -> None:
        """
        Set the configuration for an adapter.

        Args:
            adapter_name: The name of the adapter
            config: The adapter configuration
        """
        self._adapter_configs[adapter_name] = config

    def remove(self, adapter_name: str) -> Optional[Dict[str, Any]]:
        """
        Remove an adapter configuration.

        Args:
            adapter_name: The name of the adapter

        Returns:
            The removed configuration or None if not found
        """
        return self._adapter_configs.pop(adapter_name, None)

    def get_available_adapters(self) -> List[str]:
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

    def reload_from_config(self, new_config: Dict[str, Any]) -> Dict[str, List[str]]:
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

    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all adapter configurations.

        Returns:
            Dictionary of all adapter configurations
        """
        return self._adapter_configs.copy()

    def find_adapter_in_config_list(
        self,
        adapter_name: str,
        config_list: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
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
