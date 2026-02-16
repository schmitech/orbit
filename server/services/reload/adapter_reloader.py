"""
Adapter Reloader for orchestrating adapter reload process.

Coordinates the reload process with cache managers and config manager.
"""

import logging
from typing import Any, Dict

from ..config.config_change_detector import ConfigChangeDetector

logger = logging.getLogger(__name__)


class AdapterReloader:
    """
    Orchestrates adapter reload process.

    Responsibilities:
    - Coordinate adapter reload
    - Manage configuration updates
    - Handle error recovery
    - Track reload results
    """

    def __init__(
        self,
        config_manager,
        adapter_cache,
        adapter_loader,
        dependency_cleaner
    ):
        """
        Initialize the adapter reloader.

        Args:
            config_manager: Adapter configuration manager
            adapter_cache: Adapter cache manager
            adapter_loader: Adapter loader
            dependency_cleaner: Dependency cache cleaner
        """
        self.config_manager = config_manager
        self.adapter_cache = adapter_cache
        self.adapter_loader = adapter_loader
        self.dependency_cleaner = dependency_cleaner

    async def reload_single_adapter(
        self,
        adapter_name: str,
        new_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reload a single adapter configuration.

        Args:
            adapter_name: Name of the adapter to reload
            new_config: Full application configuration

        Returns:
            Result dictionary with action and details
        """
        # Extract adapter configs from new config
        new_adapter_configs_list = new_config.get('adapters', [])

        # Find the specific adapter config
        adapter_config_full = None
        for adapter_config in new_adapter_configs_list:
            if adapter_config.get('name') == adapter_name:
                adapter_config_full = adapter_config
                break

        if adapter_config_full is None:
            raise ValueError(f"Adapter '{adapter_name}' not found in configuration file")

        # Get old config
        old_config = self.config_manager.get(adapter_name)
        is_enabled = adapter_config_full.get('enabled', True)
        was_cached = self.adapter_cache.contains(adapter_name)

        # Handle getting old config for disabled adapters
        if not old_config and was_cached:
            cached_adapter = self.adapter_cache.get(adapter_name)
            if cached_adapter and hasattr(cached_adapter, '_adapter_config'):
                old_config = getattr(cached_adapter, '_adapter_config', None)

        if not old_config and self.config_manager.contains(adapter_name):
            old_config = self.config_manager.get(adapter_name)

        # Clear dependency caches before removing adapter
        if old_config:
            await self.dependency_cleaner.clear_adapter_dependencies(adapter_name, old_config)
        elif was_cached:
            await self.dependency_cleaner.clear_adapter_dependencies(adapter_name, adapter_config_full)

        # Remove from cache if it exists
        if self.adapter_cache.contains(adapter_name):
            await self.adapter_cache.remove(adapter_name)

        # Handle based on enabled status
        if is_enabled:
            # Determine action
            if was_cached and not old_config:
                action = "enabled"
            elif old_config and not old_config.get('enabled', True):
                action = "enabled"
            elif old_config:
                action = "updated"
            else:
                action = "added"

            # Update config
            self.config_manager.put(adapter_name, adapter_config_full)

            # Log changes if applicable
            if old_config and action in ["updated", "enabled"]:
                changes = ConfigChangeDetector.detect_changes(old_config, adapter_config_full)
                if changes:
                    logger.info(f"Adapter '{adapter_name}' config changes detected: {', '.join(changes)}")
                else:
                    logger.debug(f"Adapter '{adapter_name}' reloaded with no configuration changes detected")

            # Preload adapter
            try:
                if action in ["updated", "enabled", "added"]:
                    logger.info(f"Preloading adapter '{adapter_name}' to apply new configuration...")
                    adapter = await self.adapter_loader.load_adapter(adapter_name, adapter_config_full)
                    self.adapter_cache.put(adapter_name, adapter)
                    logger.info(f"Successfully preloaded adapter '{adapter_name}' with new configuration")
            except ValueError as e:
                error_msg = str(e)
                logger.error(f"Failed to preload adapter '{adapter_name}' after reload: {error_msg}")
            except Exception as e:
                logger.warning(f"Failed to preload adapter '{adapter_name}' after reload: {str(e)}. "
                             f"Adapter will be loaded lazily on next access. Error type: {type(e).__name__}")

            logger.info(f"Reloaded adapter '{adapter_name}' ({action})")

            return {
                "adapter_name": adapter_name,
                "action": action,
                "previous_config": old_config,
                "new_config": adapter_config_full
            }
        else:
            # Disable/remove the adapter
            self.config_manager.remove(adapter_name)
            action = "disabled"
            logger.info(f"Disabled adapter '{adapter_name}'")

            return {
                "adapter_name": adapter_name,
                "action": action,
                "previous_config": old_config,
                "new_config": None
            }

    async def reload_all_adapters(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reload all adapter configurations.

        Args:
            new_config: Full application configuration

        Returns:
            Summary dictionary with counts and lists of changes
        """
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
            old_config = self.config_manager.get(name)

            if not old_config:
                # New adapter
                added.append(name)
                self.config_manager.put(name, new_cfg)
                await self._preload_adapter_safe(name, new_cfg, "newly added")
            elif ConfigChangeDetector.configs_differ(old_config, new_cfg):
                # Updated adapter
                updated.append(name)

                # Log changes
                changes = ConfigChangeDetector.detect_changes(old_config, new_cfg)
                if changes:
                    logger.info(f"Adapter '{name}' config changes: {', '.join(changes)}")

                # Clear dependencies and remove from cache
                await self.dependency_cleaner.clear_adapter_dependencies(name, old_config)

                if self.adapter_cache.contains(name):
                    await self.adapter_cache.remove(name)

                # Update config
                self.config_manager.put(name, new_cfg)

                # Preload with new config
                await self._preload_adapter_safe(name, new_cfg, "updated")
            else:
                unchanged.append(name)

        # Find removed adapters
        for name in self.config_manager.get_available_adapters():
            if name not in new_adapter_configs:
                removed.append(name)

                # Clear dependencies
                old_config = self.config_manager.get(name)
                if old_config:
                    await self.dependency_cleaner.clear_adapter_dependencies(name, old_config)

                # Remove from cache
                if self.adapter_cache.contains(name):
                    await self.adapter_cache.remove(name)

                # Remove from configs
                self.config_manager.remove(name)

        total = self.config_manager.get_adapter_count()

        logger.info(
            f"Adapter reload complete: {len(added)} added, {len(removed)} removed, "
            f"{len(updated)} updated, {len(unchanged)} unchanged, {total} total"
        )

        return {
            "added": len(added),
            "removed": len(removed),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "total": total,
            "added_names": added,
            "removed_names": removed,
            "updated_names": updated
        }

    async def _preload_adapter_safe(
        self,
        adapter_name: str,
        adapter_config: Dict[str, Any],
        action_desc: str
    ) -> None:
        """
        Safely preload an adapter with error handling.

        Args:
            adapter_name: Name of the adapter
            adapter_config: Adapter configuration
            action_desc: Description of the action for logging
        """
        try:
            logger.debug(f"Preloading {action_desc} adapter '{adapter_name}'...")

            adapter = await self.adapter_loader.load_adapter(adapter_name, adapter_config)
            self.adapter_cache.put(adapter_name, adapter)

            logger.debug(f"Successfully preloaded {action_desc} adapter '{adapter_name}'")
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"Failed to preload {action_desc} adapter '{adapter_name}': {error_msg}")
        except Exception as e:
            logger.warning(f"Failed to preload {action_desc} adapter '{adapter_name}': {str(e)}. "
                          f"Adapter will be loaded lazily on next access. Error type: {type(e).__name__}")
