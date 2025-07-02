"""Default configuration values for ORBIT CLI."""

from typing import Dict, Any

# Try to detect if keyring is available
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False


def get_default_config() -> Dict[str, Any]:
    """
    Get the default configuration dictionary.
    
    Returns:
        Dictionary containing default configuration values
    """
    return {
        "server": {
            "default_url": "http://localhost:3000",
            "timeout": 30,
            "retry_attempts": 3,
            "retry_delay": 2,  # seconds
            "retry_backoff": "exponential"  # exponential or linear
        },
        "auth": {
            "use_keyring": KEYRING_AVAILABLE,
            "credential_storage": "keyring" if KEYRING_AVAILABLE else "file",
            "fallback_token_file": "~/.orbit/.env",
            "session_duration_hours": 12,
            "auto_refresh_token": True,
            "token_refresh_threshold": 3600  # seconds before expiry
        },
        "output": {
            "format": "table",  # table, json, yaml
            "color": True,
            "verbose": False,
            "progress_bars": True,
            "timestamp_format": "%Y-%m-%d %H:%M:%S"
        },
        "history": {
            "enabled": True,
            "max_entries": 1000,
            "file": "~/.orbit/history.json"
        },
        "logging": {
            "level": "INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
            "file": "~/.orbit/logs/orbit.log",
            "max_file_size": 10485760,  # 10MB
            "backup_count": 5,
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "api": {
            "verify_ssl": True,
            "user_agent": "ORBIT-CLI",
            "max_retries": 3,
            "connection_pool_size": 10
        },
        "cache": {
            "enabled": True,
            "directory": "~/.orbit/cache",
            "ttl": 300,  # seconds
            "max_size": 104857600  # 100MB
        }
    }


# Configuration schema for validation
CONFIG_SCHEMA = {
    "server": {
        "default_url": {"type": "string", "pattern": r"^https?://"},
        "timeout": {"type": "integer", "min": 1, "max": 300},
        "retry_attempts": {"type": "integer", "min": 0, "max": 10},
        "retry_delay": {"type": "number", "min": 0, "max": 60},
        "retry_backoff": {"type": "string", "enum": ["exponential", "linear"]}
    },
    "auth": {
        "use_keyring": {"type": "boolean"},
        "credential_storage": {"type": "string", "enum": ["keyring", "file", "memory"]},
        "fallback_token_file": {"type": "string"},
        "session_duration_hours": {"type": "integer", "min": 1, "max": 720},
        "auto_refresh_token": {"type": "boolean"},
        "token_refresh_threshold": {"type": "integer", "min": 60, "max": 86400}
    },
    "output": {
        "format": {"type": "string", "enum": ["table", "json", "yaml"]},
        "color": {"type": "boolean"},
        "verbose": {"type": "boolean"},
        "progress_bars": {"type": "boolean"},
        "timestamp_format": {"type": "string"}
    },
    "history": {
        "enabled": {"type": "boolean"},
        "max_entries": {"type": "integer", "min": 0, "max": 10000},
        "file": {"type": "string"}
    },
    "logging": {
        "level": {"type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
        "file": {"type": "string"},
        "max_file_size": {"type": "integer", "min": 1024},
        "backup_count": {"type": "integer", "min": 0, "max": 100},
        "format": {"type": "string"}
    },
    "api": {
        "verify_ssl": {"type": "boolean"},
        "user_agent": {"type": "string"},
        "max_retries": {"type": "integer", "min": 0, "max": 10},
        "connection_pool_size": {"type": "integer", "min": 1, "max": 100}
    },
    "cache": {
        "enabled": {"type": "boolean"},
        "directory": {"type": "string"},
        "ttl": {"type": "integer", "min": 0},
        "max_size": {"type": "integer", "min": 0}
    }
}


# Environment variable mappings
ENV_VAR_MAPPINGS = {
    "ORBIT_SERVER_URL": "server.default_url",
    "ORBIT_SERVER_TIMEOUT": "server.timeout",
    "ORBIT_AUTH_STORAGE": "auth.credential_storage",
    "ORBIT_OUTPUT_FORMAT": "output.format",
    "ORBIT_NO_COLOR": "output.color",  # Note: inverted logic
    "ORBIT_VERBOSE": "output.verbose",
    "ORBIT_LOG_LEVEL": "logging.level",
    "ORBIT_CACHE_ENABLED": "cache.enabled",
    "ORBIT_CACHE_TTL": "cache.ttl"
}


# Configuration key aliases for backward compatibility
CONFIG_ALIASES = {
    "server.url": "server.default_url",
    "auth.keyring": "auth.use_keyring",
    "output.colours": "output.color",  # British spelling
    "output.colors": "output.color",   # American spelling
}


def get_config_value_type(key: str) -> str:
    """
    Get the expected type for a configuration key.
    
    Args:
        key: Configuration key in dot notation
        
    Returns:
        Type string ("string", "integer", "boolean", "number")
    """
    parts = key.split('.')
    schema = CONFIG_SCHEMA
    
    for part in parts[:-1]:
        if part in schema:
            schema = schema[part]
        else:
            return "string"  # Default type
    
    last_part = parts[-1]
    if last_part in schema and "type" in schema[last_part]:
        return schema[last_part]["type"]
    
    return "string"  # Default type


def get_config_constraints(key: str) -> Dict[str, Any]:
    """
    Get validation constraints for a configuration key.
    
    Args:
        key: Configuration key in dot notation
        
    Returns:
        Dictionary of constraints for the key
    """
    parts = key.split('.')
    schema = CONFIG_SCHEMA
    
    for part in parts[:-1]:
        if part in schema:
            schema = schema[part]
        else:
            return {}
    
    last_part = parts[-1]
    if last_part in schema:
        return schema[last_part]
    
    return {}