"""Configuration validation utilities for ORBIT CLI."""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..core.exceptions import ConfigurationError, ValidationError
from .defaults import (
    get_config_value_type,
    get_config_constraints,
    CONFIG_ALIASES,
    ENV_VAR_MAPPINGS
)


class ConfigValidator:
    """Validates configuration values against schema."""
    
    @staticmethod
    def validate_value(key: str, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate a configuration value against its schema.
        
        Args:
            key: Configuration key in dot notation
            value: Value to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        expected_type = get_config_value_type(key)
        constraints = get_config_constraints(key)
        
        # Type validation
        if not ConfigValidator._check_type(value, expected_type):
            return False, f"Expected {expected_type}, got {type(value).__name__}"
        
        # Constraint validation
        if "enum" in constraints:
            if value not in constraints["enum"]:
                return False, f"Value must be one of: {', '.join(constraints['enum'])}"
        
        if "pattern" in constraints:
            if isinstance(value, str) and not re.match(constraints["pattern"], value):
                return False, f"Value does not match required pattern: {constraints['pattern']}"
        
        if "min" in constraints:
            if value < constraints["min"]:
                return False, f"Value must be at least {constraints['min']}"
        
        if "max" in constraints:
            if value > constraints["max"]:
                return False, f"Value must be at most {constraints['max']}"
        
        return True, None
    
    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """Check if a value matches the expected type."""
        type_map = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "number": (int, float)
        }
        
        expected = type_map.get(expected_type, str)
        return isinstance(value, expected)
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> List[str]:
        """
        Validate an entire configuration dictionary.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        def validate_nested(data: Dict[str, Any], prefix: str = "") -> None:
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                
                if isinstance(value, dict):
                    validate_nested(value, full_key)
                else:
                    is_valid, error = ConfigValidator.validate_value(full_key, value)
                    if not is_valid:
                        errors.append(f"{full_key}: {error}")
        
        validate_nested(config)
        return errors
    
    @staticmethod
    def coerce_value(value: str, target_type: str) -> Any:
        """
        Coerce a string value to the target type.
        
        Args:
            value: String value to coerce
            target_type: Target type name
            
        Returns:
            Coerced value
            
        Raises:
            ValidationError: If coercion fails
        """
        try:
            if target_type == "string":
                return value
            elif target_type == "integer":
                return int(value)
            elif target_type == "number":
                return float(value)
            elif target_type == "boolean":
                return ConfigValidator._parse_bool(value)
            else:
                return value
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Cannot convert '{value}' to {target_type}: {e}")
    
    @staticmethod
    def _parse_bool(value: Union[str, bool]) -> bool:
        """Parse a boolean value from string."""
        if isinstance(value, bool):
            return value
        
        value_lower = value.lower()
        if value_lower in ("true", "yes", "y", "1", "on"):
            return True
        elif value_lower in ("false", "no", "n", "0", "off"):
            return False
        else:
            raise ValueError(f"Cannot parse '{value}' as boolean")


class ConfigMerger:
    """Handles merging configurations from multiple sources."""
    
    @staticmethod
    def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge multiple configuration dictionaries.
        
        Later configs override earlier ones.
        
        Args:
            *configs: Configuration dictionaries to merge
            
        Returns:
            Merged configuration
        """
        result = {}
        
        for config in configs:
            ConfigMerger._deep_merge(result, config)
        
        return result
    
    @staticmethod
    def _deep_merge(target: Dict[str, Any], source: Dict[str, Any]) -> None:
        """Recursively merge source into target."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                ConfigMerger._deep_merge(target[key], value)
            else:
                target[key] = value
    
    @staticmethod
    def apply_environment_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment variable overrides to configuration.
        
        Args:
            config: Base configuration
            
        Returns:
            Configuration with environment overrides applied
        """
        result = config.copy()
        
        for env_var, config_key in ENV_VAR_MAPPINGS.items():
            if env_var in os.environ:
                value = os.environ[env_var]
                
                # Special handling for inverted logic
                if env_var == "ORBIT_NO_COLOR":
                    value = not ConfigValidator._parse_bool(value)
                else:
                    # Coerce to appropriate type
                    target_type = get_config_value_type(config_key)
                    value = ConfigValidator.coerce_value(value, target_type)
                
                # Set the value in the config
                ConfigMerger._set_nested_value(result, config_key, value)
        
        return result
    
    @staticmethod
    def _set_nested_value(data: Dict[str, Any], key: str, value: Any) -> None:
        """Set a value in a nested dictionary using dot notation."""
        parts = key.split('.')
        target = data
        
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        
        target[parts[-1]] = value


class ConfigPathResolver:
    """Resolves and expands configuration paths."""
    
    @staticmethod
    def resolve_path(path: str) -> Path:
        """
        Resolve a configuration path, expanding ~ and environment variables.
        
        Args:
            path: Path string to resolve
            
        Returns:
            Resolved Path object
        """
        # Expand user home directory
        path = os.path.expanduser(path)
        
        # Expand environment variables
        path = os.path.expandvars(path)
        
        # Convert to Path object and resolve
        return Path(path).resolve()
    
    @staticmethod
    def ensure_directory(path: Union[str, Path], mode: int = 0o700) -> Path:
        """
        Ensure a directory exists with proper permissions.
        
        Args:
            path: Directory path
            mode: Directory permissions (default: 0o700)
            
        Returns:
            Path object for the directory
        """
        path = ConfigPathResolver.resolve_path(str(path))
        path.mkdir(parents=True, exist_ok=True, mode=mode)
        return path
    
    @staticmethod
    def resolve_config_paths(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve all path values in a configuration dictionary.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Configuration with resolved paths
        """
        path_keys = [
            "auth.fallback_token_file",
            "history.file",
            "logging.file",
            "cache.directory"
        ]
        
        result = config.copy()
        
        for key in path_keys:
            parts = key.split('.')
            try:
                value = result
                for part in parts[:-1]:
                    value = value[part]
                
                if parts[-1] in value and isinstance(value[parts[-1]], str):
                    value[parts[-1]] = str(ConfigPathResolver.resolve_path(value[parts[-1]]))
            except KeyError:
                # Key doesn't exist in config, skip
                pass
        
        return result


def normalize_config_key(key: str) -> str:
    """
    Normalize a configuration key, handling aliases.
    
    Args:
        key: Configuration key
        
    Returns:
        Normalized key
    """
    return CONFIG_ALIASES.get(key, key)


def split_config_key(key: str) -> List[str]:
    """
    Split a configuration key into parts.
    
    Args:
        key: Configuration key in dot notation
        
    Returns:
        List of key parts
    """
    return key.split('.')


def join_config_key(*parts: str) -> str:
    """
    Join configuration key parts.
    
    Args:
        *parts: Key parts to join
        
    Returns:
        Joined key in dot notation
    """
    return '.'.join(parts)