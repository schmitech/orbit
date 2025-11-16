"""
Configuration Change Detector for identifying differences between configurations.

Provides utilities for comparing configurations and identifying specific changes.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ConfigChangeDetector:
    """
    Detects and reports configuration changes.

    Responsibilities:
    - Compare old vs new configurations
    - Identify specific changes
    - Return structured change descriptions
    """

    # Key fields that affect caching and behavior
    KEY_FIELDS = [
        'inference_provider',
        'model',
        'embedding_provider',
        'reranker_provider',
        'vision_provider',
        'database',
        'enabled',
        'adapter',
        'datasource'
    ]

    @staticmethod
    def configs_differ(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> bool:
        """
        Compare configs reliably using JSON serialization.

        This ensures we catch all nested changes including deep dictionary differences.

        Args:
            old_config: The old configuration dictionary
            new_config: The new configuration dictionary

        Returns:
            True if configs differ, False if they are the same
        """
        try:
            old_json = json.dumps(old_config, sort_keys=True)
            new_json = json.dumps(new_config, sort_keys=True)
            return old_json != new_json
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize configs for comparison: {e}")
            return old_config != new_config

    @staticmethod
    def detect_changes(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> List[str]:
        """
        Detect what specific configuration values changed between old and new config.

        Args:
            old_config: The old configuration dictionary
            new_config: The new configuration dictionary

        Returns:
            List of change descriptions (e.g., ["inference_provider: ollama -> anthropic"])
        """
        changes = []

        # Check key fields
        for field in ConfigChangeDetector.KEY_FIELDS:
            old_val = old_config.get(field)
            new_val = new_config.get(field)

            if old_val != new_val:
                old_str = str(old_val) if old_val is not None else "None"
                new_str = str(new_val) if new_val is not None else "None"
                changes.append(f"{field}: {old_str} -> {new_str}")

        # Check nested config section
        old_nested = old_config.get('config', {})
        new_nested = new_config.get('config', {})

        if old_nested != new_nested:
            nested_changes = []
            all_keys = set(old_nested.keys()) | set(new_nested.keys())

            for key in all_keys:
                old_nested_val = old_nested.get(key)
                new_nested_val = new_nested.get(key)

                if old_nested_val != new_nested_val:
                    old_str = str(old_nested_val) if old_nested_val is not None else "None"
                    new_str = str(new_nested_val) if new_nested_val is not None else "None"
                    nested_changes.append(f"config.{key}: {old_str} -> {new_str}")

            if nested_changes:
                # Limit to first 3 nested changes to avoid log spam
                changes.extend(nested_changes[:3])
                if len(nested_changes) > 3:
                    changes.append(f"... and {len(nested_changes) - 3} more nested config changes")

        return changes

    @staticmethod
    def get_affected_services(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> Dict[str, bool]:
        """
        Determine which services are affected by the configuration change.

        Args:
            old_config: The old configuration dictionary
            new_config: The new configuration dictionary

        Returns:
            Dictionary indicating which services need to be reloaded
        """
        affected = {
            'provider': False,
            'embedding': False,
            'reranker': False,
            'adapter': False
        }

        # Check provider-related changes
        if (old_config.get('inference_provider') != new_config.get('inference_provider') or
            old_config.get('model') != new_config.get('model')):
            affected['provider'] = True
            affected['adapter'] = True

        # Check embedding-related changes
        if old_config.get('embedding_provider') != new_config.get('embedding_provider'):
            affected['embedding'] = True
            affected['adapter'] = True

        # Check reranker-related changes
        if old_config.get('reranker_provider') != new_config.get('reranker_provider'):
            affected['reranker'] = True
            affected['adapter'] = True

        # Check other adapter-affecting changes
        if (old_config.get('database') != new_config.get('database') or
            old_config.get('adapter') != new_config.get('adapter') or
            old_config.get('datasource') != new_config.get('datasource') or
            old_config.get('config', {}) != new_config.get('config', {})):
            affected['adapter'] = True

        return affected
