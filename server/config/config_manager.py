"""
Configuration management for the chat application
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from functools import lru_cache
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_config(config_path: Optional[str] = None):
    """Load configuration from shared config.yaml file"""
    
    # Load environment variables first
    try:
        from dotenv import load_dotenv
        # Try to load .env from various possible locations
        import os
        from pathlib import Path
        
        # Get the current directory
        current_dir = Path.cwd()
        
        # Try different possible .env file locations
        env_paths = [
            current_dir / '.env',
            current_dir.parent / '.env',
            current_dir.parent.parent / '.env',
            Path('.env'),
        ]
        
        env_loaded = False
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path, override=True)
                logger.info(f"Loaded environment variables from: {env_path}")
                env_loaded = True
                break
        
        if not env_loaded:
            logger.warning("No .env file found in expected locations")
            
    except ImportError:
        logger.warning("python-dotenv not available, environment variables may not be loaded")
    except Exception as e:
        logger.warning(f"Error loading environment variables: {str(e)}")
    
    config_paths = [
        config_path, 
        '../config/config.yaml',
        '../../config/config.yaml',
        'config.yaml',
    ]
    
    # Filter out None values
    config_paths = [p for p in config_paths if p is not None]
    
    for config_path in config_paths:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Successfully loaded configuration from {os.path.abspath(config_path)}")
                
                # Process imports (like adapters.yaml)
                config = _process_imports(config, os.path.dirname(config_path))
                
                # Process environment variables
                config = _process_env_vars(config)

                # Resolve Ollama preset references (must be after imports and env vars)
                config = _resolve_ollama_presets(config)
                
                # Log key configuration values
                _log_config_summary(config, config_path)
                
                return config
        except FileNotFoundError:
            logger.debug(f"Config file not found at {os.path.abspath(config_path)}")
            continue
        except Exception as e:
            logger.warning(f"Error loading config from {os.path.abspath(config_path)}: {str(e)}")

def _log_config_summary(config: Dict[str, Any], source_path: str):
    """Log a summary of important config values with sensitive data masked"""
    logger.info(f"Configuration loaded from: {source_path}")
    
    # Get the active inference provider
    inference_provider = config.get('general', {}).get('inference_provider', 'ollama')
    
    # Only log the active inference provider settings
    if inference_provider == 'ollama':
        ollama_config = config.get('inference', {}).get('ollama', {})
        logger.info(f"Inference: {inference_provider} - model={ollama_config.get('model')}, base_url={_mask_url(ollama_config.get('base_url'))}")
    elif inference_provider == 'together':
        together_config = config.get('inference', {}).get('together', {})
        logger.info(f"Inference: {inference_provider} - model={together_config.get('model')}")
    elif inference_provider == 'xai':
        xai_config = config.get('inference', {}).get('xai', {})
        logger.info(f"Inference: {inference_provider} - model={xai_config.get('model')}")
    elif inference_provider == 'watson':
        watson_config = config.get('inference', {}).get('watson', {})
        logger.info(f"Inference: {inference_provider} - model={watson_config.get('model')}")
    elif inference_provider == 'openai':
        openai_config = config.get('inference', {}).get('openai', {})
        logger.info(f"Inference: {inference_provider} - model={openai_config.get('model')}")
    elif inference_provider == 'anthropic':
        anthropic_config = config.get('inference', {}).get('anthropic', {})
        logger.info(f"Inference: {inference_provider} - model={anthropic_config.get('model')}")
    else:
        logger.info(f"Inference: {inference_provider}")
    
    # Get language detection from new configuration structure
    lang_detect_config = config.get('language_detection', {})
    language_detection = lang_detect_config.get('enabled', False)

    logger.info(f"Language Detection: enabled={language_detection}")
    
    # Log fault tolerance configuration (always enabled)
    fault_tolerance_config = config.get('fault_tolerance', {})
    circuit_breaker_config = fault_tolerance_config.get('circuit_breaker', {})
    execution_config = fault_tolerance_config.get('execution', {})
    logger.info(f"Fault Tolerance: enabled - strategy={execution_config.get('strategy', 'all')}, "
               f"circuit_breaker_threshold={circuit_breaker_config.get('failure_threshold', 5)}, "
               f"timeout={execution_config.get('timeout', 35)}s")
    
    # Log performance configuration
    perf_config = config.get('performance', {})
    if perf_config:
        workers = perf_config.get('workers', 1)
        keep_alive = perf_config.get('keep_alive_timeout', 30)
        
        # Calculate total thread pool capacity
        thread_pools = perf_config.get('thread_pools', {})
        if thread_pools:
            total_workers = sum(thread_pools.values())
            pool_summary = ', '.join([f"{k.replace('_workers', '')}={v}" for k, v in thread_pools.items()])
            logger.info(f"Performance: workers={workers}, keep_alive={keep_alive}s, "
                       f"thread_pools=({pool_summary}), total_capacity={total_workers}")
        else:
            logger.info(f"Performance: workers={workers}, keep_alive={keep_alive}s, thread_pools=default")
    else:
        logger.info("Performance: using default configuration")
    
    # Log adapter configuration summary
    adapters_config = config.get('adapters', [])
    if adapters_config:
        enabled_adapters = [adapter for adapter in adapters_config if adapter.get('enabled', True)]
        disabled_adapters = [adapter for adapter in adapters_config if not adapter.get('enabled', True)]
        logger.info(f"Adapters: {len(enabled_adapters)} enabled, {len(disabled_adapters)} disabled")
        if disabled_adapters:
            disabled_names = [adapter.get('name', 'unnamed') for adapter in disabled_adapters]
            logger.info(f"Disabled adapters: {', '.join(disabled_names)}")
    
    # Log monitoring configuration
    monitoring_config = config.get('monitoring', {})
    if monitoring_config:
        monitoring_enabled = monitoring_config.get('enabled', True)
        metrics_config = monitoring_config.get('metrics', {})
        
        if monitoring_enabled:
            collection_interval = metrics_config.get('collection_interval', 5)
            time_window = metrics_config.get('time_window', 300)
            prometheus_enabled = metrics_config.get('prometheus', {}).get('enabled', True)
            dashboard_enabled = metrics_config.get('dashboard', {}).get('enabled', True)
            websocket_interval = metrics_config.get('dashboard', {}).get('websocket_update_interval', 5)
            
            features = []
            if prometheus_enabled:
                features.append("prometheus")
            if dashboard_enabled:
                features.append("dashboard")
            
            logger.info(f"Monitoring: enabled - features=({', '.join(features)}), "
                       f"collection_interval={collection_interval}s, time_window={time_window}s, "
                       f"websocket_update={websocket_interval}s")
            
            # Log alert thresholds if configured
            alerts_config = monitoring_config.get('alerts', {})
            if alerts_config:
                thresholds = []
                if 'cpu_threshold' in alerts_config:
                    thresholds.append(f"cpu={alerts_config['cpu_threshold']}%")
                if 'memory_threshold' in alerts_config:
                    thresholds.append(f"memory={alerts_config['memory_threshold']}%")
                if 'error_rate_threshold' in alerts_config:
                    thresholds.append(f"error_rate={alerts_config['error_rate_threshold']}%")
                if 'response_time_threshold' in alerts_config:
                    thresholds.append(f"response_time={alerts_config['response_time_threshold']}ms")
                
                if thresholds:
                    logger.info(f"Monitoring Alert Thresholds: {', '.join(thresholds)}")
        else:
            logger.info("Monitoring: disabled")
    else:
        logger.info("Monitoring: using default settings")


def _mask_url(url: str) -> str:
    """Mask sensitive parts of URLs like credentials"""
    if not url:
        return url
    
    try:
        # For URLs with credentials like https://user:pass@host.com
        if '@' in url and '//' in url:
            # Split by // to get the protocol and the rest
            protocol, rest = url.split('//', 1)
            # If there are credentials in the URL
            if '@' in rest:
                # Split by @ to separate credentials from host
                credentials_part, host_part = rest.split('@', 1)
                # Replace credentials with [REDACTED]
                return f"{protocol}//[REDACTED]@{host_part}"
        
        # For URLs with API keys like query parameters
        if '?' in url and ('key=' in url.lower() or 'token=' in url.lower() or 'api_key=' in url.lower() or 'apikey=' in url.lower()):
            # Simple pattern matching for common API key parameters
            # Split URL and query string
            base_url, query = url.split('?', 1)
            params = query.split('&')
            masked_params = []
            
            for param in params:
                param_lower = param.lower()
                if 'key=' in param_lower or 'token=' in param_lower or 'api_key=' in param_lower or 'apikey=' in param_lower or 'password=' in param_lower:
                    # Find the parameter name
                    param_name = param.split('=')[0]
                    masked_params.append(f"{param_name}=[REDACTED]")
                else:
                    masked_params.append(param)
            
            return f"{base_url}?{'&'.join(masked_params)}"
        
        return url
    except Exception:
        # If any error occurs during masking, return a generically masked URL
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
    for import_file in import_files:
        import_path = os.path.join(config_dir, import_file)
        try:
            with open(import_path, 'r') as file:
                imported_config = yaml.safe_load(file)
                logger.debug(f"Successfully imported configuration from {os.path.abspath(import_path)}")
                
                # Recursively process imports in the imported file
                imported_config = _process_imports(imported_config, config_dir)
                
                # Merge the imported config into the main config
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


def _process_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process environment variables in config values

    Supports two formats:
    - ${ENV_VAR_NAME} - Required variable, logs warning if not found
    - ${ENV_VAR_NAME:-default} - Optional variable with default value
    """
    def replace_env_vars(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            inner = value[2:-1]

            # Check for default value syntax: ${VAR:-default}
            if ':-' in inner:
                env_var_name, default_value = inner.split(':-', 1)
                env_value = os.environ.get(env_var_name)
                if env_value is not None and env_value != "":
                    return env_value
                else:
                    # Use default silently (no warning for optional vars)
                    return default_value
            else:
                # No default - this is a required variable
                env_var_name = inner
                env_value = os.environ.get(env_var_name)
                if env_value is not None:
                    return env_value
                else:
                    logger.warning(f"Environment variable {env_var_name} not found")
                    return ""
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
    # Clear the cache to force a fresh load
    load_config.cache_clear()

    try:
        # Load the FULL config (includes all imports: adapters, inference, embeddings, etc.)
        config = load_config(config_path)

        logger.info(f"Reloaded FULL configuration from {os.path.abspath(config_path)} (includes all provider configs)")

        return config

    except FileNotFoundError:
        logger.error(f"Configuration file not found: {os.path.abspath(config_path)}")
        raise
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        raise


def _resolve_ollama_presets(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve Ollama preset references in inference configuration.
    
    If inference.ollama contains a 'use_preset' key, this function looks up the
    preset in ollama_presets and replaces the ollama config with the preset values.
    
    The 'enabled' flag from inference.yaml is preserved and takes precedence.
    
    Example:
        # In inference.yaml:
        inference:
          ollama:
            enabled: true
            use_preset: "granite-cpu"
        
        # In ollama.yaml:
        ollama_presets:
          granite-cpu:
            model: "granite4:1b"
            num_gpu: 0
            ...
        
        # Result after resolution:
        inference:
          ollama:
            enabled: true
            model: "granite4:1b"
            num_gpu: 0
            ...
    
    Args:
        config: The merged configuration dictionary
        
    Returns:
        The configuration with ollama presets resolved
    """
    try:
        inference_config = config.get('inference', {})
        ollama_config = inference_config.get('ollama', {})
        ollama_presets = config.get('ollama_presets', {})
        
        # Check if there's a preset reference
        preset_name = ollama_config.get('use_preset')
        if not preset_name:
            return config
        
        # Look up the preset
        if preset_name not in ollama_presets:
            logger.error(
                f"Ollama preset '{preset_name}' not found in ollama_presets. "
                f"Available presets: {list(ollama_presets.keys())}"
            )
            return config
        
        preset = ollama_presets[preset_name]
        if not isinstance(preset, dict):
            logger.error(f"Ollama preset '{preset_name}' is not a valid configuration dictionary")
            return config
        
        # Preserve the 'enabled' flag from inference.yaml
        enabled = ollama_config.get('enabled', True)
        
        # Replace ollama config with preset values
        resolved_ollama = preset.copy()
        resolved_ollama['enabled'] = enabled
        
        # Mark that this config came from a preset - adapter loader should NOT override the model
        # This prevents adapter model overrides (e.g., "gpt-5.1") from breaking Ollama presets
        resolved_ollama['_from_preset'] = preset_name
        
        # Remove use_preset from the resolved config (it's been processed)
        if 'use_preset' in resolved_ollama:
            del resolved_ollama['use_preset']
        
        # Update the config
        config['inference']['ollama'] = resolved_ollama
        
        logger.info(f"Resolved Ollama configuration from preset '{preset_name}' (model={preset.get('model')})")
        
        return config
        
    except Exception as e:
        logger.warning(f"Error resolving Ollama presets: {str(e)}")
        return config


