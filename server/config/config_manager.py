"""
Configuration management for the chat application
"""

import os
import copy
import re
import yaml
import logging
import threading
from typing import Dict, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

_config: Optional[Dict[str, Any]] = None
_config_lock = threading.Lock()
_reload_lock = threading.Lock()
_resolved_presets: Dict[str, str] = {}
_import_cache: Dict[str, Tuple[int, Dict[str, Any]]] = {}
_ENV_VAR_RE = re.compile(r'\$\{([^}]+)\}')


def load_config(config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load configuration from shared config.yaml file"""
    global _config
    with _config_lock:
        if _config is None:
            _config = _load_config_from_disk(config_path)
        return _config


def clear_config_cache() -> None:
    """Clear the module-level loaded config singleton."""
    global _config
    with _config_lock:
        _config = None
        _resolved_presets.clear()
        # Also drop parsed imports. A parent import (e.g. adapters.yaml) caches its
        # fully-merged subtree keyed by its own mtime, so editing a nested import
        # (e.g. adapters/multimodal.yaml) would otherwise be masked by the unchanged
        # parent's cache entry.
        _import_cache.clear()


def _load_config_from_disk(config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load and validate configuration from disk without using cached state."""
    config_paths = [
        config_path, 
        '../config/config.yaml',
        '../../config/config.yaml',
        'config.yaml',
    ]
    
    # Filter out None values
    config_paths = [p for p in config_paths if p is not None]
    
    for path in config_paths:
        try:
            with open(path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Successfully loaded configuration from {os.path.abspath(path)}")

                # Process imports (like adapters.yaml)
                config = _process_imports(config, os.path.dirname(path))

                # Process environment variables
                config = _process_env_vars(config)

                # Fail fast if required secrets are absent
                _validate_required_config(config)

                # Resolve preset references (must be after imports and env vars)
                config = _resolve_ollama_presets(config)
                config = _resolve_llama_cpp_presets(config)
                return config
        except FileNotFoundError:
            logger.debug(f"Config file not found at {os.path.abspath(path)}")
            continue
        except Exception as e:
            logger.error(f"Error loading config from {os.path.abspath(path)}: {str(e)}")
            raise


def _mask_url(url: str) -> str:
    """Mask sensitive parts of URLs like credentials and token query params."""
    if not url:
        return url

    try:
        if '@' in url and '//' in url:
            protocol, rest = url.split('//', 1)
            if '@' in rest:
                _, host_part = rest.split('@', 1)
                return f"{protocol}//[REDACTED]@{host_part}"

        sensitive_keys = ('key=', 'token=', 'api_key=', 'apikey=', 'password=')
        if '?' in url and any(key in url.lower() for key in sensitive_keys):
            base_url, query = url.split('?', 1)
            masked_params = []

            for param in query.split('&'):
                param_lower = param.lower()
                if any(key in param_lower for key in sensitive_keys):
                    param_name = param.split('=')[0]
                    masked_params.append(f"{param_name}=[REDACTED]")
                else:
                    masked_params.append(param)

            return f"{base_url}?{'&'.join(masked_params)}"

        return url
    except Exception:
        return url.split('//')[0] + '//[HOST_REDACTED]' if '//' in url else '[URL_REDACTED]'


def _process_imports(config: Dict[str, Any], config_dir: str) -> Dict[str, Any]:
    """Process import statements in config (e.g., import: adapters.yaml)"""
    if not isinstance(config, dict):
        return config
    
    # Collect all import statements (handle multiple import keys)
    import_files = []
    keys_to_remove = []
    
    for key, value in config.items():
        if key == 'import':
            if isinstance(value, str):
                import_files.append(value)
            elif isinstance(value, list):
                import_files.extend(value)
            keys_to_remove.append(key)
    
    logger.debug(f"Found import files: {import_files}")
    
    # Remove all import keys from config
    for key in keys_to_remove:
        del config[key]
    
    # Load and merge each imported file
    real_config_dir = os.path.realpath(config_dir)
    for import_file in import_files:
        import_path = os.path.join(config_dir, import_file)
        real_import_path = os.path.realpath(import_path)
        if not os.path.commonpath([real_import_path, real_config_dir]) == real_config_dir:
            logger.warning(f"Skipping import '{import_file}': path escapes config directory")
            continue
        try:
            imported_config = _load_imported_config(import_path, config_dir)
            config = _merge_configs(config, imported_config)
                
        except FileNotFoundError:
            logger.warning(f"Import file not found: {os.path.abspath(import_path)}")
        except Exception as e:
            logger.warning(f"Error loading import file {os.path.abspath(import_path)}: {str(e)}")
    
    # Recursively process nested dictionaries
    for key, value in config.items():
        if isinstance(value, dict):
            config[key] = _process_imports(value, config_dir)
        elif isinstance(value, list):
            config[key] = [_process_imports(item, config_dir) if isinstance(item, dict) else item for item in value]
    
    return config


def _load_imported_config(import_path: str, config_dir: str) -> Dict[str, Any]:
    """Load an imported YAML file, reusing unchanged parsed imports by mtime."""
    real_import_path = os.path.realpath(import_path)
    mtime = os.stat(real_import_path).st_mtime_ns
    cached = _import_cache.get(real_import_path)

    if cached and cached[0] == mtime:
        logger.debug(f"Using cached imported configuration from {os.path.abspath(import_path)}")
        return copy.deepcopy(cached[1])

    with open(import_path, 'r') as file:
        imported_config = yaml.safe_load(file)
        logger.debug(f"Successfully imported configuration from {os.path.abspath(import_path)}")

    imported_config = _process_imports(imported_config, os.path.dirname(real_import_path))
    _import_cache[real_import_path] = (mtime, copy.deepcopy(imported_config))
    return imported_config


def _merge_configs(main_config: Dict[str, Any], imported_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge imported config into main config, with main config taking precedence"""
    result = main_config.copy()
    
    for key, value in imported_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = _merge_configs(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            # Concatenate lists (useful for merging adapters from multiple files)
            result[key] = result[key] + value
        elif key not in result:
            # Add new keys from imported config
            result[key] = value
        # If key exists in both and types don't match, main config takes precedence (already handled by copy())
    
    return result


# Config paths that must be non-empty after env-var substitution.
# Tuple of keys forming the dot-path into the config dict.
_REQUIRED_CONFIG_PATHS = [
    ('auth', 'default_admin_password'),
]


def _validate_required_config(config: Dict[str, Any]) -> None:
    """Raise RuntimeError if any required config value resolved to an empty string."""
    required_paths = list(_REQUIRED_CONFIG_PATHS)
    internal_services = config.get('internal_services', {})
    backend_type = internal_services.get('backend', {}).get('type')
    audit_backend = internal_services.get('audit', {}).get('storage_backend')

    if backend_type == 'mongodb' or audit_backend == 'mongodb':
        required_paths.extend([
            ('internal_services', 'mongodb', 'host'),
            ('internal_services', 'mongodb', 'username'),
            ('internal_services', 'mongodb', 'password'),
            ('internal_services', 'mongodb', 'database'),
        ])

    elasticsearch_config = internal_services.get('elasticsearch', {})
    if elasticsearch_config.get('enabled') or audit_backend == 'elasticsearch':
        required_paths.extend([
            ('internal_services', 'elasticsearch', 'node'),
            ('internal_services', 'elasticsearch', 'username'),
            ('internal_services', 'elasticsearch', 'password'),
        ])

    redis_config = internal_services.get('redis', {})
    if redis_config.get('enabled'):
        required_paths.extend([
            ('internal_services', 'redis', 'host'),
            ('internal_services', 'redis', 'port'),
            ('internal_services', 'redis', 'password'),
        ])

    for path in required_paths:
        value = config
        for key in path:
            value = value.get(key, '') if isinstance(value, dict) else ''
        if not value:
            dotted = '.'.join(path)
            raise RuntimeError(
                f"Required configuration value '{dotted}' is missing or empty. "
                f"Set the corresponding environment variable before starting the server."
            )

    _validate_cors_config(config)


def _validate_cors_config(config: Dict[str, Any]) -> None:
    """Validate CORS combinations that Starlette rejects at request time."""
    cors = config.get('security', {}).get('cors', {})
    if cors.get('allow_credentials') and '*' in cors.get('allowed_origins', []):
        raise RuntimeError(
            "security.cors: allow_credentials cannot be true when allowed_origins contains '*'. "
            "Specify explicit origins or disable allow_credentials."
        )


def _process_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process environment variables in config values

    Supports two formats:
    - ${ENV_VAR_NAME} - Required variable, logs warning if not found
    - ${ENV_VAR_NAME:-default} - Optional variable with default value
    """
    def replace_env_vars(value):
        if not isinstance(value, str):
            return value

        def _sub(match):
            inner = match.group(1)

            if ':-' in inner:
                env_var_name, default_value = inner.split(':-', 1)
                env_value = os.environ.get(env_var_name)
                if env_value is not None and env_value != "":
                    return env_value
                return default_value

            env_value = os.environ.get(inner)
            if env_value is not None:
                return env_value

            logger.warning(f"Environment variable {inner} not found")
            return ""

        if '${' in value:
            return _ENV_VAR_RE.sub(_sub, value)
        return value

    # Recursively process the config
    def process_dict(d):
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                result[k] = process_dict(v)
            elif isinstance(v, list):
                result[k] = [process_dict(item) if isinstance(item, dict) else replace_env_vars(item) for item in v]
            else:
                result[k] = replace_env_vars(v)
        return result

    return process_dict(config)


def reload_adapters_config(config_path: str) -> Dict[str, Any]:
    """
    Reload the FULL configuration including adapters and all dependencies.

    This function is used by the adapter hot-reload functionality to get
    fresh configurations. It reloads the entire config.yaml (which includes
    all imports like adapters.yaml, inference.yaml, embeddings.yaml, etc.)
    to ensure that adapter changes can reference updated provider configurations.

    CRITICAL: This must reload the full config so that inference/embedding/vision
    provider configurations are available when adapters are reloaded. Otherwise,
    adapters using different providers (e.g., ollama vs ollama_cloud) will fail
    because the provider endpoint configurations won't be present.

    Args:
        config_path: Path to the main config.yaml file

    Returns:
        The fully reloaded configuration dictionary with all sections

    Raises:
        FileNotFoundError: If config file not found
        Exception: If there are errors loading or processing the config
    """
    with _reload_lock:
        try:
            config = reload_config(config_path)

            logger.info(f"Reloaded FULL configuration from {os.path.abspath(config_path)} (includes all provider configs)")

            return config

        except FileNotFoundError:
            logger.error(f"Configuration file not found: {os.path.abspath(config_path)}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            raise


def reload_config(config_path: str) -> Optional[Dict[str, Any]]:
    """Reload the singleton config from disk atomically."""
    global _config
    with _config_lock:
        _resolved_presets.clear()
        # A reload must reflect on-disk changes, including edits to nested imports
        # whose parent import file's mtime did not change. Drop the import cache so
        # every imported file is re-read and re-merged from disk.
        _import_cache.clear()
        _config = _load_config_from_disk(config_path)
        return _config


def _resolve_inference_preset(
    config: Dict[str, Any], provider_key: str, presets_key: str
) -> Dict[str, Any]:
    """
    Resolve a use_preset reference for an inference provider.

    Looks up config['inference'][provider_key]['use_preset'] in
    config[presets_key], replaces the provider block with the preset values,
    and preserves the 'enabled' flag. Preset metadata is tracked separately
    to avoid leaking loader internals into the public config dict.
    """
    inference_config = config.get('inference', {})
    provider_config = inference_config.get(provider_key, {})
    presets = config.get(presets_key, {})

    preset_name = provider_config.get('use_preset')
    if not preset_name:
        return config

    if preset_name not in presets:
        logger.error(
            f"Preset '{preset_name}' not found in {presets_key}. "
            f"Available presets: {list(presets.keys())}"
        )
        return config

    preset = presets[preset_name]
    if not isinstance(preset, dict):
        logger.error(f"Preset '{preset_name}' in {presets_key} is not a valid configuration dictionary")
        return config

    resolved = preset.copy()
    resolved['enabled'] = provider_config.get('enabled', True)
    resolved.pop('use_preset', None)

    config['inference'][provider_key] = resolved
    _resolved_presets[provider_key] = preset_name
    logger.info(f"Resolved {provider_key} configuration from preset '{preset_name}' (model={preset.get('model')})")
    return config


def was_resolved_from_preset(provider_key: str) -> Optional[str]:
    """Return the preset name used to resolve an inference provider, if any."""
    return _resolved_presets.get(provider_key)


def _resolve_ollama_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _resolve_inference_preset(config, 'ollama', 'ollama_presets')
    except Exception as e:
        logger.warning(f"Error resolving Ollama presets: {str(e)}")
        return config


def _resolve_llama_cpp_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _resolve_inference_preset(config, 'llama_cpp', 'llama_cpp_presets')
    except Exception as e:
        logger.warning(f"Error resolving llama.cpp presets: {str(e)}")
        return config
