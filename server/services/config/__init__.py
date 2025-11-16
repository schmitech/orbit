"""
Configuration management components for the Dynamic Adapter Manager.

This package provides configuration management utilities:
- AdapterConfigManager: Loads and validates adapter configurations
- ConfigChangeDetector: Detects and reports configuration changes
"""

from .adapter_config_manager import AdapterConfigManager
from .config_change_detector import ConfigChangeDetector

__all__ = [
    "AdapterConfigManager",
    "ConfigChangeDetector",
]
