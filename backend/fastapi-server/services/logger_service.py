"""
Logger Service for handling logs to file and Elasticsearch
"""

import os
import json
import logging
import ipaddress
from typing import Dict, Any, Union, List, Optional, TypedDict
from datetime import datetime
import asyncio
from logging.handlers import TimedRotatingFileHandler
from pythonjsonlogger import jsonlogger
from elasticsearch import AsyncElasticsearch, NotFoundError, TransportError
import traceback
import socket

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


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
        self.es_client = None
        self.verbose = config.get('general', {}).get('verbose', 'false').lower() in ('true', 'yes', 'y', '1')
        
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        # Initialize JSON file logger
        self.file_logger = self._setup_file_logger()
        
    def _setup_file_logger(self) -> logging.Logger:
        """Set up the file logger with JSON formatting and daily rotation"""
        log_handler = TimedRotatingFileHandler(
            filename='logs/chat.log',
            when='midnight',
            interval=1,
            backupCount=14,  # Keep logs for 14 days
            encoding='utf-8'
        )
        
        # Add timestamp to filename when rotating
        log_handler.namer = lambda name: name.replace('chat.log', '') + f'chat-{datetime.now().strftime("%Y-%m-%d")}.log'
        
        # Set up JSON formatter
        formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(message)s')
        log_handler.setFormatter(formatter)
        
        # Create a dedicated logger for file output
        file_logger = logging.getLogger('chat_file_logger')
        file_logger.setLevel(logging.INFO)
        file_logger.addHandler(log_handler)
        file_logger.propagate = False  # Prevent duplicate logs
        
        return file_logger
    
    async def initialize_elasticsearch(self) -> None:
        """Initialize Elasticsearch client"""
        # Skip if elasticsearch is disabled
        if not self.config.get('elasticsearch', {}).get('enabled', False):
            logger.info("Elasticsearch logging is disabled in configuration")
            return
        
        # Check for credentials
        username = os.environ.get('ELASTICSEARCH_USERNAME')
        password = os.environ.get('ELASTICSEARCH_PASSWORD')
        
        if not username or not password:
            logger.warning("Elasticsearch credentials not found in environment variables")
            self.config['elasticsearch']['enabled'] = False
            return
        
        try:
            # Create Elasticsearch client
            self.es_client = AsyncElasticsearch(
                [self.config['elasticsearch']['node']],
                basic_auth=(username, password),
                verify_certs=False,
                request_timeout=5,  # 5 second timeout
                retry_on_timeout=True,
                max_retries=3
            )
            
            # Test connection
            await asyncio.wait_for(self.es_client.ping(), timeout=5.0)
            logger.info("Successfully connected to Elasticsearch")
            
            # Setup index
            await self._setup_elasticsearch_index()
            
        except asyncio.TimeoutError:
            logger.error("Elasticsearch connection timeout")
            self.config['elasticsearch']['enabled'] = False
            self.es_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {str(e)}")
            logger.info("Continuing without Elasticsearch logging...")
            self.config['elasticsearch']['enabled'] = False
            self.es_client = None
    
    async def _setup_elasticsearch_index(self) -> None:
        """Create Elasticsearch index if it doesn't exist"""
        if not self.es_client:
            return
        
        index_name = self.config['elasticsearch']['index']
        
        try:
            # Check if index exists
            index_exists = await self.es_client.indices.exists(index=index_name)
            
            if not index_exists:
                # Create index with settings
                await self.es_client.indices.create(
                    index=index_name,
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0
                        },
                        "mappings": {
                            "properties": {
                                "timestamp": {"type": "date"},
                                "query": {"type": "text"},
                                "response": {"type": "text"},
                                "backend": {"type": "keyword"},
                                "blocked": {"type": "boolean"},
                                "ip": {"type": "ip"},  # Main IP field
                                "ip_metadata": {  # Additional IP metadata
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
            logger.error(f"Failed to setup Elasticsearch index: {str(e)}")
            self.config['elasticsearch']['enabled'] = False
            self.es_client = None
    
    def _format_ip_address(self, ip: Optional[Union[str, List[str]]]) -> IPMetadata:
        """Format raw IP address into metadata"""
        # Default metadata
        metadata: IPMetadata = {
            "address": "unknown",
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": ', '.join(ip) if isinstance(ip, list) else (ip or "unknown")
        }
        
        # Handle array from X-Forwarded-For
        ip_to_process = ip[0] if isinstance(ip, list) and len(ip) > 0 else ip
        
        if not ip_to_process:
            return metadata
        
        # Clean the IP address
        clean_ip = ip_to_process.strip() if isinstance(ip_to_process, str) else ""
        
        # Detect and format IPv6 localhost
        if clean_ip == "::1" or clean_ip == "::ffff:127.0.0.1":
            return {
                "address": "localhost",
                "type": "local",
                "isLocal": True,
                "source": "direct",
                "originalValue": clean_ip
            }
        
        # Detect and format IPv4 localhost
        if clean_ip == "127.0.0.1" or clean_ip.startswith("::ffff:127."):
            return {
                "address": "localhost",
                "type": "local",
                "isLocal": True,
                "source": "direct",
                "originalValue": clean_ip
            }
        
        # Handle IPv4-mapped IPv6 addresses
        if clean_ip.startswith("::ffff:"):
            clean_ip = clean_ip[7:]
            metadata["type"] = "ipv4"
        elif ":" in clean_ip:
            metadata["type"] = "ipv6"
        else:
            metadata["type"] = "ipv4"
        
        metadata["address"] = clean_ip
        metadata["isLocal"] = self._is_local_ip(clean_ip)
        metadata["source"] = "proxy" if isinstance(ip, list) else "direct"
        
        return metadata
    
    def _is_local_ip(self, ip: str) -> bool:
        """Determine if an IP address is local/private"""
        try:
            # Parse the IP address
            ip_obj = ipaddress.ip_address(ip)
            
            # Check if it's a private or loopback address
            return ip_obj.is_private or ip_obj.is_loopback
        except ValueError:
            # If parsing fails, default to False
            return False
    
    async def log_conversation(self, query: str, response: str, ip: Optional[str] = None, 
                         backend: str = "ollama", blocked: bool = False) -> None:
        """Log chat interaction to file and Elasticsearch"""
        timestamp = datetime.now()
        ip_metadata = self._format_ip_address(ip)
        
        # Prepare log data
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
            "elasticsearch_status": "enabled" if (
                self.config.get('elasticsearch', {}).get('enabled', False) and self.es_client
            ) else "disabled"
        }
        
        # Always log to file
        self.file_logger.info("Chat Interaction", extra=log_data)
        
        # Log to Elasticsearch if enabled and client is available
        await self._log_to_elasticsearch(log_data, timestamp, query, response, backend, blocked, ip_metadata)
    
    async def _log_to_elasticsearch(self, log_data: Dict[str, Any], timestamp: datetime, 
                             query: str, response: str, backend: str, 
                             blocked: bool, ip_metadata: IPMetadata) -> None:
        """Log data to Elasticsearch"""
        if not (self.config.get('elasticsearch', {}).get('enabled', False) and self.es_client):
            if self.verbose:
                logger.info("\n=== Elasticsearch Logging Skipped ===")
                logger.info(f"Elasticsearch enabled: {self.config.get('elasticsearch', {}).get('enabled', False)}")
                logger.info(f"Elasticsearch client available: {self.es_client is not None}")
            return
        
        try:
            if self.verbose:
                logger.info("\n=== Elasticsearch Logging ===")
                logger.info(f"Attempting to index document to: {self.config['elasticsearch']['index']}")
            
            # Convert localhost/friendly names to actual IP for Elasticsearch storage
            ip_for_elastic = "127.0.0.1" if ip_metadata["type"] == "local" else ip_metadata["address"]
            
            # Prepare document
            document = {
                "timestamp": timestamp.isoformat(),
                "query": query,
                "response": response,
                "backend": backend,
                "blocked": blocked,
                "ip": ip_for_elastic,  # Store actual IP address
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
            
            # Index document
            index_result = await self.es_client.index(
                index=self.config['elasticsearch']['index'],
                document=document,
                refresh=True  # Make document immediately searchable
            )
            
            if self.verbose:
                logger.info(f"Elasticsearch indexing result: {index_result}")
                
                # Verify document exists
                verify_doc = await self.es_client.get(
                    index=self.config['elasticsearch']['index'],
                    id=index_result["_id"]
                )
                logger.info(f"Document verification: {verify_doc}")
                
        except Exception as e:
            logger.error(f"Failed to log to Elasticsearch: {str(e)}")
            logger.error(f"Exception details: {traceback.format_exc()}")
            
            # Try to diagnose the issue
            try:
                if self.es_client:
                    index_exists = await self.es_client.indices.exists(
                        index=self.config['elasticsearch']['index']
                    )
                    
                    logger.info(f"Index exists check: {self.config['elasticsearch']['index']} - {index_exists}")
                    
                    if not index_exists:
                        logger.error("Index does not exist! This should not happen as we create it at startup.")
                    
                    index_settings = await self.es_client.indices.get(
                        index=self.config['elasticsearch']['index']
                    )
                    
                    logger.info(f"Index settings: {index_settings}")
            except Exception as diag_error:
                logger.error(f"Error during diagnostics: {str(diag_error)}")
    
    async def close(self) -> None:
        """Close connections and resources"""
        if self.es_client:
            await self.es_client.close()