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

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConnectionError, TransportError, NotFoundError, ApiError
from fastapi import HTTPException

from utils.text_utils import mask_api_key
from utils import is_true_value

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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
        self.verbose = is_true_value(verbose_value)
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

    async def initialize_elasticsearch(self) -> None:
        """Initialize the Elasticsearch client if enabled."""
        es_config = self.config.get('internal_services', {}).get('elasticsearch', {})
        if not es_config.get('enabled', False):
            logger.info("Elasticsearch logging is disabled in configuration")
            return

        # Get credentials from environment variables
        username = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
        password = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")
        
        # Validate we have valid credentials
        if not username or not password:
            logger.warning("Elasticsearch credentials not found in environment variables")
            self.config["internal_services"]["elasticsearch"]["enabled"] = False
            return

        try:
            # Create Elasticsearch client using the minimal configuration pattern
            # Updated for Elasticsearch 9.0.2 compatibility
            client_kwargs = {
                "basic_auth": (username, password),
                "verify_certs": False,
                "ssl_show_warn": False,
                "request_timeout": 30,
                "retry_on_timeout": True,
                "max_retries": 3,
                "http_compress": True  # Enable compression for better performance
            }
                
            self.es_client = AsyncElasticsearch(
                es_config["node"],
                **client_kwargs
            )
            
            # Ensure connection is reachable
            await asyncio.wait_for(self.es_client.ping(), timeout=5.0)
            logger.info("Successfully connected to Elasticsearch using basic authentication")
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
                            "refresh_interval": "1s",
                            "analysis": {
                                "analyzer": {
                                    "default": {
                                        "type": "standard"
                                    }
                                }
                            }
                        },
                        mappings={
                            "properties": {
                                "timestamp": {"type": "date"},
                                "query": {"type": "text", "analyzer": "standard"},
                                "response": {"type": "text", "analyzer": "standard"},
                                "backend": {"type": "keyword"},
                                "blocked": {"type": "boolean"},
                                "ip": {"type": "ip"},
                                "ip_metadata": {
                                    "properties": {
                                        "type": {"type": "keyword"},
                                        "isLocal": {"type": "boolean"},
                                        "source": {"type": "keyword"},
                                        "originalValue": {"type": "keyword"}
                                    }
                                },
                                "api_key": {
                                    "properties": {
                                        "key": {"type": "keyword"},
                                        "timestamp": {"type": "date"}
                                    }
                                },
                                "session_id": {"type": "keyword"},
                                "user_id": {"type": "keyword"}
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
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Log a chat interaction to Elasticsearch only.
        
        Args:
            query: The user's query
            response: The system's response
            ip: The IP address of the user
            backend: The backend used for the response
            blocked: Whether the query was blocked by the guardrail service
            api_key: The API key used for the request
            session_id: The session ID for the conversation
            user_id: The user ID if available
        """
        timestamp = datetime.now()
        ip_metadata = self._format_ip_address(ip)
        
        # Use provided backend or fall back to inference_provider from config
        backend = backend or self.inference_provider
        
        # Check if the response indicates a blocked query
        blocked_phrases = [
            "i cannot assist with that type of request",
            "i cannot assist with that request",
            "i'm unable to help with that",
            "i cannot help with that"
        ]
        
        # If the response contains any of the blocked phrases, mark as blocked
        is_blocked = blocked or any(phrase in response.lower() for phrase in blocked_phrases)
        
        log_data = {
            "timestamp": timestamp.isoformat(),
            "query": query,
            "response": response,
            "backend": backend,
            "blocked": is_blocked,
            "ip": {
                **ip_metadata,
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
        
        if session_id:
            log_data["session_id"] = session_id
        
        if user_id:
            log_data["user_id"] = user_id

        await self._log_to_elasticsearch(log_data, timestamp, query, response, backend, is_blocked, ip_metadata, api_key, session_id, user_id)

    async def _log_to_elasticsearch(
        self,
        log_data: Dict[str, Any],
        timestamp: datetime,
        query: str,
        response: str,
        backend: str,
        blocked: bool,
        ip_metadata: IPMetadata,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
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
                    "originalValue": ip_metadata["originalValue"]
                }
            }
            
            # Add optional fields if provided
            if api_key:
                document["api_key"] = {
                    "key": api_key,  # Log unmasked API key to Elasticsearch
                    "timestamp": timestamp.isoformat()
                }
            
            if session_id:
                document["session_id"] = session_id
            
            if user_id:
                document["user_id"] = user_id
            if self.verbose:
                logger.info(f"Indexing document to Elasticsearch: {json.dumps(document, indent=2)}")
            index_result = await self.es_client.index(
                index=self.config["internal_services"]["elasticsearch"]["index"],
                document=document,
                refresh="wait_for"  # Changed from True to "wait_for" for ES 9.0.2 compatibility
            )
            if self.verbose:
                logger.info(f"Elasticsearch indexing result: {index_result}")
                # Optional verification step
                verify_doc = await self.es_client.get(
                    index=self.config["internal_services"]["elasticsearch"]["index"],
                    id=index_result["_id"]
                )
                logger.info(f"Document verification: {verify_doc}")
        except ApiError as e:
            # Handle specific Elasticsearch API errors
            logger.error(f"Elasticsearch API error: {e.info if hasattr(e, 'info') else e}", exc_info=True)
            await self._handle_elasticsearch_error(e)
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
                        # Try to recreate the index
                        await self._setup_elasticsearch_index()
                    else:
                        index_settings = await self.es_client.indices.get(
                            index=self.config["internal_services"]["elasticsearch"]["index"]
                        )
                        logger.info(f"Index settings: {index_settings}")
            except Exception as diag_error:
                logger.error(f"Error during Elasticsearch diagnostics: {diag_error}", exc_info=True)

    async def _handle_elasticsearch_error(self, error: Exception) -> None:
        """Handle specific Elasticsearch errors and attempt recovery."""
        error_str = str(error)
        
        if "index_not_found_exception" in error_str.lower():
            logger.warning("Index not found, attempting to recreate...")
            try:
                await self._setup_elasticsearch_index()
                logger.info("Successfully recreated Elasticsearch index")
            except Exception as e:
                logger.error(f"Failed to recreate index: {e}")
        elif "version_conflict" in error_str.lower():
            logger.warning("Version conflict detected, document may have been updated concurrently")
        elif "circuit_breaking_exception" in error_str.lower():
            logger.error("Elasticsearch circuit breaker triggered - system under memory pressure")
        else:
            logger.error(f"Unhandled Elasticsearch error type: {error_str}")
    
    async def close(self) -> None:
        """Close the Elasticsearch client if open."""
        if self.es_client:
            try:
                await self.es_client.close()
                logger.info("Elasticsearch client closed successfully")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch client: {e}")
