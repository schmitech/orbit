"""
Elasticsearch Audit Storage Strategy
=====================================

Implementation of AuditStorageStrategy for Elasticsearch backend.
"""

import os
import asyncio
import logging
from typing import Dict, Any, Optional, List

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, compress_text, decompress_text

logger = logging.getLogger(__name__)


def extract_client_ip(ip_value: str) -> tuple[str, str | None]:
    """
    Extract the client IP from a potentially comma-separated list of IPs.

    When behind proxies like Cloudflare, X-Forwarded-For contains multiple IPs:
    "client_ip, proxy1_ip, proxy2_ip, ..."

    The first IP is the original client IP.

    Args:
        ip_value: A single IP or comma-separated list of IPs

    Returns:
        Tuple of (client_ip, full_chain or None if single IP)
    """
    if not ip_value:
        return "127.0.0.1", None

    ip_value = ip_value.strip()

    # Check if there are multiple IPs
    if ',' in ip_value:
        ips = [ip.strip() for ip in ip_value.split(',')]
        # First IP is the original client IP
        client_ip = ips[0] if ips else "127.0.0.1"
        return client_ip, ip_value  # Return client IP and full chain
    else:
        return ip_value, None  # Single IP, no chain


class ElasticsearchAuditStrategy(AuditStorageStrategy):
    """
    Elasticsearch implementation of audit storage.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Elasticsearch audit strategy.

        Args:
            config: Application configuration dictionary
        """
        super().__init__(config)
        self._es_client: Optional[AsyncElasticsearch] = None
        # Use audit collection_name as the ES index name (separate from logger's 'orbit' index)
        self._index_name = config.get('internal_services', {}).get('audit', {}).get(
            'collection_name', 'audit_logs'
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
            # Create Elasticsearch client with ES 9.0.2 options.
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
            logger.debug("Connected to Elasticsearch for audit storage")

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
                logger.debug(f"Creating audit index: {self._index_name}")
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
                            "provider": {"type": "keyword"},
                            "blocked": {"type": "boolean"},
                            "ip": {"type": "ip"},
                            "ip_chain": {"type": "keyword"},  # Full IP chain when behind proxies (e.g., Cloudflare)
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
                            "user_id": {"type": "keyword"},
                            "adapter_name": {"type": "keyword"},
                            "model": {"type": "keyword"},
                            **self._usage_mapping_properties(),
                        }
                    }
                )
                logger.debug(f"Created audit index: {self._index_name}")
            else:
                logger.debug(f"Using existing audit index: {self._index_name}")
                await self._ensure_usage_mapping()

        except Exception as e:
            logger.error(f"Failed to setup Elasticsearch index: {e}")
            raise

    @staticmethod
    def _usage_mapping_properties() -> Dict[str, Any]:
        """Explicit mapping for the token-usage/cost fields.

        Applied on both index creation and (via put_mapping) on an existing
        index, so cost_usd is never dynamically typed from the first document
        seen — a document with an integer 0 would otherwise map it as "long"
        and silently truncate every later fractional cost to 0.
        """
        return {
            "prompt_tokens": {"type": "integer"},
            "completion_tokens": {"type": "integer"},
            "total_tokens": {"type": "integer"},
            "reasoning_tokens": {"type": "integer"},
            "cost_usd": {"type": "double"},
            "input_rate_per_1m": {"type": "double"},
            "output_rate_per_1m": {"type": "double"},
            "pricing_source": {"type": "keyword"},
        }

    async def _ensure_usage_mapping(self) -> None:
        """
        Idempotent put_mapping so pre-existing indexes get the explicit
        usage/cost field types too. put_mapping can only add new fields to an
        existing index (it cannot retype a field already indexed dynamically);
        an index that already ingested an integer 0 for cost_usd before this
        change needs a reindex to fix the type. Never blocks startup.
        """
        try:
            await self._es_client.indices.put_mapping(
                index=self._index_name,
                properties=self._usage_mapping_properties(),
            )
        except Exception as e:
            logger.warning(
                f"Failed to ensure usage-field mapping on {self._index_name} "
                f"(non-fatal, existing dynamic mapping may mistype cost_usd): {e}"
            )

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
            # Handle proxy scenarios (e.g., Cloudflare) where IP may contain multiple addresses
            if record.ip_metadata.get("type") == "local":
                ip_for_elastic = "127.0.0.1"
                ip_chain = None
            else:
                ip_for_elastic, ip_chain = extract_client_ip(record.ip)

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
                "provider": record.provider,
                "blocked": record.blocked,
                "ip": ip_for_elastic,
                "ip_metadata": record.ip_metadata
            }

            # Store full IP chain if present (for proxy scenarios like Cloudflare)
            if ip_chain:
                document["ip_chain"] = ip_chain

            # Add optional fields
            if record.api_key:
                document["api_key"] = record.api_key

            if record.session_id:
                document["session_id"] = record.session_id

            if record.user_id:
                document["user_id"] = record.user_id

            if record.adapter_name:
                document["adapter_name"] = record.adapter_name

            if record.model:
                document["model"] = record.model

            # Index document
            result = await self._es_client.index(
                index=self._index_name,
                document=document,
                refresh="wait_for"
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

    _GROUP_BY_COLUMNS = {"model", "provider", "adapter_name", "user_id"}

    async def aggregate_usage(
        self,
        since: str,
        until: str,
        bucket: str = "day",
        group_by: str = "model",
        filters: Optional[Dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> Dict[str, Any]:
        """Elasticsearch implementation: date_histogram + terms aggs, size 0."""
        if not self._initialized or not self._es_client:
            raise NotImplementedError("Elasticsearch client not available for aggregation")

        must = [{"range": {"timestamp": {"gte": since, "lt": until}}}]
        for key, value in (filters or {}).items():
            if key in {"provider", "adapter_name", "model"}:
                must.append({"term": {key: value}})
        query = {"bool": {"must": must}}

        sum_aggs = {
            "prompt_tokens": {"sum": {"field": "prompt_tokens"}},
            "completion_tokens": {"sum": {"field": "completion_tokens"}},
            "total_tokens": {"sum": {"field": "total_tokens"}},
            "cost_usd": {"sum": {"field": "cost_usd"}},
        }
        group_column = group_by if group_by in self._GROUP_BY_COLUMNS else None
        aggs = {
            **sum_aggs,
            "unpriced_requests": {"filter": {"bool": {"must": [
                {"exists": {"field": "total_tokens"}},
            ], "must_not": [{"exists": {"field": "cost_usd"}}]}}},
            "unreported_requests": {"filter": {"bool": {"must_not": [
                {"exists": {"field": "total_tokens"}}
            ]}}},
            "series": {
                "date_histogram": {
                    "field": "timestamp",
                    "calendar_interval": "hour" if bucket == "hour" else "day",
                },
                "aggs": sum_aggs,
            },
        }
        if group_column:
            aggs["groups"] = {
                "terms": {"field": group_column, "size": limit_groups, "order": {"cost_usd": "desc"}},
                "aggs": sum_aggs,
            }

        response = await self._es_client.search(
            index=self._index_name, query=query, size=0, aggs=aggs,
            track_total_hits=True,
        )
        es_aggs = response.get("aggregations", {})

        series = [
            {
                "bucket": bucket_doc.get("key_as_string") or bucket_doc.get("key"),
                "requests": bucket_doc.get("doc_count", 0),
                "prompt_tokens": bucket_doc.get("prompt_tokens", {}).get("value") or 0,
                "completion_tokens": bucket_doc.get("completion_tokens", {}).get("value") or 0,
                "total_tokens": bucket_doc.get("total_tokens", {}).get("value") or 0,
                "cost_usd": bucket_doc.get("cost_usd", {}).get("value") or 0.0,
            }
            for bucket_doc in es_aggs.get("series", {}).get("buckets", [])
        ]

        groups: List[Dict[str, Any]] = []
        if group_column:
            for bucket_doc in es_aggs.get("groups", {}).get("buckets", []):
                cost = bucket_doc.get("cost_usd", {}).get("value") or 0.0
                groups.append({
                    "key": bucket_doc.get("key"),
                    "requests": bucket_doc.get("doc_count", 0),
                    "total_tokens": bucket_doc.get("total_tokens", {}).get("value") or 0,
                    "cost_usd": cost,
                    "unpriced": cost == 0.0,
                })

        total_requests = response.get("hits", {}).get("total", {}).get("value", 0)
        return {
            "totals": {
                "requests": total_requests,
                "prompt_tokens": es_aggs.get("prompt_tokens", {}).get("value") or 0,
                "completion_tokens": es_aggs.get("completion_tokens", {}).get("value") or 0,
                "total_tokens": es_aggs.get("total_tokens", {}).get("value") or 0,
                "cost_usd": es_aggs.get("cost_usd", {}).get("value") or 0.0,
                "unpriced_requests": es_aggs.get("unpriced_requests", {}).get("doc_count", 0),
                "unreported_requests": es_aggs.get("unreported_requests", {}).get("doc_count", 0),
            },
            "series": series,
            "groups": groups,
        }

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
