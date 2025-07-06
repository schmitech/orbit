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
    inference_only = _is_true_value(config.get('general', {}).get('inference_only', False))
    logger.info(f"  Server: port={config['general'].get('port')}, verbose={config['general'].get('verbose')}, inference_only={inference_only}")
    
    # Logging settings
    log_config = config.get('logging', {})
    logger.info(f"  Logging: level={log_config.get('level', 'INFO')}, file_enabled={_is_true_value(log_config.get('handlers', {}).get('file', {}).get('enabled', True))}")
    if _is_true_value(log_config.get('handlers', {}).get('file', {}).get('enabled', True)):
        logger.info(f"    File: rotation={log_config.get('handlers', {}).get('file', {}).get('rotation', 'midnight')}, max_size_mb={log_config.get('handlers', {}).get('file', {}).get('max_size_mb', 10)}")
    
    # Only log embedding settings if enabled and not in inference-only mode
    if not inference_only:
        embedding_provider = config.get('embedding', {}).get('provider', 'ollama')
        if _is_true_value(config.get('embedding', {}).get('enabled', True)):
            logger.info(f"  Embedding: provider={embedding_provider}")
            if embedding_provider == 'openai':
                openai_config = config.get('embeddings', {}).get('openai', {})
                logger.info(f"    OpenAI: model={openai_config.get('model', 'text-embedding-3-small')}, dimensions={openai_config.get('dimensions', 1536)}")
            elif embedding_provider == 'ollama':
                ollama_config = config.get('embeddings', {}).get('ollama', {})
                logger.info(f"    Ollama: model={ollama_config.get('model', 'nomic-embed-text')}, dimensions={ollama_config.get('dimensions', 768)}")
    
    # Only log datasource settings if they are used by any adapter and not in inference-only mode
    if not inference_only:
        adapter_configs = config.get('adapters', [])
        used_datasources = {adapter.get('datasource') for adapter in adapter_configs}
        
        if 'chroma' in used_datasources:
            chroma_config = config.get('datasources', {}).get('chroma', {})
            logger.info(f"  Chroma: host={chroma_config.get('host')}, port={chroma_config.get('port')}")
    
    # Get the active inference provider
    inference_provider = config.get('general', {}).get('inference_provider', 'ollama')
    
    # Only log the active inference provider settings
    if inference_provider == 'ollama':
        ollama_config = config.get('inference', {}).get('ollama', {})
        logger.info(f"  Ollama: base_url={_mask_url(ollama_config.get('base_url'))}, model={ollama_config.get('model')}")
        logger.info(f"  Stream: {_is_true_value(ollama_config.get('stream', True))}")
    elif inference_provider == 'together':
        together_config = config.get('inference', {}).get('together', {})
        logger.info(f"  Together AI: model={together_config.get('model')}, show_thinking={_is_true_value(together_config.get('show_thinking', False))}")
    elif inference_provider == 'xai':
        xai_config = config.get('inference', {}).get('xai', {})
        logger.info(f"  XAI: model={xai_config.get('model')}, show_thinking={_is_true_value(xai_config.get('show_thinking', False))}")
    elif inference_provider == 'watson':
        watson_config = config.get('inference', {}).get('watson', {})
        logger.info(f"  Watson AI: model={watson_config.get('model')}, api_base={_mask_url(watson_config.get('api_base'))}")
        logger.info(f"  Stream: {_is_true_value(watson_config.get('stream', True))}")
    
    # Only log MongoDB settings if chat history is enabled OR auth is enabled
    chat_history_enabled = _is_true_value(config.get('chat_history', {}).get('enabled', True))
    auth_enabled = _is_true_value(config.get('auth', {}).get('enabled', False))
    
    if chat_history_enabled or auth_enabled:
        mongodb_config = config.get('internal_services', {}).get('mongodb', {})
        if mongodb_config:
            usage_reasons = []
            if chat_history_enabled:
                usage_reasons.append("chat history")
            if auth_enabled:
                usage_reasons.append("authentication")
            
            logger.info(f"  MongoDB: host={mongodb_config.get('host')}, port={mongodb_config.get('port')}, db={mongodb_config.get('database')} (used for: {', '.join(usage_reasons)})")
    
    # Only log adapters if not in inference-only mode
    if not inference_only:
        adapter_configs = config.get('adapters', [])
        if adapter_configs:
            logger.info("  Adapters:")
            for adapter in adapter_configs:
                logger.info(f"    {adapter.get('name')}: type={adapter.get('type')}, datasource={adapter.get('datasource')}, adapter={adapter.get('adapter')}")
    
    # Log LLM Guard configuration
    llm_guard_config = config.get('llm_guard', {})
    
    # Check if enabled field exists or if section exists
    if llm_guard_config:
        if 'enabled' in llm_guard_config:
            # Structure with explicit enabled field
            llm_guard_enabled = llm_guard_config.get('enabled', False)
        else:
            # Simplified structure - if section exists, it's enabled
            llm_guard_enabled = True
    else:
        llm_guard_enabled = False
    
    logger.info(f"  LLM Guard: {'enabled' if llm_guard_enabled else 'disabled'}")
    if llm_guard_enabled:
        service_config = llm_guard_config.get('service', {})
        base_url = service_config.get('base_url', 'http://localhost:8000')
        logger.info(f"    Service URL: {_mask_url(base_url)}")
        
        security_config = llm_guard_config.get('security', {})
        risk_threshold = security_config.get('risk_threshold', 0.6)
        logger.info(f"    Default risk threshold: {risk_threshold}")
        
        # Log scanner configurations
        scanner_config = security_config.get('scanners', {})
        prompt_scanners = scanner_config.get('prompt', [])
        response_scanners = scanner_config.get('response', [])
        
        if prompt_scanners:
            logger.info(f"    Prompt scanners: {', '.join(prompt_scanners)}")
        if response_scanners:
            logger.info(f"    Response scanners: {', '.join(response_scanners)}")
        
        fallback_config = llm_guard_config.get('fallback', {})
        fallback_behavior = fallback_config.get('on_error', 'allow')
        logger.info(f"    Fallback behavior: {fallback_behavior}")
    
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
        "auth": {
            "enabled": False,
            "session_duration_hours": 12,
            "default_admin_username": "admin",
            "default_admin_password": "admin123"
        },
        "logging": {
            "level": "INFO",
            "handlers": {
                "file": {
                    "enabled": True,
                    "directory": "logs",
                    "filename": "orbit.log",
                    "max_size_mb": 10,
                    "backup_count": 30,
                    "rotation": "midnight",
                    "format": "json"
                },
                "console": {
                    "enabled": True,
                    "format": "text"
                }
            },
            "capture_warnings": True,
            "propagate": False
        },
        "embedding": {
            "provider": "ollama",
            "enabled": False,
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
        "reranker": {
            "provider": "ollama",
            "enabled": True
        },
        "rerankers": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "xitao/bge-reranker-v2-m3:latest",
                "temperature": 0.0,
                "batch_size": 5
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
                "host": "${DATASOURCE_PINECONE_HOST}",
                "namespace": "default",
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
            },
            "watson": {
                "api_key": "${WATSON_API_KEY}",
                "api_base": "${WATSON_API_BASE}",
                "project_id": "${WATSON_PROJECT_ID}",
                "space_id": None,
                "instance_id": None,
                "region": None,
                "auth_type": "iam",
                "model": "meta-llama/llama-3-8b-instruct",
                "temperature": 0.1,
                "top_p": 0.8,
                "top_k": 20,
                "max_tokens": 1024,
                "time_limit": 10000,
                "stream": True,
                "verify": False
            }
        },
        "internal_services": {
            "elasticsearch": {
                "enabled": False,
                "node": "http://localhost:9200",
                "index": "orbit",
                "username": "${INTERNAL_SERVICES_ELASTICSEARCH_USERNAME}",
                "password": "${INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD}"
            },
            "mongodb": {
                "host": "localhost",
                "port": 27017,
                "database": "orbit",
                "apikey_collection": "api_keys",
                "users_collection": "users",
                "sessions_collection": "sessions",
                "prompts_collection": "system_prompts",
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
                "name": "qa-vector",
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
        ],
        "chat_history": {
            "enabled": True,
            "collection_name": "chat_history",
            "store_metadata": True,
            "retention_days": 90,
            "max_tracked_sessions": 10000,
            "session": {
                "auto_generate": True,
                "required": True,
                "header_name": "X-Session-ID"
            },
            "user": {
                "header_name": "X-User-ID",
                "required": False
            }
        },
        "file_upload": {
            "enabled": True,
            "max_size_mb": 10,
            "max_files_per_batch": 10,
            "allowed_extensions": [
                ".txt",
                ".pdf",
                ".docx",
                ".doc",
                ".xlsx",
                ".xls",
                ".csv",
                ".md",
                ".json"
            ],
            "upload_directory": "uploads",
            "save_to_disk": True,
            "auto_store_in_vector_db": True,
            "chunk_size": 1000,
            "chunk_overlap": 200
        },
        "llm_guard": {
            "enabled": False,
            "service": {
                "base_url": "http://localhost:8000",
                "timeout": 30
            },
            "security": {
                "risk_threshold": 0.6,
                "scanners": {
                    "prompt": [
                        "ban_substrings",
                        "ban_topics", 
                        "prompt_injection",
                        "toxicity",
                        "secrets"
                    ],
                    "response": [
                        "no_refusal",
                        "sensitive",
                        "bias",
                        "relevance"
                    ]
                }
            },
            "fallback": {
                "on_error": "allow"
            }
        }
    }