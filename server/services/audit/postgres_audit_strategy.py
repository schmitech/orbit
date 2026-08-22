"""
PostgreSQL Audit Storage Strategy
==================================

Implementation of AuditStorageStrategy for PostgreSQL backend.
Uses the existing PostgresService/DatabaseService interface for storage operations.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from .audit_storage_strategy import AuditStorageStrategy, AuditRecord, decompress_text
from utils.id_utils import generate_id

logger = logging.getLogger(__name__)


class PostgresAuditStrategy(AuditStorageStrategy):
    """
    PostgreSQL implementation of audit storage.

    Uses the DatabaseService abstraction to store audit records in the
    audit_logs table with flattened structure for nested objects.
    """

    def __init__(self, config: Dict[str, Any], database_service=None):
        """
        Initialize the Postgres audit strategy.

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
        self._compress_responses = config.get('internal_services', {}).get('audit', {}).get(
            'compress_responses', False
        )

    async def initialize(self) -> None:
        """
        Initialize the Postgres storage backend.

        Creates a dedicated PostgresService if one wasn't provided - constructed
        directly rather than via create_database_service(), since that factory
        branches on internal_services.backend.type, which may be sqlite/mongodb
        even when audit storage is explicitly configured to use postgres. The
        audit_logs table and its columns (including provider/model) are part of
        PostgresService's schema and are created/migrated automatically during
        database initialization.
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

            logger.debug(f"Postgres audit storage initialized with collection: {self._collection_name}")
            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to initialize Postgres audit storage: {e}")
            raise

    async def store(self, record: AuditRecord) -> bool:
        """
        Store an audit record in Postgres.

        Args:
            record: The audit record to store

        Returns:
            True if stored successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            doc = record.to_flat_dict(compress=self._compress_responses)
            doc['id'] = generate_id('postgres')

            result = await self._database_service.insert_one(self._collection_name, doc)

            if result:
                logger.debug(f"Stored audit record with ID: {result} (compressed: {self._compress_responses})")
                return True
            else:
                logger.warning("Failed to store audit record - no ID returned")
                return False

        except Exception as e:
            logger.error(f"Error storing audit record in Postgres: {e}")
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
        Query audit records from Postgres.

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
            converted_filters = {}
            for key, value in filters.items():
                if isinstance(value, bool):
                    converted_filters[key] = 1 if value else 0
                else:
                    converted_filters[key] = value

            results = await self._database_service.find_many(
                collection_name=self._collection_name,
                query=converted_filters,
                limit=limit,
                skip=offset,
                sort=[(sort_by, sort_order)]
            )

            return [self._unflatten_record(record) for record in results]

        except Exception as e:
            logger.error(f"Error querying audit records from Postgres: {e}")
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
        filters: Optional[Dict[str, Any]] = None,
        limit_groups: int = 10,
    ) -> Dict[str, Any]:
        """Postgres implementation: SUM/COUNT via raw SQL, no full-row transfer."""
        if not self._initialized:
            await self.initialize()

        connection = getattr(self._database_service, "connection", None)
        executor = getattr(self._database_service, "executor", None)
        db_lock = getattr(self._database_service, "_db_lock", None)
        if connection is None or executor is None:
            raise NotImplementedError("Postgres connection not available for aggregation")

        # timestamp is stored as TEXT (ISO), so date_trunc needs an explicit cast.
        trunc_unit = "hour" if bucket == "hour" else "day"
        bucket_expr = f"date_trunc('{trunc_unit}', timestamp::timestamptz)"
        group_column = self._resolve_dimension_field(group_by)

        where_clauses = ["timestamp >= %s", "timestamp < %s"]
        params: List[Any] = [since, until]
        for key, value in (filters or {}).items():
            if key not in self._FILTERABLE_DIMENSIONS:
                continue
            field = self._resolve_dimension_field(key)
            where_clauses.append(f"{field} = %s")
            params.append(value)
        where_sql = " AND ".join(where_clauses)

        def run() -> Dict[str, Any]:
            with db_lock:
                cursor = connection.cursor()

                # The shared connection uses psycopg's dict_row row_factory
                # (see PostgresService._connect_db), so every column must be
                # explicitly aliased and read by name — unaliased duplicate
                # aggregate expressions (six SUM(...) calls below) would
                # otherwise all be keyed "sum" by Postgres and collapse into
                # a single dict entry, breaking positional/tuple access.
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS requests,
                        SUM(prompt_tokens) AS prompt_tokens,
                        SUM(completion_tokens) AS completion_tokens,
                        SUM(total_tokens) AS total_tokens,
                        SUM(cost_usd) AS cost_usd,
                        SUM(CASE WHEN cost_usd IS NULL AND total_tokens IS NOT NULL THEN 1 ELSE 0 END) AS unpriced_requests,
                        SUM(CASE WHEN total_tokens IS NULL THEN 1 ELSE 0 END) AS unreported_requests
                    FROM {self._collection_name}
                    WHERE {where_sql}
                    """,
                    params,
                )
                totals_row = cursor.fetchone()

                cursor.execute(
                    f"""
                    SELECT {bucket_expr} AS bucket, COUNT(*) AS requests,
                        SUM(prompt_tokens) AS prompt_tokens, SUM(completion_tokens) AS completion_tokens,
                        SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS cost_usd
                    FROM {self._collection_name}
                    WHERE {where_sql}
                    GROUP BY bucket
                    ORDER BY bucket ASC
                    """,
                    params,
                )
                series = [
                    {
                        "bucket": row["bucket"].isoformat() if row["bucket"] is not None else None,
                        "requests": row["requests"],
                        "prompt_tokens": row["prompt_tokens"] or 0, "completion_tokens": row["completion_tokens"] or 0,
                        "total_tokens": row["total_tokens"] or 0, "cost_usd": float(row["cost_usd"] or 0.0),
                    }
                    for row in cursor.fetchall()
                ]

                groups: List[Dict[str, Any]] = []
                if group_column:
                    cursor.execute(
                        f"""
                        SELECT {group_column} AS key, COUNT(*) AS requests,
                            SUM(total_tokens) AS total_tokens, SUM(cost_usd) AS cost_usd,
                            SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unpriced
                        FROM {self._collection_name}
                        WHERE {where_sql} AND {group_column} IS NOT NULL
                        GROUP BY key
                        ORDER BY SUM(cost_usd) DESC NULLS LAST
                        LIMIT %s
                        """,
                        params + [limit_groups],
                    )
                    groups = [
                        {
                            "key": row["key"], "requests": row["requests"],
                            "total_tokens": row["total_tokens"] or 0, "cost_usd": float(row["cost_usd"] or 0.0),
                            "unpriced": bool(row["unpriced"]),
                        }
                        for row in cursor.fetchall()
                    ]

                return {
                    "totals": {
                        "requests": totals_row["requests"] or 0,
                        "prompt_tokens": totals_row["prompt_tokens"] or 0,
                        "completion_tokens": totals_row["completion_tokens"] or 0,
                        "total_tokens": totals_row["total_tokens"] or 0,
                        "cost_usd": float(totals_row["cost_usd"] or 0.0),
                        "unpriced_requests": totals_row["unpriced_requests"] or 0,
                        "unreported_requests": totals_row["unreported_requests"] or 0,
                    },
                    "series": series,
                    "groups": groups,
                }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, run)

    async def close(self) -> None:
        """Close Postgres audit storage resources."""
        if self._database_service and self._owns_database_service:
            try:
                self._database_service.close()
            except Exception as e:
                logger.error(f"Error closing Postgres audit database service: {e}")

        self._initialized = False

    def _unflatten_record(self, flat_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a flat Postgres record back to nested format.

        Args:
            flat_record: Record with flattened fields

        Returns:
            Record with nested ip_metadata and api_key structures
        """
        query = flat_record.get('query', '')
        response = flat_record.get('response', '')
        is_compressed = bool(flat_record.get('response_compressed', 0))

        if is_compressed and response:
            try:
                response = decompress_text(response)
            except Exception as e:
                logger.warning(f"Failed to decompress response: {e}")

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

        if flat_record.get('api_key_value'):
            result['api_key'] = {
                'key': flat_record.get('api_key_value'),
                'timestamp': flat_record.get('api_key_timestamp')
            }
            if flat_record.get('api_key_id'):
                result['api_key']['id'] = flat_record.get('api_key_id')

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
        Clear all audit records from the Postgres audit_logs table.

        Returns:
            True if cleared successfully, False otherwise
        """
        if not self._initialized:
            await self.initialize()

        try:
            deleted_count = await self._database_service.clear_collection(
                self._collection_name
            )
            logger.info(f"Cleared {deleted_count} audit records from Postgres table '{self._collection_name}'")
            return True

        except Exception as e:
            logger.error(f"Error clearing Postgres audit records: {e}")
            return False
