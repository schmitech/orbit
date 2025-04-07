"""
Configuration management for the chat application
"""

import os
import yaml
import logging
from typing import Dict, Any
from functools import lru_cache
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def load_config():
    """Load configuration from shared config.yaml file"""
    # First try the shared config
    config_paths = [
        '../config/config.yaml',  # Shared config
        '../../backend/config/config.yaml',  # Alternative path
        'config.yaml',  # Fallback to local config
    ]
    
    for config_path in config_paths:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                logger.info(f"Successfully loaded configuration from {os.path.abspath(config_path)}")
                
                # Ensure all required config sections exist with defaults
                config = ensure_config_defaults(config)
                
                # Log key configuration values
                _log_config_summary(config, config_path)
                
                return config
        except FileNotFoundError:
            logger.debug(f"Config file not found at {os.path.abspath(config_path)}")
            continue
        except Exception as e:
            logger.warning(f"Error loading config from {os.path.abspath(config_path)}: {str(e)}")
    
    # If we get here, no config was found - use default config
    logger.warning("No config file found. Using default configuration.")
    default_config = get_default_config()
    _log_config_summary(default_config, "DEFAULT")
    return default_config


def _log_config_summary(config: Dict[str, Any], source_path: str):
    """Log a summary of important config values with sensitive data masked"""
    logger.info(f"Configuration summary (source: {source_path}):")
    
    # Server settings
    logger.info(f"  Server: port={config['general'].get('port')}, verbose={config['general'].get('verbose')}")
    
    # Logging settings
    log_config = config.get('logging', {})
    logger.info(f"  Logging: level={log_config.get('level', 'INFO')}, file_enabled={_is_true_value(log_config.get('file', {}).get('enabled', True))}")
    if _is_true_value(log_config.get('file', {}).get('enabled', True)):
        logger.info(f"    File: rotation={log_config.get('file', {}).get('rotation', 'midnight')}, max_size_mb={log_config.get('file', {}).get('max_size_mb', 10)}")
    
    # Safety settings
    safety_mode = config.get('safety', {}).get('mode', 'strict')
    logger.info(f"  Safety: mode={safety_mode}, max_retries={config.get('safety', {}).get('max_retries', 3)}")
    
    # Chroma settings
    logger.info(f"  Chroma: host={config['chroma'].get('host')}, port={config['chroma'].get('port')}, collection={config['chroma'].get('collection')}")
    
    # Ollama settings - don't log any potential API keys
    logger.info(f"  Ollama: base_url={_mask_url(config['ollama'].get('base_url'))}, model={config['ollama'].get('model')}, embed_model={config['ollama'].get('embed_model')}")
    logger.info(f"  Stream: {_is_true_value(config['ollama'].get('stream', True))}")
    
    # Elasticsearch settings - mask credentials
    if _is_true_value(config.get('elasticsearch', {}).get('enabled', False)):
        es_node = _mask_url(config['elasticsearch'].get('node', ''))
        has_auth = bool(config['elasticsearch'].get('auth', {}).get('username'))
        logger.info(f"  Elasticsearch: enabled=True, node={es_node}, index={config['elasticsearch'].get('index')}, auth={'[CONFIGURED]' if has_auth else '[NONE]'}")
    
    # Eleven Labs settings - mask API key
    if 'eleven_labs' in config:
        has_api_key = bool(config['eleven_labs'].get('api_key'))
        logger.info(f"  ElevenLabs: api_key={'[CONFIGURED]' if has_api_key else '[NONE]'}, voice_id={config['eleven_labs'].get('voice_id')}")
    
    # Log if HTTPS is enabled
    https_enabled = _is_true_value(config.get('general', {}).get('https', {}).get('enabled', False))
    if https_enabled:
        logger.info(f"  HTTPS: enabled=True, port={config['general']['https'].get('port')}")


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


def ensure_config_defaults(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all required config sections and values exist with defaults"""
    default_config = get_default_config()
    
    # Process environment variables in config before checking defaults
    config = _process_env_vars(config)
    
    # Ensure top-level sections exist
    for section in default_config:
        if section not in config:
            logger.warning(f"Missing config section '{section}'. Using defaults.")
            config[section] = default_config[section]
        elif isinstance(default_config[section], dict):
            # For dict sections, merge with defaults preserving existing values
            for key, value in default_config[section].items():
                if key not in config[section]:
                    logger.warning(f"Missing config key '{section}.{key}'. Using default value: {value}")
                    config[section][key] = value
    
    # Make sure confidence_threshold exists
    if 'chroma' in config:
        if 'confidence_threshold' not in config['chroma']:
            config['chroma']['confidence_threshold'] = 0.65
    
    return config


def _process_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process environment variables in config values"""
    # Handle environment variables in the config (format: ${ENV_VAR_NAME})
    def replace_env_vars(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var_name = value[2:-1]
            env_value = os.environ.get(env_var_name)
            if env_value is not None:
                logger.info(f"Using environment variable {env_var_name} for configuration")
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


def _is_true_value(value) -> bool:
    """Helper function to check if a value (string or boolean) is equivalent to True"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', 'y', '1', 'on')
    # Numeric values - 0 is False, anything else is True
    if isinstance(value, (int, float)):
        return bool(value)
    # Default for anything else
    return False


def get_default_config() -> Dict[str, Any]:
    """Return default configuration values"""
    return {
        "general": {
            "port": 3000,
            "verbose": "false",
            "https": {
                "enabled": False,
                "port": 3443,
                "cert_file": "./cert.pem",
                "key_file": "./key.pem"
            }
        },
        "logging": {
            "level": "INFO",
            "file": {
                "enabled": True,
                "directory": "logs",
                "filename": "server.log",
                "max_size_mb": 10,
                "backup_count": 30,
                "rotation": "midnight",
                "format": "json"
            },
            "console": {
                "enabled": True,
                "format": "text"
            },
            "capture_warnings": True,
            "propagate": False
        },
        "safety": {
            "mode": "fuzzy",
            "model": "gemma3:12b",
            "max_retries": 3,
            "retry_delay": 1.0,
            "request_timeout": 15,
            "allow_on_timeout": False,
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "num_predict": 20,
            "stream": False,
            "repeat_penalty": 1.1
        },
        "chroma": {
            "host": "localhost",
            "port": 8000,
            "collection": "qa-chatbot",
            "confidence_threshold": 0.85
        },
        "elasticsearch": {
            "enabled": False,
            "node": "http://localhost:9200",
            "index": "chat-logs",
            "auth": {
                "username": "",
                "password": ""
            }
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_predict": 1024,
            "model": "llama2",
            "embed_model": "nomic-embed-text",
            # Summarization settings
            "summarization_model": "llama2",
            "max_summary_length": 100,
            "enable_summarization": False
        }
    }