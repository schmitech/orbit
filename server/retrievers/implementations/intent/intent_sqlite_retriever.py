"""
SQLite Intent Retriever using the unified base classes.
Similar to IntentPostgreSQLRetriever but for SQLite databases.
"""

import logging
from typing import Any, Optional

try:
    import sqlite3
    _OperationalError = sqlite3.OperationalError
except ImportError:  # pragma: no cover - optional dependency for tests
    sqlite3 = None

    class _OperationalError(Exception):
        """Fallback when sqlite3 is unavailable."""

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.base.sql_param_binding import convert_named_style, detect_placeholder_style

logger = logging.getLogger(__name__)


class IntentSQLiteRetriever(IntentSQLRetriever):
    """
    SQLite-specific intent retriever using unified base.
    Inherits all intent functionality and SQLite connection handling.
    """

    def __init__(self, config: dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize SQLite intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)

        # SQLite-specific settings
        self.database_path = None
        self.check_same_thread = self.datasource_config.get('check_same_thread', False)

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "sqlite"

    def get_default_port(self) -> int:
        """SQLite doesn't use ports, return None."""
        return None

    def get_default_database(self) -> str:
        """SQLite default database path."""
        return 'orbit.db'

    def get_default_username(self) -> str:
        """SQLite doesn't use usernames."""
        return None

    async def create_connection(self) -> Any:
        """Create SQLite connection."""
        try:
            if sqlite3 is None:
                raise ImportError("sqlite3 not available")

            # SQLite uses a file path instead of host/port
            self.database_path = self.resolve_file_database_path(self.datasource_config, self.connection_params)

            # Create connection
            connection = sqlite3.connect(
                self.database_path,
                check_same_thread=self.check_same_thread,
                timeout=self.connection_timeout if self.connection_timeout else 5.0
            )

            # Enable row factory for dict-like access
            connection.row_factory = sqlite3.Row

            # Test connection
            cursor = connection.cursor()
            cursor.execute("SELECT sqlite_version();")
            version = cursor.fetchone()

            if version:
                logger.debug(f"SQLite connection successful: version {version[0]}")

            # Verify database has tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            tables = cursor.fetchall()
            cursor.close()

            if tables:
                table_names = [row[0] for row in tables]
                logger.info(f"Connected to SQLite database with {len(table_names)} tables: {', '.join(table_names[:5])}")
            else:
                logger.warning(f"SQLite database at '{self.database_path}' has no tables!")

            return connection

        except ImportError:
            logger.error("sqlite3 not available")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise

    def get_test_query(self) -> str:
        """SQLite test query."""
        return "SELECT 1 as test"

    def _is_connection_alive(self) -> bool:
        """Check if SQLite connection is still alive."""
        try:
            if not self.connection:
                return False
            # Try a simple query to verify connection is working
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:  # noqa: BLE001 - sqlite3 driver boundary; connection-health probe must fail safe
            return False

    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> list[Any]:
        """Execute SQLite query with intent-specific handling."""
        cursor = None
        try:
            # Check connection health before executing
            if not self._is_connection_alive():
                raise _OperationalError("connection is closed")

            cursor = self.connection.cursor()

            # SQLite's sqlite3 module natively supports ':name' and '?'
            # placeholders, but not '%(name)s' -- convert that one case via
            # the shared helper (retrievers/base/sql_param_binding.py).
            #
            # Branch on the TYPE of params the caller supplied, not on
            # placeholder style detected from the query text: style detection
            # is a regex over the rendered SQL string, so a string literal
            # like '12:30' can look like a ':30' named placeholder. A caller
            # that already supplied a positional tuple/list has unambiguously
            # declared "bind these positionally" regardless of what a literal
            # elsewhere in the query happens to look like.
            if params is not None and isinstance(params, (list, tuple)):
                placeholder_count = query.count('?')
                if placeholder_count > 0:
                    cursor.execute(query, tuple(params))
                else:
                    cursor.execute(query)
            elif params and isinstance(params, dict):
                style = detect_placeholder_style(query)
                if style == 'qmark':
                    raise ValueError(
                        "SQLite received dict params with ? placeholders; caller must "
                        f"convert params to a positional sequence using template parameter order. Query: {query[:100]}"
                    )
                converted_query = convert_named_style(query, to_style='colon')
                cursor.execute(converted_query, params)
            else:
                # No params provided.
                placeholder_count = query.count('?')
                if placeholder_count > 0:
                    # Query has ? placeholders but no params - use None values
                    cursor.execute(query, tuple([None] * placeholder_count))
                else:
                    cursor.execute(query)

            query_upper = query.strip().upper()
            if query_upper.startswith("SELECT") or query_upper.startswith("WITH"):
                # Convert Row objects to dictionaries
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]

        except Exception:
            if self.connection:
                self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()

    async def _close_connection(self) -> None:
        """Close SQLite connection."""
        if self.connection:
            self.connection.close()
            logger.debug("Closed SQLite connection")


# Register the intent SQLite retriever
RetrieverFactory.register_retriever('intent_sqlite', IntentSQLiteRetriever)
