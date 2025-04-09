"""
Logger Service for handling logs to file and Elasticsearch
"""

import os
import json
import logging
import logging.handlers
import ipaddress
from typing import Dict, Any, Union, List, Optional, TypedDict
from datetime import datetime
import asyncio
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from pythonjsonlogger import jsonlogger
from elasticsearch import AsyncElasticsearch
import traceback

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _is_true_value(value: Union[str, bool]) -> bool:
    """Convert string or boolean value to boolean.
    
    Args:
        value: String or boolean value to convert
        
    Returns:
        bool: True if value is 'true', 'yes', '1', or True (case insensitive)
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('true', 'yes', '1')
    return False


class IPMetadata(TypedDict):
    """IP address metadata"""
    address: str
    type: str  # 'ipv4' | 'ipv6' | 'local' | 'unknown'
    isLocal: bool
    source: str  # 'direct' | 'proxy' | 'unknown'
    originalValue: str


class LoggerService:
    """Logger service for handling logs to file and Elasticsearch"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.es_client: Optional[AsyncElasticsearch] = None
        # Handle both string and boolean values for verbose setting
        verbose_value = config.get('general', {}).get('verbose', False)
        self.verbose = _is_true_value(verbose_value)
        
        # Get logging configuration
        self.log_config = config.get('logging', {})
        self.log_dir = self.log_config.get('file', {}).get('directory', 'logs')
        
        # Ensure logs directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Initialize JSON file logger for chat interactions
        self.file_logger = self._setup_chat_logger()
        
    def _setup_chat_logger(self) -> logging.Logger:
        """Set up the chat logger with JSON formatting and rotation"""
        chat_logger = logging.getLogger("chat_file_logger")
        chat_logger.setLevel(logging.INFO)
        chat_logger.handlers.clear()  # Clear any existing handlers
        
        # Determine log file path
        log_file = os.path.join(self.log_dir, 'chat.log')
        
        # Configure rotation settings
        rotation = self.log_config.get('file', {}).get('rotation', 'midnight')
        backup_count = self.log_config.get('file', {}).get('backup_count', 30)
        max_size_mb = self.log_config.get('file', {}).get('max_size_mb', 10)
        
        if rotation == 'midnight':
            handler = TimedRotatingFileHandler(
                filename=log_file,
                when='midnight',
                interval=1,
                backupCount=backup_count,
                encoding='utf-8'
            )
            # Append timestamp to rotated filenames
            handler.namer = lambda name: name.replace('chat.log', f'chat-{datetime.now().strftime("%Y-%m-%d")}.log')
        else:
            handler = RotatingFileHandler(
                filename=log_file,
                maxBytes=max_size_mb * 1024 * 1024,
                backupCount=backup_count,
                encoding='utf-8'
            )
        
        # Use JSON formatter for structured logging
        formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        
        chat_logger.addHandler(handler)
        chat_logger.propagate = False  # Prevent duplicate logs
        
        return chat_logger
    
    async def initialize_elasticsearch(self) -> None:
        """Initialize Elasticsearch client"""
        if not self.config.get('elasticsearch', {}).get('enabled', False):
            logger.info("Elasticsearch logging is disabled in configuration")
            return
        
        username = os.environ.get("ELASTICSEARCH_USERNAME")
        password = os.environ.get("ELASTICSEARCH_PASSWORD")
        
        if not username or not password:
            logger.warning("Elasticsearch credentials not found in environment variables")
            self.config["elasticsearch"]["enabled"] = False
            return
        
        try:
            self.es_client = AsyncElasticsearch(
                [self.config["elasticsearch"]["node"]],
                basic_auth=(username, password),
                verify_certs=False,
                request_timeout=5,  # 5-second timeout
                retry_on_timeout=True,
                max_retries=3
            )
            
            await asyncio.wait_for(self.es_client.ping(), timeout=5.0)
            logger.info("Successfully connected to Elasticsearch")
            await self._setup_elasticsearch_index()
            
        except asyncio.TimeoutError:
            logger.error("Elasticsearch connection timeout", exc_info=True)
            self.config["elasticsearch"]["enabled"] = False
            self.es_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}", exc_info=True)
            logger.info("Continuing without Elasticsearch logging...")
            self.config["elasticsearch"]["enabled"] = False
            self.es_client = None
    
    async def _setup_elasticsearch_index(self) -> None:
        """Create Elasticsearch index if it doesn't exist"""
        if not self.es_client:
            return
        
        index_name = self.config["elasticsearch"]["index"]
        
        try:
            index_exists = await self.es_client.indices.exists(index=index_name)
            
            if not index_exists:
                await self.es_client.indices.create(
                    index=index_name,
                    body={
                        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                        "mappings": {
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
                    }
                )
                logger.info(f"Created new Elasticsearch index: {index_name}")
            else:
                logger.info(f"Using existing Elasticsearch index: {index_name}")
                
        except Exception as e:
            logger.error(f"Failed to setup Elasticsearch index: {e}", exc_info=True)
            self.config["elasticsearch"]["enabled"] = False
            self.es_client = None
    
    def _format_ip_address(self, ip: Optional[Union[str, List[str]]]) -> IPMetadata:
        """Format raw IP address into metadata"""
        default_metadata: IPMetadata = {
            "address": "unknown",
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": ", ".join(ip) if isinstance(ip, list) else (ip or "unknown")
        }
        
        ip_value = ip[0] if isinstance(ip, list) and ip else ip
        if not ip_value:
            return default_metadata
        
        clean_ip = ip_value.strip() if isinstance(ip_value, str) else ""
        
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
        """Determine if an IP address is local/private"""
        try:
            return ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback
        except ValueError:
            return False
    
    async def log_conversation(self, query: str, response: str, ip: Optional[str] = None, 
                               backend: str = "ollama", blocked: bool = False, api_key: Optional[str] = None) -> None:
        """Log chat interaction to file and Elasticsearch"""
        timestamp = datetime.now()
        ip_metadata = self._format_ip_address(ip)
        
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
            "elasticsearch_status": "enabled" if (self.config.get("elasticsearch", {}).get("enabled", False) and self.es_client) else "disabled"
        }
        
        # Add API key information if provided
        if api_key:
            log_data["api_key"] = {
                "key": api_key[:5] + "..." if api_key else None,  # Only log first 5 chars for security
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
        """Log data to Elasticsearch"""
        if not (self.config.get("elasticsearch", {}).get("enabled", False) and self.es_client):
            if self.verbose:
                logger.info("\n=== Elasticsearch Logging Skipped ===")
                logger.info(f"Elasticsearch enabled: {self.config.get('elasticsearch', {}).get('enabled', False)}")
                logger.info(f"Elasticsearch client available: {self.es_client is not None}")
            return
        
        try:
            if self.verbose:
                logger.info("\n=== Elasticsearch Logging ===")
                logger.info(f"Attempting to index document to: {self.config['elasticsearch']['index']}")
            
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
                logger.info(f"Document to index: {json.dumps(document, indent=2)}")
            
            index_result = await self.es_client.index(
                index=self.config["elasticsearch"]["index"],
                document=document,
                refresh=True  # Make document immediately searchable
            )
            
            if self.verbose:
                logger.info(f"Elasticsearch indexing result: {index_result}")
                verify_doc = await self.es_client.get(
                    index=self.config["elasticsearch"]["index"],
                    id=index_result["_id"]
                )
                logger.info(f"Document verification: {verify_doc}")
                
        except Exception as e:
            logger.error(f"Failed to log to Elasticsearch: {e}", exc_info=True)
            try:
                if self.es_client:
                    index_exists = await self.es_client.indices.exists(
                        index=self.config["elasticsearch"]["index"]
                    )
                    logger.info(f"Index exists check: {self.config['elasticsearch']['index']} - {index_exists}")
                    if not index_exists:
                        logger.error("Index does not exist! This should not happen as we create it at startup.")
                    index_settings = await self.es_client.indices.get(
                        index=self.config["elasticsearch"]["index"]
                    )
                    logger.info(f"Index settings: {index_settings}")
            except Exception as diag_error:
                logger.error(f"Error during diagnostics: {diag_error}", exc_info=True)
    
    async def close(self) -> None:
        """Close connections and resources"""
        if self.es_client:
            await self.es_client.close()
