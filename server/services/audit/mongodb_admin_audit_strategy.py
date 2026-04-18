"""
MongoDB Admin Audit Storage Strategy
====================================

Stores AdminAuditRecord documents into the `audit_admin_logs` MongoDB
collection via the shared DatabaseService abstraction.
"""

import logging
from typing import Any, Dict, List

from .admin_audit_storage_strategy import AdminAuditRecord, AdminAuditStorageStrategy

logger = logging.getLogger(__name__)


class MongoDBAdminAuditStrategy(AdminAuditStorageStrategy):
    """MongoDB implementation of admin audit storage."""

    def __init__(self, config: Dict[str, Any], database_service=None):
        super().__init__(config)
        self._database_service = database_service
        self._owns_database_service = False
        admin_cfg = (
            config.get("internal_services", {})
            .get("audit", {})
            .get("admin_events", {})
        )
        self._collection_name = admin_cfg.get("collection_name", "audit_admin_logs")
        self._indexes_created = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        try:
            if self._database_service is None:
                from services.database_service import create_database_service
                self._database_service = create_database_service(self.config)
                self._owns_database_service = True

            if not self._database_service._initialized:
                await self._database_service.initialize()

            await self._create_indexes()

            logger.info(
                f"MongoDB admin audit storage initialized with collection: {self._collection_name}"
            )
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize MongoDB admin audit storage: {e}")
            raise

    async def _create_indexes(self) -> None:
        if self._indexes_created:
            return

        try:
            await self._database_service.create_index(self._collection_name, [("timestamp", -1)])
            await self._database_service.create_index(self._collection_name, "actor_id")
            await self._database_service.create_index(self._collection_name, "event_type")
            await self._database_service.create_index(self._collection_name, "resource_type")
            await self._database_service.create_index(self._collection_name, "success")
            await self._database_service.create_index(
                self._collection_name, [("actor_id", 1), ("timestamp", -1)]
            )
            self._indexes_created = True
            logger.debug(f"Created indexes on {self._collection_name} collection")
        except Exception as e:
            logger.warning(f"Error creating indexes on {self._collection_name}: {e}")

    async def store(self, record: AdminAuditRecord) -> bool:
        if not self._initialized:
            await self.initialize()

        try:
            doc = record.to_dict()
            result = await self._database_service.insert_one(self._collection_name, doc)
            if result:
                logger.debug(f"Stored admin audit record with ID: {result}")
                return True
            logger.warning("Failed to store admin audit record - no ID returned")
            return False
        except Exception as e:
            logger.error(f"Error storing admin audit record in MongoDB: {e}")
            return False

    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "timestamp",
        sort_order: int = -1,
    ) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        try:
            return await self._database_service.find_many(
                collection_name=self._collection_name,
                query=filters,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)],
            )
        except Exception as e:
            logger.error(f"Error querying admin audit records from MongoDB: {e}")
            return []

    async def close(self) -> None:
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:
                logger.error(f"Error closing MongoDB admin audit database service: {e}")
        self._initialized = False

    async def clear(self) -> bool:
        if not self._initialized:
            await self.initialize()
        try:
            deleted_count = await self._database_service.clear_collection(self._collection_name)
            logger.info(
                f"Cleared {deleted_count} admin audit records from MongoDB collection '{self._collection_name}'"
            )
            return True
        except Exception as e:
            logger.error(f"Error clearing MongoDB admin audit records: {e}")
            return False
