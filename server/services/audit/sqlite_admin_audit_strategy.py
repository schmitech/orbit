"""
SQLite Admin Audit Storage Strategy
===================================

Stores AdminAuditRecord rows into the `audit_admin_logs` SQLite table via the
shared DatabaseService abstraction.
"""

import json
import logging
from typing import Any, Dict, List

from .admin_audit_storage_strategy import AdminAuditRecord, AdminAuditStorageStrategy
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class SQLiteAdminAuditStrategy(AdminAuditStorageStrategy):
    """SQLite implementation of admin audit storage."""

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

            # The audit_admin_logs table is defined in sqlite_service.py's schema
            # and auto-created at DatabaseService initialization time.

            logger.info(
                f"SQLite admin audit storage initialized with collection: {self._collection_name}"
            )
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite admin audit storage: {e}")
            raise

    async def store(self, record: AdminAuditRecord) -> bool:
        if not self._initialized:
            await self.initialize()

        try:
            doc = record.to_flat_dict()
            doc["id"] = generate_id("sqlite")
            result = await self._database_service.insert_one(self._collection_name, doc)
            if result:
                logger.debug(f"Stored admin audit record with ID: {result}")
                return True
            logger.warning("Failed to store admin audit record - no ID returned")
            return False
        except Exception as e:
            logger.error(f"Error storing admin audit record in SQLite: {e}")
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
            converted: Dict[str, Any] = {}
            for key, value in filters.items():
                if isinstance(value, bool):
                    converted[key] = 1 if value else 0
                else:
                    converted[key] = value

            results = await self._database_service.find_many(
                collection_name=self._collection_name,
                query=converted,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)],
            )
            return [self._unflatten(r) for r in results]
        except Exception as e:
            logger.error(f"Error querying admin audit records from SQLite: {e}")
            return []

    def _unflatten(self, row: Dict[str, Any]) -> Dict[str, Any]:
        summary = row.get("request_summary")
        if isinstance(summary, str) and summary:
            try:
                summary = json.loads(summary)
            except json.JSONDecodeError:
                pass

        result: Dict[str, Any] = {
            "timestamp": row.get("timestamp"),
            "event_type": row.get("event_type"),
            "action": row.get("action"),
            "resource_type": row.get("resource_type"),
            "resource_id": row.get("resource_id"),
            "actor_type": row.get("actor_type"),
            "actor_id": row.get("actor_id"),
            "actor_username": row.get("actor_username"),
            "method": row.get("method"),
            "path": row.get("path"),
            "status_code": row.get("status_code"),
            "success": bool(row.get("success", 0)),
            "ip": row.get("ip"),
            "ip_metadata": {
                "type": row.get("ip_type", "unknown"),
                "isLocal": bool(row.get("ip_is_local", 0)),
                "source": row.get("ip_source", "unknown"),
                "originalValue": row.get("ip_original_value", ""),
            },
            "user_agent": row.get("user_agent"),
            "error_message": row.get("error_message"),
            "request_summary": summary,
        }
        if row.get("id"):
            result["_id"] = row["id"]
        return result

    async def close(self) -> None:
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:
                logger.error(f"Error closing SQLite admin audit database service: {e}")
        self._initialized = False

    async def clear(self) -> bool:
        if not self._initialized:
            await self.initialize()
        try:
            deleted_count = await self._database_service.clear_collection(self._collection_name)
            logger.info(
                f"Cleared {deleted_count} admin audit records from SQLite table '{self._collection_name}'"
            )
            return True
        except Exception as e:
            logger.error(f"Error clearing SQLite admin audit records: {e}")
            return False
