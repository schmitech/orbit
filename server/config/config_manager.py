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
    
    # Embedding settings
    embedding_provider = config.get('embedding', {}).get('provider', 'ollama')
    logger.info(f"  Embedding: provider={embedding_provider}, enabled={_is_true_value(config.get('embedding', {}).get('enabled', True))}")
    
    # Log the specific embedding provider configuration
    if embedding_provider == 'openai':
        openai_config = config.get('embeddings', {}).get('openai', {})
        logger.info(f"    OpenAI: model={openai_config.get('model', 'text-embedding-3-small')}, dimensions={openai_config.get('dimensions', 1536)}")
    elif embedding_provider == 'ollama':
        ollama_config = config.get('embeddings', {}).get('ollama', {})
        logger.info(f"    Ollama: model={ollama_config.get('model', 'nomic-embed-text')}, dimensions={ollama_config.get('dimensions', 768)}")
    elif embedding_provider == 'jina':
        jina_config = config.get('embeddings', {}).get('jina', {})
        logger.info(f"    Jina: model={jina_config.get('model')}, dimensions={jina_config.get('dimensions', 1024)}")
    elif embedding_provider == 'cohere':
        cohere_config = config.get('embeddings', {}).get('cohere', {})
        logger.info(f"    Cohere: model={cohere_config.get('model')}, dimensions={cohere_config.get('dimensions', 1024)}, input_type={cohere_config.get('input_type', 'search_document')}")
    elif embedding_provider == 'mistral':
        mistral_config = config.get('embeddings', {}).get('mistral', {})
        logger.info(f"    Mistral: model={mistral_config.get('model')}, dimensions={mistral_config.get('dimensions', 1024)}")
    
    # Safety settings
    safety_mode = config.get('safety', {}).get('mode', 'strict')
    safety_enabled = config.get('safety', {}).get('enabled', True)
    logger.info(f"  Safety: enabled={safety_enabled}, mode={safety_mode}, max_retries={config.get('safety', {}).get('max_retries', 3)}")
    
    # Datasources settings (Chroma)
    chroma_config = config.get('datasources', {}).get('chroma', {})
    logger.info(f"  Chroma: host={chroma_config.get('host')}, port={chroma_config.get('port')}")
    
    # Inference settings (Ollama)
    ollama_config = config.get('inference', {}).get('ollama', {})
    logger.info(f"  Ollama: base_url={_mask_url(ollama_config.get('base_url'))}, model={ollama_config.get('model')}")
    logger.info(f"  Stream: {_is_true_value(ollama_config.get('stream', True))}")
    
    # Together AI settings
    together_config = config.get('inference', {}).get('together', {})
    if together_config:
        logger.info(f"  Together AI: model={together_config.get('model')}, show_thinking={_is_true_value(together_config.get('show_thinking', False))}")
    
    # XAI settings
    xai_config = config.get('inference', {}).get('xai', {})
    if xai_config:
        logger.info(f"  XAI: model={xai_config.get('model')}, show_thinking={_is_true_value(xai_config.get('show_thinking', False))}")
    
    # Elasticsearch settings - mask credentials
    es_config = config.get('internal_services', {}).get('elasticsearch', {})
    if _is_true_value(es_config.get('enabled', False)):
        es_node = _mask_url(es_config.get('node', ''))
        has_api_key = bool(es_config.get('api_key'))
        logger.info(f"  Elasticsearch: enabled=True, node={es_node}, index={es_config.get('index')}, auth='API Key'")
    
    # MongoDB settings - mask credentials
    mongodb_config = config.get('internal_services', {}).get('mongodb', {})
    if mongodb_config:
        logger.info(f"  MongoDB: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}, db={mongodb_config.get('database')}")
    
    # Log adapter configuration
    adapter_configs = config.get('adapters', [])
    if adapter_configs:
        logger.info("  Adapters:")
        for adapter in adapter_configs:
            logger.info(f"    {adapter.get('name')}: type={adapter.get('type')}, datasource={adapter.get('datasource')}, adapter={adapter.get('adapter')}")
    
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
            "inference_only": False,
            "https": {
                "enabled": False,
                "port": 3443,
                "cert_file": "./cert.pem",
                "key_file": "./key.pem"
            },
            "inference_provider": "ollama",
            "session_id": {
                "header_name": "X-Session-ID",
                "required": False
            }
        },
        "messages": {
            "no_results_response": "I'm sorry, but I don't have any specific information about that topic in my knowledge base.",
            "collection_not_found": "I couldn't find the requested collection. Please make sure the collection exists before querying it."
        },
        "api_keys": {
            "header_name": "X-API-Key",
            "prefix": "orbit_",
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
        "embedding": {
            "provider": "ollama",
            "enabled": True,
            "fail_on_error": False
        },
        "embeddings": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "nomic-embed-text",
                "dimensions": 768
            },
            "openai": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "text-embedding-3-large",
                "dimensions": 1024,
                "batch_size": 10
            },
            "jina": {
                "api_key": "${JINA_API_KEY}",
                "base_url": "https://api.jina.ai/v1",
                "model": "jina-embeddings-v3",
                "task": "text-matching",
                "dimensions": 1024,
                "batch_size": 10
            },
            "cohere": {
                "api_key": "${COHERE_API_KEY}",
                "model": "embed-english-v3.0",
                "input_type": "search_document",
                "dimensions": 1024,
                "batch_size": 32,
                "truncate": "NONE",
                "embedding_types": ["float"]
            },
            "mistral": {
                "api_key": "${MISTRAL_API_KEY}",
                "api_base": "https://api.mistral.ai/v1",
                "model": "mistral-embed",
                "dimensions": 1024
            }
        },
        "safety": {
            "enabled": True,
            "mode": "fuzzy",
            "moderator": "ollama",
            "max_retries": 3,
            "retry_delay": 1.0,
            "request_timeout": 10,
            "allow_on_timeout": False
        },
        "moderators": {
            "openai": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "omni-moderation-latest"
            },
            "anthropic": {
                "api_key": "${ANTHROPIC_API_KEY}",
                "model": "claude-3-haiku-20240307",
                "temperature": 0.0,
                "max_tokens": 10,
                "batch_size": 5
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "gemma3:12b",
                "temperature": 0.0,
                "top_p": 1.0,
                "max_tokens": 50,
                "batch_size": 1
            }
        },
        "reranker": {
            "enabled": False,
            "provider_override": None,
            "model": "gemma3:1b",
            "batch_size": 5,
            "temperature": 0.0,
            "top_n": 3
        },
        "rerankers": {
            "cohere": {
                "api_key": "${COHERE_API_KEY}",
                "model": "rerank-english-v3.0",
                "top_n": 5,
                "batch_size": 32
            },
            "openai": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o",
                "temperature": 0.0,
                "max_tokens": 512,
                "batch_size": 20
            },
            "anthropic": {
                "api_key": "${ANTHROPIC_API_KEY}",
                "model": "claude-3-haiku-20240307",
                "temperature": 0.0,
                "max_tokens": 512,
                "batch_size": 10
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "gemma3:1b",
                "temperature": 0.0,
                "batch_size": 5
            },
            "jina": {
                "api_key": "${JINA_API_KEY}",
                "model": "jina-reranker-v2-base-en",
                "batch_size": 20
            },
            "vertex": {
                "project_id": "${GOOGLE_CLOUD_PROJECT}",
                "location": "us-central1",
                "model": "text-bison@002",
                "temperature": 0.0,
                "max_tokens": 256,
                "batch_size": 8,
                "credentials_path": ""
            }
        },
        "datasources": {
            "chroma": {
                "use_local": True,
                "db_path": "./chroma_db",
                "host": "localhost",
                "port": 8000,
                "embedding_provider": None
            },
            "sqlite": {
                "db_path": "sqlite_db"
            },
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "retrieval",
                "username": "${DATASOURCE_POSTGRES_USERNAME}",
                "password": "${DATASOURCE_POSTGRES_PASSWORD}"
            },
            "milvus": {
                "host": "localhost",
                "port": 19530,
                "dim": 768,
                "metric_type": "IP",
                "embedding_provider": None
            },
            "pinecone": {
                "api_key": "${DATASOURCE_PINECONE_API_KEY}",
                "environment": "${DATASOURCE_PINECONE_ENVIRONMENT}",
                "index_name": "${DATASOURCE_PINECONE_INDEX_NAME}",
                "embedding_provider": None
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
                "stream": True
            },
            "aws": {
                "access_key": "${AWS_BEDROCK_ACCESS_KEY}",
                "secret_access_key": "${AWS_SECRET_ACCESS_KEY}",
                "region": "us-east-1",
                "model": "amazon.titan-embed-001",
                "content_type": "application/json",
                "accept": "application/json",
                "max_tokens": 1024
            },
            "together": {
                "api_key": "${TOGETHER_API_KEY}",
                "api_base": "https://api.together.xyz/v1",
                "model": "meta-llama/Llama-3-8b-chat-hf",
                "temperature": 0.1,
                "top_p": 0.8,
                "max_tokens": 1024,
                "stream": True,
                "show_thinking": False
            },
            "xai": {
                "api_key": "${XAI_API_KEY}",
                "api_base": "https://api.x.ai/v1",
                "model": "grok-3-mini-beta",
                "temperature": 0.1,
                "top_p": 0.8,
                "max_tokens": 1024,
                "stream": True,
                "show_thinking": False
            }
        },
        "internal_services": {
            "elasticsearch": {
                "enabled": False,
                "node": "http://localhost:9200",
                "index": "orbit",
                "api_key": ""
            },
            "mongodb": {
                "host": "localhost",
                "port": 27017,
                "database": "orbit",
                "apikey_collection": "api_keys",
                "username": "${INTERNAL_SERVICES_MONGODB_USERNAME}",
                "password": "${INTERNAL_SERVICES_MONGODB_PASSWORD}"
            }
        },
        "adapters": [
            {
                "name": "qa-sqlite",
                "type": "retriever",
                "datasource": "sqlite",
                "adapter": "qa",
                "implementation": "retrievers.implementations.sqlite.qa_sqlite_retriever.QASqliteRetriever",
                "config": {
                    "confidence_threshold": 0.3,
                    "max_results": 5,
                    "return_results": 3
                }
            },
            {
                "name": "qa-chroma",
                "type": "retriever",
                "datasource": "chroma",
                "adapter": "qa",
                "implementation": "retrievers.implementations.chroma.qa_chroma_retriever.QAChromaRetriever",
                "config": {
                    "confidence_threshold": 0.3,
                    "distance_scaling_factor": 200.0,
                    "embedding_provider": None,
                    "max_results": 5,
                    "return_results": 3
                }
            }
        ]
    }