"""
SQLite Audit Storage Strategy
=============================

Implementation of AuditStorageStrategy for SQLite backend.
Uses the existing SQLiteService/DatabaseService interface for storage operations.
"""

import asyncio
import logging
import re
import sqlite3
from contextlib import nullcontext as _NullContext
from typing import Any, Optional

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, decompress_text
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class SQLiteAuditStrategy(AuditStorageStrategy):
    """
    SQLite implementation of audit storage.

    Uses the DatabaseService abstraction to store audit records in the
    audit_logs table with flattened structure for nested objects.
    """

    def __init__(self, config: dict[str, Any], database_service=None):
        """
        Initialize the SQLite audit strategy.

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
        # Compression setting
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the SQLite storage backend.

        Creates the database service if not provided and ensures
        the audit_logs table and indexes exist.
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

            # The audit_logs table, its columns (including token/cost usage),
            # and migration of missing columns on existing installs are all
            # handled by SQLiteService's schema + _migrate_table_schema.
            # This strategy only needs to ensure its own indexes exist.
            await self._ensure_audit_indexes()
            await self._ensure_fts_index()

            logger.debug(f"SQLite audit storage initialized with collection: {self._collection_name}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize SQLite audit storage: {e}")
            raise

    async def _ensure_audit_indexes(self) -> None:
        """Ensure lookup indexes exist for the SQLite audit table."""
        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            return

        import asyncio

        def ensure_indexes() -> None:
            def run() -> None:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (self._collection_name,),
                )
                if cursor.fetchone() is None:
                    return
                for index_name, column in (
                    ("provider", "provider"),
                    ("model", "model"),
                    ("timestamp", "timestamp"),
                ):
                    cursor.execute(
                        f"CREATE INDEX IF NOT EXISTS idx_{self._collection_name}_{index_name} "
                        f"ON {self._collection_name}({column})"
                    )
                connection.commit()

            if db_lock is not None:
                with db_lock:
                    run()
            else:
                run()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, ensure_indexes)

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
        filters, sort order, and pagination in the same query.

        An earlier version of this resolved matching ids via FTS first (with
        its own LIMIT), then ran a separate find_many() call to apply the
        real filters/sort/limit/offset against that id list. Any LIMIT inside
        the id-resolution step — whether set to the page size or to a larger
        safety cap — necessarily truncates the candidate set *before*
        filtering and ordering happen, so a dataset with more matches than
        that cap can reproduce the exact bug a smaller page-size cap did: a
        wrong row returned for a given page, a combined filter coming back
        empty despite a real match, or a later page coming back empty despite
        more matches existing. A single joined query has no such
        intermediate truncation point — FTS resolves the match set, the
        WHERE/ORDER BY/LIMIT/OFFSET apply to it exactly as they would for any
        other query.

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
        # FTS5 query syntax is special (quotes, AND/OR, column filters, '*',
        # etc.) — wrapping in double quotes (escaping embedded quotes) makes
        # `search` a single literal phrase rather than FTS query syntax.
        match_expr = '"' + search.replace('"', '""') + '"'

        base_where, base_params = db._convert_query_to_sql(table, converted_filters)
        where_parts = [f"{fts_table} MATCH ?"]
        params: list[Any] = [match_expr]
        if base_where:
            # _convert_query_to_sql quotes every bare column reference (e.g.
            # "provider" = ?) without a table prefix. fts_table also has a
            # same-named "provider" column (it mirrors _SEARCH_FIELDS), so an
            # unqualified reference in this JOIN would be ambiguous — qualify
            # every one with the main table's alias.
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
        (`ORDER BY timestamp DESC LIMIT <cap>` as an inner subquery, verified
        via EXPLAIN QUERY PLAN in tests to use that index rather than a full
        table scan) instead of scanning the whole table. This is the only
        path search cost isn't bounded by an index lookup, and it is bounded
        by this cap rather than left unbounded — see _FALLBACK_SCAN_CAP.
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

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in SQLite.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert record to flat dictionary for SQLite storage
            # Pass compress flag to optionally compress the response
            doc = record.to_flat_dict(compress=self._compress_responses)

            # Add ID
            doc['id'] = generate_id('sqlite')

            # Insert into database
            result = await self._database_service.insert_one(self._collection_name, doc)

            if result:
                logger.debug(f"Stored audit record with ID: {result} (compressed: {self._compress_responses})")
                return True
            else:
                logger.warning("Failed to store audit record - no ID returned")
                return False

        except Exception as e:  # noqa: BLE001 - database-backend call; audit write must fail safe
            logger.error(f"Error storing audit record in SQLite: {e}")
            return False

    # Columns a free-text `search` matches against — same fields the admin
    # panel showed via Python-side substring search before Phase 4.
    # response_plain is an always-plaintext copy of a compressed `response`
    # (see AuditRecord.to_flat_dict), only ever populated when
    # response_compressed=1 — including it here means a compressed
    # response's text is still searchable at the datastore layer, with no
    # separate decompress-and-check pass needed.
    _SEARCH_FIELDS = (
        "provider", "model", "adapter_name", "session_id", "user_id",
        "ip", "api_key_value", "query", "response", "response_plain",
    )

    async def query(
        self,
        filters: dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = 'timestamp',
        sort_order: int = -1,
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Query audit records from SQLite.

        Args:
            filters: Query criteria (e.g., {'session_id': 'abc', 'blocked': True})
            limit: Maximum number of records to return
            offset: Number of records to skip
            sort_by: Field to sort by (default: 'timestamp')
            sort_order: Sort direction (1=ascending, -1=descending)
            search: Free-text match across _SEARCH_FIELDS, pushed down as an
                indexed-table LIKE rather than filtered in Python.

        Returns:
            List of matching audit records as dictionaries
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Convert boolean filters to SQLite integer format
            converted_filters = {}
            for key, value in filters.items():
                if isinstance(value, bool):
                    converted_filters[key] = 1 if value else 0
                else:
                    converted_filters[key] = value

            results: list[dict[str, Any]] = []
            if search:
                # Prefer the FTS5 trigram index (an indexed lookup) over the
                # $contains OR-of-LIKE path (an unindexed scan) when it's
                # available and the term is long enough for it to apply.
                fts_results = await self._fts_search(
                    converted_filters, search, limit, offset, sort_by, sort_order
                )
                if fts_results is not None:
                    results = fts_results
                else:
                    results = await self._bounded_contains_search(
                        converted_filters, search, limit, offset, sort_by, sort_order
                    )
            else:
                results = await self._database_service.find_many(
                    collection_name=self._collection_name,
                    query=converted_filters,
                    limit=limit,
                    skip=offset,
                    sort=[(sort_by, sort_order)]
                )

            # Convert results back to nested format for consistency
            return [self._unflatten_record(record) for record in results]

        except Exception as e:  # noqa: BLE001 - database-backend call; audit query must fail safe
            logger.error(f"Error querying audit records from SQLite: {e}")
            return []

    # Logical group-by dimension -> the column that actually holds it. Most
    # are identity mappings; api_key is handled separately by
    # _resolve_dimension_field, since its expression depends on the
    # (configurable) table name.
    _GROUP_BY_FIELDS = {
        "model": "model",
        "provider": "provider",
        "adapter_name": "adapter_name",
        "user_id": "user_id",
        "call_type": "call_type",
    }

    # Dimensions accepted in `filters`. Reuses _resolve_dimension_field for
    # the logical-name -> column/expression mapping; user_id is groupable
    # but not (yet) filterable, so it is deliberately excluded here.
    _FILTERABLE_DIMENSIONS = {"provider", "adapter_name", "model", "call_type", "api_key"}

    def _resolve_dimension_field(self, dimension: str) -> Optional[str]:
        """Return the SQL expression backing a logical dimension, for both
        grouping and equality filtering.

        api_key needs more than COALESCE(api_key_id, api_key_value): a key
        that already has an id-bearing row (any row, not just ones in the
        current window) must have ALL of its rows — including older ones
        written before api_key_id existed, which only carry the masked
        value — resolve to that same id. Otherwise legacy and new rows for
        the one underlying key split into two groups, and filtering by the
        id a group row exposes silently omits that key's legacy spend.
        The self-join below finds that id when this row doesn't carry its
        own; a key that has never written an id-bearing row still falls
        back to its masked value, unchanged from before.
        """
        if dimension == "api_key":
            return (
                f"COALESCE({self._collection_name}.api_key_id, "
                f"(SELECT sub.api_key_id FROM {self._collection_name} sub "
                f"WHERE sub.api_key_value = {self._collection_name}.api_key_value "
                f"AND sub.api_key_id IS NOT NULL LIMIT 1), "
                f"{self._collection_name}.api_key_value)"
            )
        return self._GROUP_BY_FIELDS.get(dimension)

    async def aggregate_usage(
        self,
        since: str,
        until: str,
        bucket: str = "day",
        group_by: str = "model",
        filters: Optional[dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> dict[str, Any]:
        """SQLite implementation: SUM/COUNT via raw SQL, no full-row transfer."""
        if not self._initialized:
            await self.initialize()

        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            raise NotImplementedError("SQLite connection not available for aggregation")

        # timestamp is stored as an ISO string; substr(timestamp,1,10) buckets
        # by day, substr(timestamp,1,13) buckets by hour (both index-friendly
        # alongside the range predicate below).
        bucket_expr = "substr(timestamp,1,13)" if bucket == "hour" else "substr(timestamp,1,10)"
        group_column = self._resolve_dimension_field(group_by)

        where_clauses = ["timestamp >= ?", "timestamp < ?"]
        params: list[Any] = [since, until]
        for key, value in (filters or {}).items():
            if key not in self._FILTERABLE_DIMENSIONS:
                continue
            field = self._resolve_dimension_field(key)
            where_clauses.append(f"{field} = ?")
            params.append(value)
        where_sql = " AND ".join(where_clauses)

        def run() -> dict[str, Any]:
            with db_lock if db_lock is not None else _NullContext():
                cursor = connection.cursor()

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens),
                        SUM(cost_usd),
                        SUM(CASE WHEN cost_usd IS NULL AND total_tokens IS NOT NULL THEN 1 ELSE 0 END),
                        SUM(CASE WHEN total_tokens IS NULL THEN 1 ELSE 0 END)
                    FROM {self._collection_name}
                    WHERE {where_sql}
                    """,
                    params,
                )
                (
                    requests, prompt_tokens, completion_tokens, total_tokens,
                    cost_usd, unpriced_requests, unreported_requests,
                ) = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT {bucket_expr} AS b, COUNT(*),
                        SUM(prompt_tokens), SUM(completion_tokens), SUM(total_tokens), SUM(cost_usd)
                    FROM {self._collection_name}
                    WHERE {where_sql}
                    GROUP BY b
                    ORDER BY b ASC
                    """,
                    params,
                )
                series = [
                    {
                        "bucket": row[0], "requests": row[1],
                        "prompt_tokens": row[2] or 0, "completion_tokens": row[3] or 0,
                        "total_tokens": row[4] or 0, "cost_usd": row[5] or 0.0,
                    }
                    for row in cursor.fetchall()
                ]

                groups: list[dict[str, Any]] = []
                if group_column:
                    cursor.execute(
                        f"""
                        SELECT {group_column} AS g, COUNT(*),
                            SUM(total_tokens), SUM(cost_usd),
                            SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END)
                        FROM {self._collection_name}
                        WHERE {where_sql} AND {group_column} IS NOT NULL
                        GROUP BY g
                        ORDER BY SUM(cost_usd) DESC
                        LIMIT ?
                        """,
                        params + [limit_groups],
                    )
                    groups = [
                        {
                            "key": row[0], "requests": row[1],
                            "total_tokens": row[2] or 0, "cost_usd": row[3] or 0.0,
                            "unpriced": bool(row[4]),
                        }
                        for row in cursor.fetchall()
                    ]

                return {
                    "totals": {
                        "requests": requests or 0,
                        "prompt_tokens": prompt_tokens or 0,
                        "completion_tokens": completion_tokens or 0,
                        "total_tokens": total_tokens or 0,
                        "cost_usd": cost_usd or 0.0,
                        "unpriced_requests": unpriced_requests or 0,
                        "unreported_requests": unreported_requests or 0,
                    },
                    "series": series,
                    "groups": groups,
                }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, run)

    async def close(self) -> None:
        """Close SQLite audit storage resources."""
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:  # noqa: BLE001 - database-backend call; cleanup must not crash shutdown
                logger.error(f"Error closing SQLite audit database service: {e}")

        self._initialized = False

    def _unflatten_record(self, flat_record: dict[str, Any]) -> dict[str, Any]:
        """
        Convert a flat SQLite record back to nested format.

        Args:
            flat_record: Record with flattened fields

        Returns:
            Record with nested ip_metadata and api_key structures
        """
        # Only the response field is compressed; query remains plain text.
        query = flat_record.get('query', '')
        response = flat_record.get('response', '')
        is_compressed = bool(flat_record.get('response_compressed', 0))

        if is_compressed and response:
            try:
                response = decompress_text(response)
            except Exception as e:  # noqa: BLE001 - best-effort decompression; falls back to raw stored value
                logger.warning(f"Failed to decompress response: {e}")
                # Return compressed response as-is if decompression fails

        result = {
            'timestamp': flat_record.get('timestamp'),
            'query': query,
            'response': response,
            'response_compressed': is_compressed,
            'provider': flat_record.get('provider'),
            'blocked': bool(flat_record.get('blocked', 0)),
            'ip': flat_record.get('ip'),
            'ip_metadata': {
                'type': flat_record.get('ip_type', 'unknown'),
                'isLocal': bool(flat_record.get('ip_is_local', 0)),
                'source': flat_record.get('ip_source', 'unknown'),
                'originalValue': flat_record.get('ip_original_value', '')
            }
        }

        # Add api_key if present
        if flat_record.get('api_key_value'):
            result['api_key'] = {
                'key': flat_record.get('api_key_value'),
                'timestamp': flat_record.get('api_key_timestamp')
            }
            if flat_record.get('api_key_id'):
                result['api_key']['id'] = flat_record.get('api_key_id')

        # Add optional fields
        if flat_record.get('session_id'):
            result['session_id'] = flat_record.get('session_id')
        if flat_record.get('user_id'):
            result['user_id'] = flat_record.get('user_id')
        if flat_record.get('adapter_name'):
            result['adapter_name'] = flat_record.get('adapter_name')
        if flat_record.get('model'):
            result['model'] = flat_record.get('model')
        if flat_record.get('_id'):
            result['_id'] = flat_record.get('_id')

        for field in (
            'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens',
            'cached_prompt_tokens',
            'cost_usd', 'input_rate_per_1m', 'output_rate_per_1m', 'pricing_source',
            'usage_unit', 'usage_quantity', 'call_type',
        ):
            if flat_record.get(field) is not None:
                result[field] = flat_record.get(field)

        return result

    async def clear(self) -> bool:
        """
        Clear all audit records from the SQLite audit_logs table.

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
            logger.info(f"Cleared {deleted_count} audit records from SQLite table '{self._collection_name}'")
            return True

        except Exception as e:  # noqa: BLE001 - database-backend call; audit clear must fail safe
            logger.error(f"Error clearing SQLite audit records: {e}")
            return False
