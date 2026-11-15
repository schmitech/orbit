"""
AWS Athena Intent Retriever using the unified base classes.
"""

import logging
from typing import Any, Optional

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.base.sql_param_binding import (
    convert_named_style,
    convert_qmark_to_pyformat,
    escape_literal_percents_for_pyformat,
)

logger = logging.getLogger(__name__)


class IntentAthenaRetriever(IntentSQLRetriever):
    """
    Athena-specific intent retriever using the unified SQL intent base.
    """

    def __init__(self, config: dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize Athena intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)

        self.region_name = self.datasource_config.get('region_name', 'us-east-1')
        self.work_group = self.datasource_config.get('work_group', 'primary')

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "athena"

    def get_default_port(self) -> int:
        """Athena does not use a TCP port in retriever config."""
        return 0

    def get_default_database(self) -> str:
        """Athena default schema name."""
        return "default"

    def get_default_username(self) -> str:
        """Athena does not use database usernames."""
        return ""

    async def create_connection(self) -> Any:
        """
        Connection is managed by datasource registry.
        Kept for compatibility with the base interface.
        """
        if self.connection:
            return self.connection
        raise ValueError("Athena datasource connection not initialized")

    def get_test_query(self) -> str:
        """Athena test query."""
        return "SELECT 1 AS test"

    def _is_connection_alive(self) -> bool:
        """Check if Athena connection is still alive."""
        try:
            if not self.connection:
                return False
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:  # noqa: BLE001 - pyathena driver boundary, connection check must fail safe
            return False

    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> list[Any]:
        """
        Execute Athena query with parameter-format normalization.
        PyAthena supports `%(name)s` style best, so normalize `:name` and `?`.
        """
        cursor = None
        try:
            if not self._is_connection_alive():
                raise RuntimeError("Athena connection is closed")

            normalized_query = query
            normalized_params: Any = params

            if isinstance(normalized_params, dict):
                normalized_query = convert_named_style(normalized_query, to_style='pyformat')
                # PyAthena uses pyformat; escape literal % in SQL LIKE patterns, etc.
                normalized_query = escape_literal_percents_for_pyformat(normalized_query)
            elif isinstance(normalized_params, (list, tuple)) and '?' in normalized_query:
                # Cap conversion at the number of supplied values: the query
                # text can contain more literal '?' characters (e.g. inside a
                # string literal) than there are real placeholders to bind.
                normalized_query, generated_names = convert_qmark_to_pyformat(
                    normalized_query, max_replacements=len(normalized_params)
                )
                normalized_params = dict(zip(generated_names, normalized_params))
                normalized_query = escape_literal_percents_for_pyformat(normalized_query)

            cursor = self.connection.cursor()
            if normalized_params is None:
                cursor.execute(normalized_query)
            else:
                cursor.execute(normalized_query, normalized_params)

            query_upper = normalized_query.strip().upper()
            if query_upper.startswith("SELECT") or query_upper.startswith("WITH"):
                rows = cursor.fetchall()
                if rows and isinstance(rows[0], dict):
                    return rows

                # Fallback for non-dict cursor rows.
                description = cursor.description or []
                columns = [col[0] for col in description]
                if columns:
                    return [dict(zip(columns, row)) for row in rows]
                return []

            # Athena is typically read-only for this adapter; return generic result.
            return [{"affected_rows": cursor.rowcount}]

        except Exception as e:
            logger.error(f"Athena query execution error: {e}")
            raise
        finally:
            if cursor:
                cursor.close()

    async def _close_connection(self) -> None:
        """Connection lifecycle is handled by datasource pool."""
        return None


# Register the Athena intent retriever
RetrieverFactory.register_retriever('intent_athena', IntentAthenaRetriever)
