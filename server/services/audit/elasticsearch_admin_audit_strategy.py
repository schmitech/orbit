"""
Elasticsearch Admin Audit Storage Strategy
==========================================

Stores AdminAuditRecord documents into an Elasticsearch index
(default: `audit_admin_logs`) with explicit field mappings.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ApiError

from .admin_audit_storage_strategy import AdminAuditRecord, AdminAuditStorageStrategy
from .elasticsearch_audit_strategy import extract_client_ip

logger = logging.getLogger(__name__)


class ElasticsearchAdminAuditStrategy(AdminAuditStorageStrategy):
    """Elasticsearch implementation of admin audit storage."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._es_client: Optional[AsyncElasticsearch] = None
        admin_cfg = (
            config.get("internal_services", {})
            .get("audit", {})
            .get("admin_events", {})
        )
        self._index_name = admin_cfg.get("collection_name", "audit_admin_logs")

    async def initialize(self) -> None:
        if self._initialized:
            return

        es_config = self.config.get("internal_services", {}).get("elasticsearch", {})
        if not es_config.get("enabled", False):
            logger.warning("Elasticsearch is disabled in configuration")
            return

        username = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_USERNAME")
        password = os.environ.get("INTERNAL_SERVICES_ELASTICSEARCH_PASSWORD")

        if not username or not password:
            logger.warning("Elasticsearch credentials not found in environment variables")
            return

        try:
            self._es_client = AsyncElasticsearch(
                es_config["node"],
                basic_auth=(username, password),
                verify_certs=False,
                ssl_show_warn=False,
                request_timeout=30,
                retry_on_timeout=True,
                max_retries=3,
                http_compress=True,
            )

            await asyncio.wait_for(self._es_client.ping(), timeout=5.0)
            logger.info("Connected to Elasticsearch for admin audit storage")

            await self._setup_index()
            self._initialized = True

        except asyncio.TimeoutError:
            logger.error("Elasticsearch connection timeout (admin audit)")
            self._es_client = None
        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch for admin audit: {e}")
            self._es_client = None

    async def _setup_index(self) -> None:
        if not self._es_client:
            return
        try:
            exists = await self._es_client.indices.exists(index=self._index_name)
            if exists:
                logger.debug(f"Using existing admin audit index: {self._index_name}")
                return

            logger.info(f"Creating admin audit index: {self._index_name}")
            await self._es_client.indices.create(
                index=self._index_name,
                settings={
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "refresh_interval": "1s",
                },
                mappings={
                    "properties": {
                        "timestamp": {"type": "date"},
                        "event_type": {"type": "keyword"},
                        "action": {"type": "keyword"},
                        "resource_type": {"type": "keyword"},
                        "resource_id": {"type": "keyword"},
                        "actor_type": {"type": "keyword"},
                        "actor_id": {"type": "keyword"},
                        "actor_username": {"type": "keyword"},
                        "method": {"type": "keyword"},
                        "path": {"type": "keyword"},
                        "status_code": {"type": "integer"},
                        "success": {"type": "boolean"},
                        "ip": {"type": "ip"},
                        "ip_chain": {"type": "keyword"},
                        "ip_metadata": {
                            "properties": {
                                "type": {"type": "keyword"},
                                "isLocal": {"type": "boolean"},
                                "source": {"type": "keyword"},
                                "originalValue": {"type": "keyword"},
                            }
                        },
                        "user_agent": {"type": "keyword"},
                        "error_message": {"type": "text"},
                        "request_summary": {"type": "object", "enabled": True},
                    }
                },
            )
            logger.info(f"Created admin audit index: {self._index_name}")
        except Exception as e:
            logger.error(f"Failed to setup Elasticsearch admin audit index: {e}")
            raise

    async def store(self, record: AdminAuditRecord) -> bool:
        if not self._initialized or not self._es_client:
            logger.debug("Elasticsearch not available, skipping admin audit storage")
            return False

        try:
            if record.ip_metadata.get("type") == "local":
                ip_for_elastic = "127.0.0.1"
                ip_chain = None
            else:
                ip_for_elastic, ip_chain = extract_client_ip(record.ip)

            document = record.to_dict()
            document["ip"] = ip_for_elastic
            if ip_chain:
                document["ip_chain"] = ip_chain

            result = await self._es_client.index(
                index=self._index_name,
                document=document,
                refresh="wait_for",
            )
            logger.debug(f"Stored admin audit record in Elasticsearch: {result['_id']}")
            return True

        except ApiError as e:
            logger.error(f"Elasticsearch API error (admin audit): {e.info if hasattr(e, 'info') else e}")
            return False
        except Exception as e:
            logger.error(f"Failed to store admin audit record in Elasticsearch: {e}")
            return False

    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "timestamp",
        sort_order: int = -1,
    ) -> List[Dict[str, Any]]:
        if not self._initialized or not self._es_client:
            return []

        try:
            must_clauses = []
            for key, value in filters.items():
                if isinstance(value, bool):
                    must_clauses.append({"term": {key: value}})
                elif isinstance(value, str):
                    must_clauses.append({"term": {key: value}})
                else:
                    must_clauses.append({"match": {key: value}})

            query = {"bool": {"must": must_clauses}} if must_clauses else {"match_all": {}}

            response = await self._es_client.search(
                index=self._index_name,
                query=query,
                sort=[{sort_by: {"order": "asc" if sort_order == 1 else "desc"}}],
                from_=offset,
                size=limit,
            )

            results = []
            for hit in response["hits"]["hits"]:
                doc = hit["_source"]
                doc["_id"] = hit["_id"]
                results.append(doc)
            return results

        except Exception as e:
            logger.error(f"Failed to query admin audit records from Elasticsearch: {e}")
            return []

    async def clear(self) -> bool:
        if not self._initialized or not self._es_client:
            return False
        try:
            response = await self._es_client.delete_by_query(
                index=self._index_name,
                query={"match_all": {}},
                refresh=True,
            )
            deleted_count = response.get("deleted", 0)
            logger.info(
                f"Cleared {deleted_count} admin audit records from Elasticsearch index '{self._index_name}'"
            )
            return True
        except Exception as e:
            logger.error(f"Error clearing admin audit records from Elasticsearch: {e}")
            return False

    async def close(self) -> None:
        if self._es_client:
            try:
                await self._es_client.close()
                logger.info("Elasticsearch admin audit client closed")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch admin audit client: {e}")
        self._initialized = False
        self._es_client = None
