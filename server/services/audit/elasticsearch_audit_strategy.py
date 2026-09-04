"""
Elasticsearch Audit Storage Strategy
=====================================

Implementation of AuditStorageStrategy for Elasticsearch backend.
"""

import os
import asyncio
import logging
from typing import Any, Optional

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

    def __init__(self, config: dict[str, Any]):
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
                                    "timestamp": {"type": "date"},
                                    "id": {"type": "keyword"}
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
    def _usage_mapping_properties() -> dict[str, Any]:
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
            "cached_prompt_tokens": {"type": "integer"},
            "cost_usd": {"type": "double"},
            "input_rate_per_1m": {"type": "double"},
            "output_rate_per_1m": {"type": "double"},
            "pricing_source": {"type": "keyword"},
            "usage_unit": {"type": "keyword"},
            # Explicitly "double", not left to dynamic mapping — a first
            # document with an integer quantity (e.g. "images": 1) would
            # otherwise map this as "long" and silently truncate later
            # fractional quantities (e.g. "seconds": 2.5), the same trap
            # cost_usd above is guarding against.
            "usage_quantity": {"type": "double"},
            "call_type": {"type": "keyword"},
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

        try:
            # Adds api_key.id to pre-existing indexes created before Phase 4
            # of docs/roadmap/costs-by-api-key.md — put_mapping can add a new
            # sub-field to an already-mapped object field without a reindex.
            await self._es_client.indices.put_mapping(
                index=self._index_name,
                properties={"api_key": {"properties": {"id": {"type": "keyword"}}}},
            )
        except Exception as e:
            logger.warning(
                f"Failed to ensure api_key.id mapping on {self._index_name} "
                f"(non-fatal, the api_key group_by/filter falls back to the masked key): {e}"
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

            if record.call_type:
                document["call_type"] = record.call_type

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
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> list[dict[str, Any]]:
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

    # Logical group-by dimension -> the indexed field that actually holds it.
    # Most are identity mappings; api_key is handled separately (see
    # _fetch_api_key_masked_to_id_map / the groups terms script below).
    _GROUP_BY_FIELDS = {
        "model": "model",
        "provider": "provider",
        "adapter_name": "adapter_name",
        "user_id": "user_id",
        "call_type": "call_type",
    }

    def _resolve_dimension_field(self, dimension: str) -> Optional[str]:
        """Field backing a logical dimension, for dimensions other than
        api_key (which is resolved via _fetch_api_key_masked_to_id_map)."""
        return self._GROUP_BY_FIELDS.get(dimension)

    # Dimensions accepted in `filters`. Reuses _resolve_dimension_field for
    # the logical-name -> field mapping; user_id is groupable but not (yet)
    # filterable, so it is deliberately excluded here.
    _FILTERABLE_DIMENSIONS = {"provider", "adapter_name", "model", "call_type", "api_key"}

    async def _fetch_api_key_masked_to_id_map(self) -> dict[str, str]:
        """Map every masked key that has EVER written an id-bearing row
        (anywhere in the index, not just the current query's window) to
        that id. Used to resolve legacy rows (masked value only) onto the
        same identity as newer rows for the same underlying key — without
        this, a key with both pre- and post-Phase-4 rows would split into
        two groups, and an id-filtered view would miss its legacy spend.

        Best-effort: an aggregation failure (e.g. api_key.id unmapped on an
        older index whose put_mapping backfill failed) returns an empty
        map, degrading to the masked-value-only behavior rather than
        breaking the whole request.
        """
        try:
            response = await self._es_client.search(
                index=self._index_name, size=0,
                aggs={"by_masked": {
                    "terms": {"field": "api_key.key", "size": 10000},
                    "aggs": {"resolved_id": {"terms": {"field": "api_key.id", "size": 1}}},
                }},
            )
        except Exception as e:
            logger.warning(f"Failed to build api_key masked-value-to-id map, falling back to masked-only: {e}")
            return {}

        masked_to_id: dict[str, str] = {}
        for bucket in response.get("aggregations", {}).get("by_masked", {}).get("buckets", []):
            id_buckets = bucket.get("resolved_id", {}).get("buckets", [])
            if id_buckets:
                masked_to_id[bucket["key"]] = id_buckets[0]["key"]
        return masked_to_id

    @staticmethod
    def _api_key_terms_script(masked_to_id: dict[str, str]) -> dict[str, Any]:
        """Painless script for the "groups" terms agg when group_by ==
        "api_key": prefer this doc's own stable id; else resolve its masked
        key through `masked_to_id` (built from the whole index, so a legacy
        row lands in the same bucket as this key's newer, id-bearing rows);
        else fall back to the masked key itself. `doc.containsKey` guards
        every field access so an older index whose api_key.id mapping
        backfill (Phase 4's put_mapping) never succeeded still falls back
        cleanly instead of throwing "no field found"."""
        return {
            "source": (
                "if (doc.containsKey('api_key.id') && doc['api_key.id'].size() != 0) "
                "{ return doc['api_key.id'].value; } "
                "if (!doc.containsKey('api_key.key') || doc['api_key.key'].size() == 0) { return null; } "
                "def keyVal = doc['api_key.key'].value; "
                "def resolved = params.maskedToId.get(keyVal); "
                "return resolved != null ? resolved : keyVal;"
            ),
            "lang": "painless",
            "params": {"maskedToId": masked_to_id},
        }

    async def aggregate_usage(
        self,
        since: str,
        until: str,
        bucket: str = "day",
        group_by: str = "model",
        filters: Optional[dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> dict[str, Any]:
        """Elasticsearch implementation: date_histogram + terms aggs, size 0."""
        if not self._initialized or not self._es_client:
            raise NotImplementedError("Elasticsearch client not available for aggregation")

        # The api_key dimension needs the whole-index masked-key/id map
        # whether it's the active group_by or just a filter — otherwise a
        # legacy row for a key that's since written an id-bearing row
        # wouldn't be reachable by that id.
        needs_api_key_resolution = group_by == "api_key" or "api_key" in (filters or {})
        masked_to_id = await self._fetch_api_key_masked_to_id_map() if needs_api_key_resolution else {}
        id_to_masked: dict[str, list[str]] = {}
        for masked, key_id in masked_to_id.items():
            id_to_masked.setdefault(key_id, []).append(masked)

        must = [{"range": {"timestamp": {"gte": since, "lt": until}}}]
        for key, value in (filters or {}).items():
            if key not in self._FILTERABLE_DIMENSIONS:
                continue
            if key == "api_key":
                # `value` may be a stable id or a masked key (whichever a
                # group row's "key" was). Match it directly on both fields,
                # plus: any masked key known to resolve to `value` (in case
                # `value` is an id and the matching row is a legacy,
                # id-less one), and the id `value` resolves to if `value`
                # is itself a masked key that has since gotten one.
                candidate_ids = {value}
                if value in masked_to_id and masked_to_id[value]:
                    candidate_ids.add(masked_to_id[value])
                candidate_keys = set(id_to_masked.get(value, [])) | {value}
                must.append({"bool": {"should": [
                    {"terms": {"api_key.id": sorted(candidate_ids)}},
                    {"terms": {"api_key.key": sorted(candidate_keys)}},
                ], "minimum_should_match": 1}})
                continue
            field = self._resolve_dimension_field(key)
            must.append({"term": {field: value}})
        query = {"bool": {"must": must}}

        sum_aggs = {
            "prompt_tokens": {"sum": {"field": "prompt_tokens"}},
            "completion_tokens": {"sum": {"field": "completion_tokens"}},
            "total_tokens": {"sum": {"field": "total_tokens"}},
            "cost_usd": {"sum": {"field": "cost_usd"}},
        }
        group_column = self._resolve_dimension_field(group_by)
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
        if group_by == "api_key":
            aggs["groups"] = {
                "terms": {
                    "script": self._api_key_terms_script(masked_to_id),
                    "size": limit_groups, "order": {"cost_usd": "desc"},
                },
                "aggs": sum_aggs,
            }
        elif group_column:
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

        groups: list[dict[str, Any]] = []
        if group_by == "api_key" or group_column:
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
