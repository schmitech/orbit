"""
Elasticsearch Audit Storage Strategy
=====================================

Implementation of AuditStorageStrategy for Elasticsearch backend.
Extracted from the existing LoggerService implementation for backward compatibility.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, compress_text, decompress_text

logger = logging.getLogger(__name__)


class ElasticsearchAuditStrategy(AuditStorageStrategy):
    """
    Elasticsearch implementation of audit storage.

    This implementation is extracted from the existing LoggerService to maintain
    backward compatibility with existing Elasticsearch audit logs.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Elasticsearch audit strategy.

        Args:
            config: Application configuration dictionary
        """
        super().__init__(config)
        self._es_client: Optional[AsyncElasticsearch] = None
        self._index_name = config.get('internal_services', {}).get('elasticsearch', {}).get(
            'index', 'orbit'
        )
        # Compression setting
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the Elasticsearch storage backend.

        Creates the ES client, tests connectivity, and ensures
        the audit index exists with proper mappings.
        """
        if self._initialized:
            return

        es_config = self.config.get('internal_services', {}).get('elasticsearch', {})
        if not es_config.get('enabled', False):
            logger.warning("Elasticsearch is disabled in configuration")
            return

        # Get credentials from environment variables
        username = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
        password = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")

        if not username or not password:
            logger.warning("Elasticsearch credentials not found in environment variables")
            return

        try:
            # Create Elasticsearch client (ES 9.0.2 compatible)
            client_kwargs = {
                "basic_auth": (username, password),
                "verify_certs": False,
                "ssl_show_warn": False,
                "request_timeout": 30,
                "retry_on_timeout": True,
                "max_retries": 3,
                "http_compress": True
            }

            self._es_client = AsyncElasticsearch(
                es_config["node"],
                **client_kwargs
            )

            # Test connection
            await asyncio.wait_for(self._es_client.ping(), timeout=5.0)
            logger.info("Connected to Elasticsearch for audit storage")

            # Setup index
            await self._setup_index()

            self._initialized = True

        except asyncio.TimeoutError:
            logger.error("Elasticsearch connection timeout")
            self._es_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            self._es_client = None

    async def _setup_index(self) -> None:
        """Create the Elasticsearch index if it does not exist."""
        if not self._es_client:
            return

        try:
            index_exists = await self._es_client.indices.exists(index=self._index_name)
            if not index_exists:
                logger.info(f"Creating audit index: {self._index_name}")
                await self._es_client.indices.create(
                    index=self._index_name,
                    settings={
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "refresh_interval": "1s",
                        "analysis": {
                            "analyzer": {
                                "default": {"type": "standard"}
                            }
                        }
                    },
                    mappings={
                        "properties": {
                            "timestamp": {"type": "date"},
                            "query": {"type": "text", "analyzer": "standard"},
                            "response": {"type": "text", "analyzer": "standard"},
                            "response_compressed": {"type": "boolean"},
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
                logger.info(f"Created audit index: {self._index_name}")
            else:
                logger.debug(f"Using existing audit index: {self._index_name}")

        except Exception as e:
            logger.error(f"Failed to setup Elasticsearch index: {e}")
            raise

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in Elasticsearch.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized or not self._es_client:
            logger.debug("Elasticsearch not available, skipping audit storage")
            return False

        try:
            # Build document (matches existing LoggerService schema)
            ip_for_elastic = "127.0.0.1" if record.ip_metadata.get("type") == "local" else record.ip

            # Handle compression
            response_value = record.response
            is_compressed = record.response_compressed

            if self._compress_responses and not record.response_compressed:
                response_value = compress_text(record.response)
                is_compressed = True

            document = {
                "timestamp": record.timestamp.isoformat() if hasattr(record.timestamp, 'isoformat') else record.timestamp,
                "query": record.query,
                "response": response_value,
                "response_compressed": is_compressed,
                "backend": record.backend,
                "blocked": record.blocked,
                "ip": ip_for_elastic,
                "ip_metadata": record.ip_metadata
            }

            # Add optional fields
            if record.api_key:
                document["api_key"] = record.api_key

            if record.session_id:
                document["session_id"] = record.session_id

            if record.user_id:
                document["user_id"] = record.user_id

            # Index document
            result = await self._es_client.index(
                index=self._index_name,
                document=document,
                refresh="wait_for"  # ES 9.0.2 compatible
            )

            logger.debug(f"Stored audit record in Elasticsearch with ID: {result['_id']} (compressed: {self._compress_responses})")
            return True

        except ApiError as e:
            logger.error(f"Elasticsearch API error: {e.info if hasattr(e, 'info') else e}")
            await self._handle_error(e)
            return False
        except Exception as e:
            logger.error(f"Failed to store audit record in Elasticsearch: {e}")
            return False

    async def _handle_error(self, error: Exception) -> None:
        """Handle specific Elasticsearch errors and attempt recovery."""
        error_str = str(error)

        if "index_not_found_exception" in error_str.lower():
            logger.warning("Audit index not found, attempting to recreate...")
            try:
                await self._setup_index()
                logger.info("Successfully recreated audit index")
            except Exception as e:
                logger.error(f"Failed to recreate audit index: {e}")
        elif "circuit_breaking_exception" in error_str.lower():
            logger.error("Elasticsearch circuit breaker triggered - system under memory pressure")

    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Query audit records from Elasticsearch.

        Args:
            filters: Query criteria
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)

        Returns:
            List of matching audit records
        """
        if not self._initialized or not self._es_client:
            return []

        try:
            # Build Elasticsearch query
            must_clauses = []
            for key, value in filters.items():
                if isinstance(value, bool):
                    must_clauses.append({"term": {key: value}})
                elif isinstance(value, str):
                    must_clauses.append({"term": {key: value}})
                else:
                    must_clauses.append({"match": {key: value}})

            query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}

            # Execute search
            response = await self._es_client.search(
                index=self._index_name,
                query=query,
                sort=[{sort_by: {"order": "asc" if sort_order == 1 else "desc"}}],
                from_=offset,
                size=limit
            )

            # Extract documents and decompress if needed
            results = []
            for hit in response["hits"]["hits"]:
                doc = hit["_source"]
                doc["_id"] = hit["_id"]

                # Decompress response if needed
                if doc.get('response_compressed') and doc.get('response'):
                    try:
                        doc['response'] = decompress_text(doc['response'])
                    except Exception as e:
                        logger.warning(f"Failed to decompress response: {e}")
                        # Keep compressed response if decompression fails

                results.append(doc)

            return results

        except Exception as e:
            logger.error(f"Failed to query audit records from Elasticsearch: {e}")
            return []

    async def clear(self) -> bool:
        """
        Clear all audit records from the Elasticsearch index.

        This deletes all documents in the audit index using delete_by_query.

        Returns:
            True if cleared successfully, False otherwise
        """
        if not self._initialized or not self._es_client:
            logger.debug("Elasticsearch not available, skipping clear operation")
            return False

        try:
            # Delete all documents in the index
            response = await self._es_client.delete_by_query(
                index=self._index_name,
                query={"match_all": {}},
                refresh=True
            )
            deleted_count = response.get('deleted', 0)
            logger.info(f"Cleared {deleted_count} audit records from Elasticsearch index '{self._index_name}'")
            return True

        except Exception as e:
            logger.error(f"Error clearing audit records from Elasticsearch: {e}")
            return False

    async def close(self) -> None:
        """Close the Elasticsearch client."""
        if self._es_client:
            try:
                await self._es_client.close()
                logger.info("Elasticsearch audit client closed")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch client: {e}")

        self._initialized = False
        self._es_client = None
