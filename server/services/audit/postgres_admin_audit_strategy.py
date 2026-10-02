"""
PostgreSQL Admin Audit Storage Strategy
========================================

Stores AdminAuditRecord rows into the `audit_admin_logs` PostgreSQL table via the
shared DatabaseService abstraction.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from .admin_audit_storage_strategy import AdminAuditRecord, AdminAuditStorageStrategy
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class PostgresAdminAuditStrategy(AdminAuditStorageStrategy):
    """PostgreSQL implementation of admin audit storage."""

    def __init__(self, config: dict[str, Any], database_service=None):
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
        """
        Creates a dedicated PostgresService if one wasn't provided - constructed
        directly rather than via create_database_service(), since that factory
        branches on internal_services.backend.type, which may be sqlite/mongodb
        even when admin audit storage is explicitly configured to use postgres.
        """
        if self._initialized:
            return

        try:
            if self._database_service is None:
                from services.postgres_service import PostgresService
                self._database_service = PostgresService(self.config)
                self._owns_database_service = True

            if not self._database_service._initialized:
                await self._database_service.initialize()

            # The audit_admin_logs table is defined in postgres_service.py's schema
            # and auto-created at DatabaseService initialization time.
            await self._ensure_trigram_indexes()

            logger.debug(
                f"Postgres admin audit storage initialized with collection: {self._collection_name}"
            )
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize Postgres admin audit storage: {e}")
            raise

    async def _ensure_trigram_indexes(self) -> None:
        """Best-effort pg_trgm GIN indexes on the `search` columns — see
        PostgresAuditStrategy._ensure_trigram_indexes for the full rationale.
        Not load-bearing for correctness: query() always runs search through
        _bounded_contains_search() regardless of whether this succeeds.
        """
        self._trgm_available = False
        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            return

        table = self._collection_name
        columns = self._SEARCH_FIELDS

        def setup() -> bool:
            cursor = connection.cursor()
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                for column in columns:
                    index_name = f"idx_{table}_{column}_trgm"
                    cursor.execute(
                        f"CREATE INDEX IF NOT EXISTS {index_name} "
                        f"ON {table} USING gin ({column} gin_trgm_ops)"
                    )
                connection.commit()
                return True
            except Exception as exc:  # noqa: BLE001 - best-effort index creation; a missing extension/privilege must not block startup
                logger.warning(
                    f"pg_trgm trigram index unavailable for {table} "
                    f"(search will use a scan bounded to the most recent rows instead): {exc}"
                )
                connection.rollback()
                return False

        def run() -> bool:
            if db_lock is not None:
                with db_lock:
                    return setup()
            return setup()

        loop = asyncio.get_running_loop()
        self._trgm_available = await loop.run_in_executor(executor, run)

    async def store(self, record: AdminAuditRecord) -> bool:
        if not self._initialized:
            await self.initialize()

        try:
            doc = record.to_flat_dict()
            doc["id"] = generate_id("postgres")
            result = await self._database_service.insert_one(self._collection_name, doc)
            if result:
                logger.debug(f"Stored admin audit record with ID: {result}")
                return True
            logger.warning("Failed to store admin audit record - no ID returned")
            return False
        except Exception as e:  # noqa: BLE001 - database-backend call must fail safe, matching precedent from sibling audit strategies
            logger.error(f"Error storing admin audit record in Postgres: {e}")
            return False

    # Columns a free-text `search` matches against — same fields the admin
    # panel showed via Python-side substring search before Phase 4.
    _SEARCH_FIELDS = (
        "event_type", "action", "actor_username", "actor_id",
        "path", "resource_id", "resource_type", "ip",
    )

    async def query(
        self,
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "timestamp",
        sort_order: int = -1,
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        try:
            converted: dict[str, Any] = {}
            for key, value in filters.items():
                if isinstance(value, bool):
                    converted[key] = 1 if value else 0
                else:
                    converted[key] = value

            if search:
                # Always bounded — see PostgresAuditStrategy.query() for why
                # trusting pg_trgm index availability/term length isn't a
                # reliable way to guarantee the scan is actually bounded.
                results = await self._bounded_contains_search(
                    converted, search, limit, offset, sort_by, sort_order
                )
            else:
                results = await self._database_service.find_many(
                    collection_name=self._collection_name,
                    query=converted,
                    limit=limit,
                    skip=offset,
                    sort=[(sort_by, sort_order)],
                )
            return [self._unflatten(r) for r in results]
        except Exception as e:  # noqa: BLE001 - database-backend call must fail safe, matching precedent from sibling audit strategies
            logger.error(f"Error querying admin audit records from Postgres: {e}")
            return []

    # Hard cap on how many rows search will ever examine, regardless of table
    # size — an explicit, accepted trade-off: a match older than the most
    # recent _FALLBACK_SCAN_CAP rows (by `timestamp`) is not found. Applied
    # unconditionally — see PostgresAuditStrategy.query().
    _FALLBACK_SCAN_CAP = 20000

    async def _bounded_contains_search(
        self,
        converted_filters: dict[str, Any],
        search: str,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: int,
    ) -> list[dict[str, Any]]:
        """Unindexed substring search, bounded to the most recent
        _FALLBACK_SCAN_CAP rows via the existing idx_{table}_timestamp index
        — see PostgresAuditStrategy's identical method for the full
        rationale.
        """
        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            return []

        db = self._database_service
        table = self._collection_name
        base_where, base_params = db._convert_query_to_sql(table, converted_filters)
        search_filter = {"$or": [{field: {"$contains": search}} for field in self._SEARCH_FIELDS]}
        search_where, search_params = db._convert_query_to_sql(table, search_filter)
        where_parts = [p for p in (base_where, search_where) if p]
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        order_dir = "ASC" if sort_order == 1 else "DESC"

        sql = (
            f"SELECT * FROM (SELECT * FROM {table} ORDER BY timestamp DESC LIMIT %s) recent "
            f"{where_sql} ORDER BY {sort_by} {order_dir} LIMIT %s OFFSET %s"
        )
        params = (self._FALLBACK_SCAN_CAP, *base_params, *search_params, limit, offset)

        logger.warning(
            f"Audit search on {table} is using the unindexed ILIKE fallback, bounded to "
            f"the {self._FALLBACK_SCAN_CAP} most recent rows (pg_trgm unavailable) — "
            f"a match older than that window will not be found."
        )

        def run() -> list[dict[str, Any]]:
            def execute() -> list[dict[str, Any]]:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                return cursor.fetchall()  # dict_row row factory: already dicts

            if db_lock is not None:
                with db_lock:
                    return execute()
            return execute()

        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(executor, run)
        return [db._convert_row_to_document(table, row) for row in rows]

    def _unflatten(self, row: dict[str, Any]) -> dict[str, Any]:
        summary = row.get("request_summary")
        if isinstance(summary, str) and summary:
            try:
                summary = json.loads(summary)
            except json.JSONDecodeError:
                pass

        result: dict[str, Any] = {
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
            except Exception as e:  # noqa: BLE001 - best-effort cleanup on close, must not raise
                logger.error(f"Error closing Postgres admin audit database service: {e}")
        self._initialized = False

    async def clear(self) -> bool:
        if not self._initialized:
            await self.initialize()
        try:
            deleted_count = await self._database_service.clear_collection(self._collection_name)
            logger.info(
                f"Cleared {deleted_count} admin audit records from Postgres table '{self._collection_name}'"
            )
            return True
        except Exception as e:  # noqa: BLE001 - database-backend call must fail safe, matching precedent from sibling audit strategies
            logger.error(f"Error clearing Postgres admin audit records: {e}")
            return False
