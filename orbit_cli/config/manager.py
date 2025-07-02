"""Enhanced ConfigManager that integrates with defaults and validation.

This is an example of how to update your existing ConfigManager to use
the new defaults and validation utilities.
"""

import json
import time
import os
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

from ..core.constants import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_FILE
from ..core.exceptions import ConfigurationError
from ..utils.logging import get_logger
from .defaults import get_default_config, get_config_value_type
from .validator import (
    ConfigValidator,
    ConfigMerger,
    ConfigPathResolver,
    normalize_config_key
)

logger = get_logger(__name__)


class ConfigManager:
    """Enhanced configuration manager with validation and multi-source support."""
    
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR):
        """
        Initialize the configuration manager.
        
        Args:
            config_dir: Configuration directory path
        """
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self._config_cache = None
        self._server_config_cache = None
        self._last_config_load = 0
        self._config_cache_ttl = 60  # Cache for 60 seconds
        self.ensure_config_dir()
    
    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists with proper permissions."""
        ConfigPathResolver.ensure_directory(self.config_dir, mode=0o700)
        ConfigPathResolver.ensure_directory(self.config_dir / "logs", mode=0o700)
    
    def load_config(self, validate: bool = True) -> Dict[str, Any]:
        """
        Load configuration from file with caching and validation.
        
        Args:
            validate: Whether to validate the configuration
            
        Returns:
            Loaded configuration dictionary
            
        Raises:
            ConfigurationError: If configuration is invalid
        """
        current_time = time.time()
        
        # Return cached config if still valid
        if (self._config_cache is not None and 
            current_time - self._last_config_load < self._config_cache_ttl):
            return self._config_cache
        
        # Get default config
        default_config = get_default_config()
        
        # Load user config if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid configuration file: {e}")
            except Exception as e:
                raise ConfigurationError(f"Failed to load configuration: {e}")
        else:
            user_config = {}
        
        # Merge configurations
        config = ConfigMerger.merge_configs(default_config, user_config)
        
        # Apply environment overrides
        config = ConfigMerger.apply_environment_overrides(config)
        
        # Resolve paths
        config = ConfigPathResolver.resolve_config_paths(config)
        
        # Validate if requested
        if validate:
            errors = ConfigValidator.validate_config(config)
            if errors:
                raise ConfigurationError(
                    f"Configuration validation failed:\n" + "\n".join(errors)
                )
        
        self._config_cache = config
        self._last_config_load = current_time
        return config
    
    def save_config(self, config: Dict[str, Any], validate: bool = True) -> None:
        """
        Save configuration to file with validation.
        
        Args:
            config: Configuration dictionary to save
            validate: Whether to validate before saving
            
        Raises:
            ConfigurationError: If configuration is invalid or save fails
        """
        if validate:
            errors = ConfigValidator.validate_config(config)
            if errors:
                raise ConfigurationError(
                    f"Cannot save invalid configuration:\n" + "\n".join(errors)
                )
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config_file.chmod(0o600)
            # Invalidate cache
            self._config_cache = None
            logger.info("Configuration saved successfully")
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Configuration key in dot notation
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        # Normalize the key
        key = normalize_config_key(key)
        
        config = self.load_config()
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any, save: bool = True) -> None:
        """
        Set configuration value by dot-notation key with validation.
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
            save: Whether to save immediately
            
        Raises:
            ValidationError: If value is invalid for the key
        """
        # Normalize the key
        key = normalize_config_key(key)
        
        # Validate the value
        is_valid, error = ConfigValidator.validate_value(key, value)
        if not is_valid:
            raise ConfigurationError(f"Invalid value for {key}: {error}")
        
        config = self.load_config()
        keys = key.split('.')
        target = config
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
        
        if save:
            self.save_config(config)
        else:
            # Just update cache
            self._config_cache = config
    
    def set_multiple(self, updates: Dict[str, Any], save: bool = True) -> None:
        """
        Set multiple configuration values at once.
        
        Args:
            updates: Dictionary of key-value pairs to update
            save: Whether to save immediately
        """
        for key, value in updates.items():
            self.set(key, value, save=False)
        
        if save:
            self.save_config(self._config_cache)
    
    def reset_to_defaults(self, keys: Optional[List[str]] = None) -> None:
        """
        Reset configuration to defaults.
        
        Args:
            keys: Optional list of keys to reset (None = reset all)
        """
        if keys is None:
            # Reset everything
            default_config = get_default_config()
            self.save_config(default_config)
        else:
            # Reset specific keys
            default_config = get_default_config()
            config = self.load_config()
            
            for key in keys:
                key = normalize_config_key(key)
                keys_parts = key.split('.')
                
                # Get default value
                default_value = default_config
                for part in keys_parts:
                    if isinstance(default_value, dict) and part in default_value:
                        default_value = default_value[part]
                    else:
                        logger.warning(f"No default value for key: {key}")
                        continue
                
                # Set in current config
                self.set(key, default_value, save=False)
            
            self.save_config(config)
    
    def export_config(self, path: Path, include_defaults: bool = False) -> None:
        """
        Export configuration to a file.
        
        Args:
            path: Path to export to
            include_defaults: Whether to include default values
        """
        config = self.load_config()
        
        if not include_defaults:
            # Remove values that match defaults
            default_config = get_default_config()
            config = self._remove_defaults(config, default_config)
        
        with open(path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Configuration exported to {path}")
    
    def import_config(self, path: Path, merge: bool = True) -> None:
        """
        Import configuration from a file.
        
        Args:
            path: Path to import from
            merge: Whether to merge with existing config or replace
        """
        try:
            with open(path, 'r') as f:
                imported_config = json.load(f)
        except Exception as e:
            raise ConfigurationError(f"Failed to import configuration: {e}")
        
        if merge:
            current_config = self.load_config()
            config = ConfigMerger.merge_configs(current_config, imported_config)
        else:
            config = imported_config
        
        self.save_config(config)
        logger.info(f"Configuration imported from {path}")
    
    def _remove_defaults(self, config: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """Remove values that match defaults from config."""
        result = {}
        
        for key, value in config.items():
            if key in defaults:
                if isinstance(value, dict) and isinstance(defaults[key], dict):
                    nested = self._remove_defaults(value, defaults[key])
                    if nested:  # Only include if non-empty
                        result[key] = nested
                elif value != defaults[key]:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def get_config_info(self) -> Dict[str, Any]:
        """
        Get information about the configuration.
        
        Returns:
            Dictionary with configuration metadata
        """
        config = self.load_config(validate=False)
        errors = ConfigValidator.validate_config(config)
        
        return {
            "config_file": str(self.config_file),
            "exists": self.config_file.exists(),
            "valid": len(errors) == 0,
            "errors": errors,
            "size": self.config_file.stat().st_size if self.config_file.exists() else 0,
            "modified": (
                self.config_file.stat().st_mtime 
                if self.config_file.exists() 
                else None
            )
        }
    
    def search_config(self, pattern: str) -> Dict[str, Any]:
        """
        Search configuration keys matching a pattern.
        
        Args:
            pattern: Search pattern (supports wildcards)
            
        Returns:
            Dictionary of matching keys and values
        """
        import fnmatch
        
        config = self.load_config()
        matches = {}
        
        def search_nested(data: Dict[str, Any], prefix: str = "") -> None:
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                
                if fnmatch.fnmatch(full_key, pattern):
                    matches[full_key] = value
                
                if isinstance(value, dict):
                    search_nested(value, full_key)
        
        search_nested(config)
        return matches
    
    # Convenience methods for backward compatibility
    def get_auth_storage_method(self) -> str:
        """Get the authentication storage method with proper fallback logic."""
        storage_method = self.get('auth.credential_storage')
        if storage_method:
            return storage_method
        
        # Final fallback
        try:
            import keyring
            return 'keyring' if keyring else 'file'
        except ImportError:
            return 'file'
    
    def get_server_url(self, override_url: Optional[str] = None) -> str:
        """Get server URL with proper precedence."""
        if override_url:
            return override_url.rstrip('/')
        
        url = self.get('server.default_url')
        if url:
            return url.rstrip('/')
        
        # Final fallback
        return "http://localhost:3000"
    
    def get_timeout(self) -> int:
        """Get request timeout."""
        return self.get('server.timeout', 30)
    
    def get_retry_attempts(self) -> int:
        """Get retry attempts."""
        return self.get('server.retry_attempts', 3)
    
    def get_output_format(self, override_format: Optional[str] = None) -> str:
        """Get output format."""
        return override_format or self.get('output.format', 'table')
    
    def get_use_color(self, override_color: Optional[bool] = None) -> bool:
        """Get color usage preference."""
        if override_color is not None:
            return override_color
        return self.get('output.color', True)
    
    def invalidate_cache(self) -> None:
        """Invalidate configuration cache."""
        self._config_cache = None
    
    def get_effective_config(self) -> Dict[str, Any]:
        """
        Get the effective configuration showing which values come from where.
        
        Returns:
            Dictionary with effective config and source information
        """
        config = self.load_config()
        
        effective_config = {
            "cli_config": config,
            "effective_values": {},
            "sources": {}
        }
        
        # Check all possible configuration keys from defaults
        from .defaults import get_default_config
        default_config = get_default_config()
        
        def collect_keys(data: Dict[str, Any], prefix: str = "") -> List[str]:
            keys = []
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.append(full_key)
                if isinstance(value, dict):
                    keys.extend(collect_keys(value, full_key))
            return keys
        
        all_keys = collect_keys(default_config)
        
        for key in all_keys:
            value = self.get(key)
            effective_config["effective_values"][key] = value
            
            # For now, all values come from the merged config
            # In the future, this could be enhanced to track sources
            effective_config["sources"][key] = "merged_config"
        
        return effective_config
    
    def _load_server_config(self) -> Optional[Dict[str, Any]]:
        """Load server configuration from config.yaml with caching."""
        current_time = time.time()
        
        # Return cached config if still valid
        if (self._server_config_cache is not None and 
            current_time - self._last_config_load < self._config_cache_ttl):
            return self._server_config_cache
        
        try:
            import yaml
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.yaml')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    server_config = yaml.safe_load(f)
                    self._server_config_cache = server_config
                    self._last_config_load = current_time
                    return server_config
        except Exception as e:
            logger.debug(f"Failed to read server config.yaml: {e}")
        
        return None
    
    def _get_server_config_value(self, key: str, default: Any = None) -> Any:
        """Get a value from server configuration with dot notation support."""
        server_config = self._load_server_config()
        if not server_config:
            return default
        
        keys = key.split('.')
        value = server_config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value