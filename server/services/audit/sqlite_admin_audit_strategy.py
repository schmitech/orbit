"""
SQLite Admin Audit Storage Strategy
===================================

Stores AdminAuditRecord rows into the `audit_admin_logs` SQLite table via the
shared DatabaseService abstraction.
"""

import asyncio
import json
import logging
import re
import sqlite3
from typing import Any, Optional

from .admin_audit_storage_strategy import AdminAuditRecord, AdminAuditStorageStrategy
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class SQLiteAdminAuditStrategy(AdminAuditStorageStrategy):
    """SQLite implementation of admin audit storage."""

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
            await self._ensure_fts_index()

            logger.debug(
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
        except Exception as e:  # noqa: BLE001 - sqlite audit-backend boundary; store must fail safe rather than crash the request
            logger.error(f"Error storing admin audit record in SQLite: {e}")
            return False

    # Columns a free-text `search` matches against — same fields the admin
    # panel showed via Python-side substring search before Phase 4.
    _SEARCH_FIELDS = (
        "event_type", "action", "actor_username", "actor_id",
        "path", "resource_id", "resource_type", "ip",
    )

    # FTS5's trigram tokenizer requires queries of at least 3 characters —
    # shorter terms silently match nothing, so those fall back to the
    # $contains OR-of-LIKE path in query() instead (an unindexed scan of a
    # 1-2 character term is cheap regardless, since so little can narrow it).
    _FTS_MIN_SEARCH_LENGTH = 3

    async def _ensure_fts_index(self) -> None:
        """Create an FTS5 (trigram tokenizer) shadow index over
        _SEARCH_FIELDS, kept in sync via triggers, so `search` can be
        resolved as an indexed lookup instead of an unindexed LIKE '%term%'
        scan of the whole table.

        Falls back silently (self._fts_available stays False) on a SQLite
        build without FTS5/the trigram tokenizer (added in SQLite 3.34, Jan
        2021) — the $contains OR-of-LIKE path in query() still works, just
        without this index, exactly like today.
        """
        self._fts_available = False
        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            return

        table = self._collection_name
        fts_table = f"{table}_fts"
        columns = self._SEARCH_FIELDS
        col_list = ", ".join(columns)
        new_cols = ", ".join(f"new.{c}" for c in columns)
        old_cols = ", ".join(f"old.{c}" for c in columns)

        def setup() -> bool:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            if cursor.fetchone() is None:
                return False
            cursor.execute("SELECT name FROM sqlite_master WHERE name=?", (fts_table,))
            if cursor.fetchone() is not None:
                return True
            try:
                cursor.execute(
                    f"CREATE VIRTUAL TABLE {fts_table} USING fts5("
                    f"{col_list}, content='{table}', content_rowid='rowid', "
                    f"tokenize='trigram case_sensitive 0')"
                )
                cursor.execute(f"INSERT INTO {fts_table}(rowid, {col_list}) "
                                f"SELECT rowid, {col_list} FROM {table}")
                cursor.execute(f"""
                    CREATE TRIGGER {table}_fts_ai AFTER INSERT ON {table} BEGIN
                      INSERT INTO {fts_table}(rowid, {col_list}) VALUES (new.rowid, {new_cols});
                    END
                """)
                cursor.execute(f"""
                    CREATE TRIGGER {table}_fts_ad AFTER DELETE ON {table} BEGIN
                      INSERT INTO {fts_table}({fts_table}, rowid, {col_list}) VALUES('delete', old.rowid, {old_cols});
                    END
                """)
                cursor.execute(f"""
                    CREATE TRIGGER {table}_fts_au AFTER UPDATE ON {table} BEGIN
                      INSERT INTO {fts_table}({fts_table}, rowid, {col_list}) VALUES('delete', old.rowid, {old_cols});
                      INSERT INTO {fts_table}(rowid, {col_list}) VALUES (new.rowid, {new_cols});
                    END
                """)
                connection.commit()
                return True
            except sqlite3.OperationalError as exc:
                logger.warning(
                    f"FTS5 trigram index unavailable for {table} "
                    f"(falling back to unindexed LIKE search): {exc}"
                )
                connection.rollback()
                return False

        def run() -> bool:
            if db_lock is not None:
                with db_lock:
                    return setup()
            return setup()

        loop = asyncio.get_running_loop()
        self._fts_available = await loop.run_in_executor(executor, run)

    async def _fts_search(
        self,
        converted_filters: dict[str, Any],
        search: str,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: int,
    ) -> Optional[list[dict[str, Any]]]:
        """Resolve `search` via the FTS5 index AND apply the caller's other
        filters, sort order, and pagination in the same query — see
        SQLiteAuditStrategy._fts_search for the full rationale (a separate
        id-resolution step with any LIMIT, including a generous safety cap,
        truncates the candidate set before filtering/ordering/pagination are
        ever applied, reproducing the same pagination/filter bugs at a larger
        scale).

        Returns None (not an empty list) when FTS isn't available or the
        term is too short for the trigram tokenizer, signaling the caller to
        use the $contains fallback instead of treating "no FTS match" as "no
        match at all".
        """
        if not getattr(self, "_fts_available", False) or len(search) < self._FTS_MIN_SEARCH_LENGTH:
            return None

        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            return None

        db = self._database_service
        table = self._collection_name
        fts_table = f"{table}_fts"
        match_expr = '"' + search.replace('"', '""') + '"'

        base_where, base_params = db._convert_query_to_sql(table, converted_filters)
        where_parts = [f"{fts_table} MATCH ?"]
        params: list[Any] = [match_expr]
        if base_where:
            # Qualify bare column references with the main table's alias —
            # fts_table also has a same-named column for each of
            # _SEARCH_FIELDS, so an unqualified reference in this JOIN would
            # be ambiguous.
            where_parts.append(re.sub(r'"(\w+)"', r't."\1"', base_where))
            params.extend(base_params)
        where_sql = " AND ".join(where_parts)
        order_dir = "ASC" if sort_order == 1 else "DESC"

        sql = (
            f"SELECT t.* FROM {fts_table} JOIN {table} t ON t.rowid = {fts_table}.rowid "
            f'WHERE {where_sql} ORDER BY t."{sort_by}" {order_dir} LIMIT ? OFFSET ?'
        )
        params.extend([limit, offset])

        def run() -> list[dict[str, Any]]:
            def execute() -> list[dict[str, Any]]:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                columns = [d[0] for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

            if db_lock is not None:
                with db_lock:
                    return execute()
            return execute()

        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(executor, run)
        return [db._convert_row_to_document(table, row) for row in rows]

    # Hard cap on how many rows the unindexed substring fallback (below) will
    # ever examine, regardless of table size — an explicit, accepted
    # trade-off: a match older than the most recent _FALLBACK_SCAN_CAP rows
    # (by `timestamp`) is not found via this path. This only matters when
    # FTS5/the trigram tokenizer is unavailable or `search` is under
    # _FTS_MIN_SEARCH_LENGTH characters; the FTS5 path has no such limit.
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
        (`ORDER BY timestamp DESC LIMIT <cap>` as an inner subquery) instead
        of scanning the whole table — see SQLiteAuditStrategy's identical
        method for the full rationale and EXPLAIN QUERY PLAN verification.
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
            f"SELECT * FROM (SELECT * FROM {table} ORDER BY timestamp DESC LIMIT ?) recent "
            f"{where_sql} ORDER BY {sort_by} {order_dir} LIMIT ? OFFSET ?"
        )
        params = (self._FALLBACK_SCAN_CAP, *base_params, *search_params, limit, offset)

        logger.warning(
            f"Audit search on {table} is using the unindexed substring fallback, bounded to "
            f"the {self._FALLBACK_SCAN_CAP} most recent rows (FTS5/trigram tokenizer "
            f"unavailable or search term under {self._FTS_MIN_SEARCH_LENGTH} characters) — "
            f"a match older than that window will not be found."
        )

        def run() -> list[dict[str, Any]]:
            def execute() -> list[dict[str, Any]]:
                cursor = connection.cursor()
                cursor.execute(sql, params)
                columns = [d[0] for d in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]

            if db_lock is not None:
                with db_lock:
                    return execute()
            return execute()

        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(executor, run)
        return [db._convert_row_to_document(table, row) for row in rows]

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

            results: list[dict[str, Any]] = []
            if search:
                fts_results = await self._fts_search(
                    converted, search, limit, offset, sort_by, sort_order
                )
                if fts_results is not None:
                    results = fts_results
                else:
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
        except Exception as e:  # noqa: BLE001 - sqlite audit-backend boundary; query must fail safe rather than crash the caller
            logger.error(f"Error querying admin audit records from SQLite: {e}")
            return []

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
            except Exception as e:  # noqa: BLE001 - best-effort database-service close during shutdown
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
        except Exception as e:  # noqa: BLE001 - sqlite audit-backend boundary; clear must fail safe rather than crash the caller
            logger.error(f"Error clearing SQLite admin audit records: {e}")
            return False
