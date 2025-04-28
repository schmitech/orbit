"""
Logger Service for handling logs to file and Elasticsearch
"""

import os
import json
import logging
import ipaddress
import asyncio
import traceback
from typing import Dict, Any, Union, List, Optional, TypedDict
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler

from pythonjsonlogger import jsonlogger
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConnectionError, TransportError, NotFoundError
from fastapi import HTTPException

from utils.text_utils import mask_api_key

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _is_true_value(value: Union[str, bool]) -> bool:
    """
    Convert a string or boolean value to a boolean.
    
    Args:
        value: The value to check.
        
    Returns:
        True if the value represents a true value, otherwise False.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1')
    return False


class IPMetadata(TypedDict):
    """Type definition for IP address metadata."""
    address: str
    type: str  # 'ipv4' | 'ipv6' | 'local' | 'unknown'
    isLocal: bool
    source: str  # 'direct' | 'proxy' | 'unknown'
    originalValue: str


class LoggerService:
    """Logger service for handling logs to file and Elasticsearch."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.es_client: Optional[AsyncElasticsearch] = None
        verbose_value = config.get('general', {}).get('verbose', False)
        self.verbose = _is_true_value(verbose_value)
        self._has_logged_es_disabled = False  # Add flag to track if we've logged ES disabled message
        
        # Get the inference provider from config
        self.inference_provider = config.get('general', {}).get('inference_provider', 'ollama')
        
        # Configure Elasticsearch-related and HTTP client loggers based on verbose setting
        if not self.verbose:
            # Only show warnings and errors for these loggers when not in verbose mode
            for logger_name in ["elastic_transport", "elasticsearch", "httpx"]:
                client_logger = logging.getLogger(logger_name)
                client_logger.setLevel(logging.WARNING)
        
        # Extract logging configuration and set up log directory
        self.log_config = config.get('logging', {})
        self.log_dir = self.log_config.get('file', {}).get('directory', 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Set up the file-based JSON logger for chat interactions
        self.file_logger = self._setup_chat_logger()

    def _setup_chat_logger(self) -> logging.Logger:
        """Set up a JSON-formatted logger with file rotation for chat interactions."""
        chat_logger = logging.getLogger("chat_file_logger")
        chat_logger.setLevel(logging.INFO)
        chat_logger.handlers.clear()  # Remove any existing handlers

        log_file = os.path.join(self.log_dir, 'chat.log')
        file_config = self.log_config.get('file', {})
        rotation = file_config.get('rotation', 'midnight')
        backup_count = file_config.get('backup_count', 30)
        max_size_mb = file_config.get('max_size_mb', 10)

        if rotation == 'midnight':
            handler = TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=backup_count,
                encoding='utf-8'
            )
            # Append current date to rotated log filenames
            handler.namer = lambda name: name.replace('chat.log', f'chat-{datetime.now().strftime("%Y-%m-%d")}.log')
        else:
            handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding='utf-8'
            )
        
        formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        chat_logger.addHandler(handler)
        chat_logger.propagate = False
        return chat_logger

    async def initialize_elasticsearch(self) -> None:
        """Initialize the Elasticsearch client if enabled."""
        es_config = self.config.get('internal_services', {}).get('elasticsearch', {})
        if not es_config.get('enabled', False):
            logger.info("Elasticsearch logging is disabled in configuration")
            return

        # Get API key from environment variables
        api_key = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_API_KEY")
        
        # Validate we have a valid API key
        if not api_key:
            logger.warning("Elasticsearch API key not found in environment variables")
            self.config["internal_services"]["elasticsearch"]["enabled"] = False
            return

        try:
            # Create Elasticsearch client using the minimal configuration pattern
            headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
            client_kwargs = {
                "api_key": api_key,
                "verify_certs": False,
                "ssl_show_warn": False,
                "request_timeout": 30,
                "retry_on_timeout": True,
                "max_retries": 3,
                "headers": headers
            }
                
            self.es_client = AsyncElasticsearch(
                es_config["node"],
                **client_kwargs
            )
            
            # Ensure connection is reachable
            await asyncio.wait_for(self.es_client.ping(), timeout=5.0)
            logger.info("Successfully connected to Elasticsearch using API key authentication")
            await self._setup_elasticsearch_index()
        except asyncio.TimeoutError:
            logger.error("Elasticsearch connection timeout", exc_info=True)
            self.config["internal_services"]["elasticsearch"]["enabled"] = False
            self.es_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}", exc_info=True)
            logger.info("Continuing without Elasticsearch logging...")
            self.config["internal_services"]["elasticsearch"]["enabled"] = False
            self.es_client = None

    async def _setup_elasticsearch_index(self) -> None:
        """Create the Elasticsearch index if it does not already exist."""
        if not self.es_client:
            return

        index_name = self.config["internal_services"]["elasticsearch"]["index"]
        try:
            # First check if we can connect to the cluster
            cluster_info = await self.es_client.info()
            logger.info(f"Connected to Elasticsearch cluster: {cluster_info['cluster_name']}")
            
            # Check if index exists
            try:
                index_exists = await self.es_client.indices.exists(index=index_name)
                if not index_exists:
                    logger.info(f"Creating new index: {index_name}")
                    await self.es_client.indices.create(
                        index=index_name,
                        settings={
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                            "refresh_interval": "1s"
                        },
                        mappings={
                            "properties": {
                                "timestamp": {"type": "date"},
                                "query": {"type": "text"},
                                "response": {"type": "text"},
                                "backend": {"type": "keyword"},
                                "blocked": {"type": "boolean"},
                                "ip": {"type": "ip"},
                                "ip_metadata": {
                                    "properties": {
                                        "type": {"type": "keyword"},
                                        "isLocal": {"type": "boolean"},
                                        "source": {"type": "keyword"},
                                        "originalValue": {"type": "keyword"},
                                        "potentialRisk": {"type": "boolean"}
                                    }
                                }
                            }
                        }
                    )
                    logger.info(f"Successfully created index: {index_name}")
                else:
                    logger.info(f"Using existing index: {index_name}")
            except Exception as index_error:
                logger.error(f"Failed to setup index {index_name}: {str(index_error)}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Failed to setup Elasticsearch index: {str(e)}", exc_info=True)
            self.config["internal_services"]["elasticsearch"]["enabled"] = False
            self.es_client = None

    def _format_ip_address(self, ip: Optional[Union[str, List[str]]]) -> IPMetadata:
        """
        Convert a raw IP value (or list thereof) into structured IP metadata.
        """
        default_val = "unknown"
        default_metadata: IPMetadata = {
            "address": default_val,
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": ", ".join(ip) if isinstance(ip, list) else (ip or default_val)
        }
        ip_value: Optional[str] = None
        if isinstance(ip, list):
            ip_value = ip[0] if ip else None
        elif isinstance(ip, str):
            ip_value = ip
        if not ip_value:
            return default_metadata

        clean_ip = ip_value.strip()
        if clean_ip in ("::1", "::ffff:127.0.0.1", "127.0.0.1") or clean_ip.startswith("::ffff:127."):
            return {
                "address": "localhost",
                "type": "local",
                "isLocal": True,
                "source": "direct",
                "originalValue": clean_ip
            }
        if clean_ip.startswith("::ffff:"):
            clean_ip = clean_ip[7:]
            ip_type = "ipv4"
        elif ":" in clean_ip:
            ip_type = "ipv6"
        else:
            ip_type = "ipv4"
        return {
            "address": clean_ip,
            "type": ip_type,
            "isLocal": self._is_local_ip(clean_ip),
            "source": "proxy" if isinstance(ip, list) else "direct",
            "originalValue": clean_ip
        }

    def _is_local_ip(self, ip: str) -> bool:
        """Determine if an IP address is local (private or loopback)."""
        try:
            return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback
        except ValueError:
            return False

    async def log_conversation(
        self,
        query: str,
        response: str,
        ip: Optional[str] = None,
        backend: Optional[str] = None,
        blocked: bool = False,
        api_key: Optional[str] = None
    ) -> None:
        """
        Log a chat interaction to the file-based logger and Elasticsearch.
        
        Args:
            query: The user's query.
            response: The generated response.
            ip: Optional IP address.
            backend: The backend service used (defaults to inference_provider from config).
            blocked: Whether the request was blocked.
            api_key: Optional API key for logging.
        """
        timestamp = datetime.now()
        ip_metadata = self._format_ip_address(ip)
        
        # Use provided backend or fall back to inference_provider from config
        backend = backend or self.inference_provider
        
        log_data = {
            "timestamp": timestamp.isoformat(),
            "query": query,
            "response": response,
            "backend": backend,
            "blocked": blocked,
            "ip": {
                **ip_metadata,
                "potentialRisk": blocked and not ip_metadata["isLocal"],
                "timestamp": timestamp.isoformat()
            },
            "elasticsearch_status": "enabled" if (self.config.get("internal_services", {}).get("elasticsearch", {}).get("enabled", False)
                                                    and self.es_client) else "disabled"
        }

        if api_key:
            log_data["api_key"] = {
                "key": mask_api_key(api_key),
                "timestamp": timestamp.isoformat()
            }

        self.file_logger.info("Chat Interaction", extra=log_data)
        await self._log_to_elasticsearch(log_data, timestamp, query, response, backend, blocked, ip_metadata)

    async def _log_to_elasticsearch(
        self,
        log_data: Dict[str, Any],
        timestamp: datetime,
        query: str,
        response: str,
        backend: str,
        blocked: bool,
        ip_metadata: IPMetadata
    ) -> None:
        """Index the log data into Elasticsearch if enabled."""
        if not (self.config.get("internal_services", {}).get("elasticsearch", {}).get("enabled", False) and self.es_client):
            if self.verbose and not self._has_logged_es_disabled:
                logger.info("Elasticsearch logging skipped; client not available or disabled.")
                self._has_logged_es_disabled = True
            return

        try:
            ip_for_elastic = "127.0.0.1" if ip_metadata["type"] == "local" else ip_metadata["address"]
            document = {
                "timestamp": timestamp.isoformat(),
                "query": query,
                "response": response,
                "backend": backend,
                "blocked": blocked,
                "ip": ip_for_elastic,
                "ip_metadata": {
                    "type": ip_metadata["type"],
                    "isLocal": ip_metadata["isLocal"],
                    "source": ip_metadata["source"],
                    "originalValue": ip_metadata["originalValue"],
                    "potentialRisk": blocked and not ip_metadata["isLocal"]
                }
            }
            if self.verbose:
                logger.info(f"Indexing document to Elasticsearch: {json.dumps(document, indent=2)}")
            index_result = await self.es_client.index(
                index=self.config["internal_services"]["elasticsearch"]["index"],
                document=document,
                refresh=True
            )
            if self.verbose:
                logger.info(f"Elasticsearch indexing result: {index_result}")
                # Optional verification step
                verify_doc = await self.es_client.get(
                    index=self.config["internal_services"]["elasticsearch"]["index"],
                    id=index_result["_id"]
                )
                logger.info(f"Document verification: {verify_doc}")
        except Exception as e:
            logger.error(f"Failed to log to Elasticsearch: {e}", exc_info=True)
            # Additional diagnostics
            try:
                if self.es_client:
                    index_exists = await self.es_client.indices.exists(
                        index=self.config["internal_services"]["elasticsearch"]["index"]
                    )
                    logger.info(f"Index exists check: {self.config['internal_services']['elasticsearch']['index']} - {index_exists}")
                    if not index_exists:
                        logger.error("Index does not exist! This should not happen as it is created on startup.")
                    index_settings = await self.es_client.indices.get(
                        index=self.config["internal_services"]["elasticsearch"]["index"]
                    )
                    logger.info(f"Index settings: {index_settings}")
            except Exception as diag_error:
                logger.error(f"Error during Elasticsearch diagnostics: {diag_error}", exc_info=True)

    async def close(self) -> None:
        """Close the Elasticsearch client if open."""
        if self.es_client:
            await self.es_client.close()
