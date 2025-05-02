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
    # First try the shared config
    config_paths = [
        config_path,  # User-specified config path
        '../config/config.yaml',  # Shared config
        '../../config/config.yaml',  # Alternative path
        'config.yaml',  # Fallback to local config
    ]
    
    # Filter out None values
    config_paths = [p for p in config_paths if p is not None]
    
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
    safety_enabled = config.get('safety', {}).get('enabled', True)
    logger.info(f"  Safety: enabled={safety_enabled}, mode={safety_mode}, max_retries={config.get('safety', {}).get('max_retries', 3)}")
    
    # Datasources settings (Chroma)
    chroma_config = config.get('datasources', {}).get('chroma', {})
    logger.info(f"  Chroma: host={chroma_config.get('host')}, port={chroma_config.get('port')}")
    
    # Inference settings (Ollama)
    ollama_config = config.get('inference', {}).get('ollama', {})
    logger.info(f"  Ollama: base_url={_mask_url(ollama_config.get('base_url'))}, model={ollama_config.get('model')}, embed_model={ollama_config.get('embed_model')}")
    logger.info(f"  Stream: {_is_true_value(ollama_config.get('stream', True))}")
    
    # Elasticsearch settings - mask credentials
    es_config = config.get('internal_services', {}).get('elasticsearch', {})
    if _is_true_value(es_config.get('enabled', False)):
        es_node = _mask_url(es_config.get('node', ''))
        has_api_key = bool(es_config.get('api_key'))
        logger.info(f"  Elasticsearch: enabled=True, node={es_node}, index={es_config.get('index')}, auth='API Key'")
    
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
    
    # Ensure top-level sections exist with recursive merging of defaults
    for section, section_defaults in default_config.items():
        if section not in config:
            logger.warning(f"Missing config section '{section}'. Using defaults.")
            config[section] = section_defaults
        elif isinstance(section_defaults, dict):
            # For dict sections, recursively merge with defaults
            config[section] = _merge_defaults(config[section], section_defaults, section)
    
    return config


def _merge_defaults(config_section: Dict[str, Any], defaults_section: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """
    Recursively merge default values into a config section
    
    Args:
        config_section: Current config section
        defaults_section: Default values for this section
        path: Current path in config (for logging)
        
    Returns:
        Dict[str, Any]: Merged config section with defaults
    """
    for key, default_value in defaults_section.items():
        current_path = f"{path}.{key}" if path else key
        
        if key not in config_section:
            logger.warning(f"Missing config key '{current_path}'. Using default value: {default_value}")
            config_section[key] = default_value
        elif isinstance(default_value, dict) and isinstance(config_section[key], dict):
            # Recursively merge nested dictionaries
            config_section[key] = _merge_defaults(config_section[key], default_value, current_path)
    
    return config_section


def _process_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Process environment variables in config values"""
    # Handle environment variables in the config (format: ${ENV_VAR_NAME})
    def replace_env_vars(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            env_var_name = value[2:-1]
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
            },
            "inference_provider": "ollama",
            "datasource_provider": "chroma"
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
            "enabled": True,
            "mode": "fuzzy",
            "provider_override": None,
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
        "reranker": {
            "enabled": False,
            "provider_override": None,
            "model": "gemma3:1b",
            "batch_size": 5,
            "temperature": 0.0,
            "top_n": 3
        },
        "embedding": {
            "provider": "ollama",
            "enabled": True,
            "fail_on_error": False
        },
        "datasources": {
            "chroma": {
                "use_local": True,
                "db_path": "./chroma_db",
                "host": "localhost",
                "port": 8000,
                "domain_adapter": "qa",
                "confidence_threshold": 0.85,
                "relevance_threshold": 0.7,
                "embedding_provider": None
            },
            "sqlite": {
                "db_path": "../utils/sqllite/rag_database.db",
                "confidence_threshold": 0.7,
                "relevance_threshold": 0.5,
                "max_results": 10,
                "return_results": 3,
                "domain_adapter": "sql_qa",
                "adapter_params": {
                    "confidence_threshold": 0.7,
                    "boost_exact_matches": True
                }
            },
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "retrieval",
                "username": "${DATASOURCE_POSTGRES_USERNAME}",
                "password": "${DATASOURCE_POSTGRES_PASSWORD}",
                "schema": "public",
                "table": "documents",
                "embedding_column": "embedding",
                "content_column": "content",
                "metadata_columns": ["source", "date", "author"],
                "domain_adapter": "generic",
                "adapter_params": {
                    "confidence_threshold": 0.7
                }
            },
            "milvus": {
                "host": "localhost",
                "port": 19530,
                "dim": 768,
                "metric_type": "IP",
                "embedding_provider": None,
                "domain_adapter": "generic",
                "adapter_params": {
                    "confidence_threshold": 0.7
                }
            },
            "pinecone": {
                "api_key": "${DATASOURCE_PINECONE_API_KEY}",
                "environment": "${DATASOURCE_PINECONE_ENVIRONMENT}",
                "index_name": "${DATASOURCE_PINECONE_INDEX_NAME}",
                "embedding_provider": None,
                "domain_adapter": "generic",
                "adapter_params": {
                    "confidence_threshold": 0.7
                }
            }
        },
        "inference": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.1,
                "num_predict": 1024,
                "model": "llama2",
                "embed_model": "nomic-embed-text",
                "stream": True
            }
        },
        "internal_services": {
            "elasticsearch": {
                "enabled": False,
                "node": "http://localhost:9200",
                "index": "orbit",
                "api_key": ""
            }
        }
    }