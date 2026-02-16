"""
CLI-local configuration service.

This service manages only CLI-specific settings. Server configuration
must be managed through the server API endpoints.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from bin.orbit.utils.exceptions import ConfigurationError

# Secure credential storage
try:
    import keyring  # noqa: F401
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

# Global configuration paths
DEFAULT_CONFIG_DIR = Path.home() / ".orbit"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_ENV_FILE = DEFAULT_CONFIG_DIR / ".env"  # Kept for backward compatibility
DEFAULT_LOG_DIR = DEFAULT_CONFIG_DIR / "logs"


class ConfigService:
    """
    Manages CLI-local configuration only.
    
    This service handles only CLI-specific settings like:
    - Server connection URL (for CLI to connect to server)
    - Request timeout and retry settings
    - Output formatting preferences
    - Authentication storage method
    
    Server configuration (port, host, adapters, etc.) must be managed
    through the server API endpoints.
    """
    
    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR):
        self.config_dir = config_dir
        self.config_file = config_dir / "config.json"
        self._config_cache = None
        self._last_config_load = 0
        self._config_cache_ttl = 60  # Cache for 60 seconds
        self.ensure_config_dir()
    
    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists with proper permissions."""
        self.config_dir.mkdir(exist_ok=True, mode=0o700)
        DEFAULT_LOG_DIR.mkdir(exist_ok=True, mode=0o700)
    
    def load_config(self) -> Dict[str, Any]:
        """Load CLI configuration from file with caching."""
        current_time = time.time()
        
        # Return cached config if still valid
        if (self._config_cache is not None and 
            current_time - self._last_config_load < self._config_cache_ttl):
            return self._config_cache
        
        if not self.config_file.exists():
            config = self.get_default_config()
        else:
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Invalid configuration file: {e}")
            except Exception as e:
                raise ConfigurationError(f"Failed to load configuration: {e}")
        
        self._config_cache = config
        self._last_config_load = current_time
        return config
    
    def save_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to file and invalidate cache."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            self.config_file.chmod(0o600)
            # Invalidate cache
            self._config_cache = None
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """Get default CLI configuration."""
        return {
            "server": {
                "default_url": "http://localhost:3000",
                "timeout": 30,
                "retry_attempts": 3
            },
            "auth": {
                "use_keyring": KEYRING_AVAILABLE,
                "fallback_token_file": str(DEFAULT_ENV_FILE),
                "session_duration_hours": 12,
                "credential_storage": "keyring" if KEYRING_AVAILABLE else "file"
            },
            "output": {
                "format": "table",  # table, json
                "color": True,
                "verbose": False
            },
            "history": {
                "enabled": True,
                "max_entries": 1000
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Configuration key in dot notation (e.g., "server.timeout")
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        config = self.load_config()
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-notation key."""
        config = self.load_config()
        keys = key.split('.')
        target = config
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
        self.save_config(config)
    
    def invalidate_cache(self) -> None:
        """Invalidate configuration cache."""
        self._config_cache = None
    
    def get_auth_storage_method(self) -> str:
        """Get the authentication storage method."""
        storage_method = self.get('auth.credential_storage')
        if storage_method:
            return storage_method
        
        # Final fallback
        return 'keyring' if KEYRING_AVAILABLE else 'file'
    
    def get_server_url(self, override_url: Optional[str] = None) -> str:
        """Get server URL for CLI connections."""
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

