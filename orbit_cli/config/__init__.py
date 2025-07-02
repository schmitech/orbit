"""Configuration management for ORBIT CLI."""

from .manager import ConfigManager
from .defaults import (
    get_default_config,
    get_config_value_type,
    get_config_constraints,
    CONFIG_SCHEMA,
    ENV_VAR_MAPPINGS,
    CONFIG_ALIASES
)
from .validator import (
    ConfigValidator,
    ConfigMerger,
    ConfigPathResolver,
    normalize_config_key,
    split_config_key,
    join_config_key
)

__all__ = [
    # Main class
    'ConfigManager',
    
    # Defaults
    'get_default_config',
    'get_config_value_type',
    'get_config_constraints',
    'CONFIG_SCHEMA',
    'ENV_VAR_MAPPINGS',
    'CONFIG_ALIASES',
    
    # Validation
    'ConfigValidator',
    'ConfigMerger',
    'ConfigPathResolver',
    
    # Utilities
    'normalize_config_key',
    'split_config_key',
    'join_config_key'
]