"""
MongoDB Audit Storage Strategy
==============================

Implementation of AuditStorageStrategy for MongoDB backend.
Uses the existing MongoDBService/DatabaseService interface for storage operations.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, decompress_text

logger = logging.getLogger(__name__)


class MongoDBDAuditStrategy(AuditStorageStrategy):
    """
    MongoDB implementation of audit storage.

    Uses the DatabaseService abstraction to store audit records in the
    audit_logs collection with nested document structure.
    """

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the MongoDB audit strategy.

        Args:
            config: Application configuration dictionary
            database_service: Optional pre-initialized DatabaseService instance.
                             If not provided, will create one during initialize().
        """
        super().__init__(config)
        self._database_service = database_service
        self._owns_database_service = False
        self._collection_name = config.get('internal_services', {}).get('audit', {}).get(
            'collection_name', 'audit_logs'
        )
        self._indexes_created = False
        # Compression setting
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the MongoDB storage backend.

        Creates the database service if not provided, ensures connection,
        and creates required indexes on the audit_logs collection.
        """
        if self._initialized:
            return

        try:
            # Create database service if not provided
            if self._database_service is None:
                from services.database_service import create_database_service
                self._database_service = create_database_service(self.config)
                self._owns_database_service = True

            # Ensure database is initialized
            if not self._database_service._initialized:
                await self._database_service.initialize()

            # Create indexes for efficient querying
            await self._create_indexes()

            logger.debug(f"MongoDB audit storage initialized with collection: {self._collection_name}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB audit storage: {e}")
            raise

    async def _create_indexes(self) -> None:
        """Create indexes on the audit_logs collection for efficient querying."""
        if self._indexes_created:
            return

        try:
            # Index on timestamp (descending for recent-first queries)
            await self._database_service.create_index(
                self._collection_name,
                [('timestamp', -1)]
            )

            # Index on session_id for session-based queries
            await self._database_service.create_index(
                self._collection_name,
                'session_id'
            )

            # Index on user_id for user-based queries
            await self._database_service.create_index(
                self._collection_name,
                'user_id'
            )

            # Index on blocked for filtering blocked requests
            await self._database_service.create_index(
                self._collection_name,
                'blocked'
            )

            # Index on provider for provider-based queries
            await self._database_service.create_index(
                self._collection_name,
                'provider'
            )

            # Index on adapter_name for adapter-based queries
            await self._database_service.create_index(
                self._collection_name,
                'adapter_name'
            )

            # Compound index for common query patterns
            await self._database_service.create_index(
                self._collection_name,
                [('session_id', 1), ('timestamp', -1)]
            )

            # Compound indexes for usage/cost aggregation ($group by provider/model
            # within a timestamp range)
            await self._database_service.create_index(
                self._collection_name,
                [('timestamp', -1), ('provider', 1)]
            )
            await self._database_service.create_index(
                self._collection_name,
                [('timestamp', -1), ('model', 1)]
            )

            self._indexes_created = True
            logger.debug(f"Created indexes on {self._collection_name} collection")

        except Exception as e:
            logger.warning(f"Error creating indexes on {self._collection_name}: {e}")
            # Don't fail initialization if index creation fails
            # MongoDB will still work, just potentially slower

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in MongoDB.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert record to dictionary (preserving nested structure)
            # Pass compress flag to optionally compress the response
            doc = record.to_dict(compress=self._compress_responses)

            # Insert into database
            result = await self._database_service.insert_one(self._collection_name, doc)

            if result:
                logger.debug(f"Stored audit record with ID: {result} (compressed: {self._compress_responses})")
                return True
            else:
                logger.warning("Failed to store audit record - no ID returned")
                return False

        except Exception as e:
            logger.error(f"Error storing audit record in MongoDB: {e}")
            return False

    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Query audit records from MongoDB.

        Args:
            filters: Query criteria (e.g., {'session_id': 'abc', 'blocked': True})
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)

        Returns:
            List of matching audit records as dictionaries
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Query the database
            results = await self._database_service.find_many(
                collection_name=self._collection_name,
                query=filters,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)]
            )

            # Only the response field is compressed; query remains plain text.
            for record in results:
                if record.get('response_compressed'):
                    if record.get('response'):
                        try:
                            record['response'] = decompress_text(record['response'])
                        except Exception as e:
                            logger.warning(f"Failed to decompress response: {e}")
                            # Keep compressed response if decompression fails

            return results

        except Exception as e:
            logger.error(f"Error querying audit records from MongoDB: {e}")
            return []

    # Logical group-by dimension -> the document field that actually holds it.
    # Most are identity mappings; api_key is stored as a nested object, so it
    # resolves to the dotted path of the masked key inside it.
    _GROUP_BY_FIELDS = {
        "model": "model",
        "provider": "provider",
        "adapter_name": "adapter_name",
        "user_id": "user_id",
        "call_type": "call_type",
        "api_key": "api_key.key",
    }

    async def aggregate_usage(
        self,
        since: str,
        until: str,
        bucket: str = "day",
        group_by: str = "model",
        filters: Optional[Dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> Dict[str, Any]:
        """MongoDB implementation: $match + $group aggregation pipeline."""
        if not self._initialized:
            await self.initialize()

        collection = self._database_service.get_collection(self._collection_name)

        match: Dict[str, Any] = {"timestamp": {"$gte": since, "$lt": until}}
        for key, value in (filters or {}).items():
            if key in {"provider", "adapter_name", "model"}:
                match[key] = value
            elif key == "call_type":
                if value == "inference":
                    match.setdefault("$or", []).append({"call_type": {"$in": ["inference", None]}})
                else:
                    match[key] = value

        totals_pipeline = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "requests": {"$sum": 1},
                "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
                "unpriced_requests": {"$sum": {
                    "$cond": [{"$and": [
                        {"$eq": ["$cost_usd", None]}, {"$ne": ["$total_tokens", None]},
                    ]}, 1, 0]
                }},
                "unreported_requests": {"$sum": {
                    "$cond": [{"$eq": ["$total_tokens", None]}, 1, 0]
                }},
            }},
        ]
        totals_result = await collection.aggregate(totals_pipeline).to_list(length=1)
        totals_doc = totals_result[0] if totals_result else {}

        date_unit = "hour" if bucket == "hour" else "day"
        series_pipeline = [
            {"$match": match},
            {"$addFields": {"_ts": {"$dateFromString": {"dateString": "$timestamp"}}}},
            {"$group": {
                "_id": {"$dateTrunc": {"date": "$_ts", "unit": date_unit}},
                "requests": {"$sum": 1},
                "prompt_tokens": {"$sum": {"$ifNull": ["$prompt_tokens", 0]}},
                "completion_tokens": {"$sum": {"$ifNull": ["$completion_tokens", 0]}},
                "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
            }},
            {"$sort": {"_id": 1}},
        ]
        series_docs = await collection.aggregate(series_pipeline).to_list(length=10000)
        series = [
            {
                "bucket": doc["_id"].isoformat() if isinstance(doc["_id"], datetime) else str(doc["_id"]),
                "requests": doc["requests"],
                "prompt_tokens": doc["prompt_tokens"], "completion_tokens": doc["completion_tokens"],
                "total_tokens": doc["total_tokens"], "cost_usd": doc["cost_usd"],
            }
            for doc in series_docs
        ]

        groups: List[Dict[str, Any]] = []
        group_column = self._GROUP_BY_FIELDS.get(group_by)
        if group_column:
            groups_pipeline = [
                {"$match": {**match, group_column: {"$ne": None}}},
                {"$group": {
                    "_id": f"${group_column}",
                    "requests": {"$sum": 1},
                    "total_tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}},
                    "cost_usd": {"$sum": {"$ifNull": ["$cost_usd", 0]}},
                    "unpriced": {"$sum": {"$cond": [{"$eq": ["$cost_usd", None]}, 1, 0]}},
                }},
                {"$sort": {"cost_usd": -1}},
                {"$limit": limit_groups},
            ]
            group_docs = await collection.aggregate(groups_pipeline).to_list(length=limit_groups)
            groups = [
                {
                    "key": doc["_id"], "requests": doc["requests"],
                    "total_tokens": doc["total_tokens"], "cost_usd": doc["cost_usd"],
                    "unpriced": bool(doc["unpriced"]),
                }
                for doc in group_docs
            ]

        return {
            "totals": {
                "requests": totals_doc.get("requests", 0),
                "prompt_tokens": totals_doc.get("prompt_tokens", 0),
                "completion_tokens": totals_doc.get("completion_tokens", 0),
                "total_tokens": totals_doc.get("total_tokens", 0),
                "cost_usd": totals_doc.get("cost_usd", 0.0),
                "unpriced_requests": totals_doc.get("unpriced_requests", 0),
                "unreported_requests": totals_doc.get("unreported_requests", 0),
            },
            "series": series,
            "groups": groups,
        }

    async def close(self) -> None:
        """Close MongoDB audit storage resources."""
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB audit database service: {e}")

        self._initialized = False

    async def clear(self) -> bool:
        """
        Clear all audit records from the MongoDB audit_logs collection.

        Returns:
            True if cleared successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Use clear_collection to delete all records
            deleted_count = await self._database_service.clear_collection(
                self._collection_name
            )
            logger.info(f"Cleared {deleted_count} audit records from MongoDB collection '{self._collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error clearing MongoDB audit records: {e}")
            return False
