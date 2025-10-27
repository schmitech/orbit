"""
SQLite Intent Retriever using the unified base classes.
Similar to IntentPostgreSQLRetriever but for SQLite databases.
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import sqlite3
    _OperationalError = sqlite3.OperationalError
except ImportError:  # pragma: no cover - optional dependency for tests
    sqlite3 = None

    class _OperationalError(Exception):
        """Fallback when sqlite3 is unavailable."""

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentSQLiteRetriever(IntentSQLRetriever):
    """
    SQLite-specific intent retriever using unified base.
    Inherits all intent functionality and SQLite connection handling.
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
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
            # Get database path from multiple possible config locations
            # Priority: database_path > database > db_path > default
            if 'database_path' in self.datasource_config:
                self.database_path = self.datasource_config['database_path']
            elif 'database' in self.datasource_config:
                self.database_path = self.datasource_config['database']
            elif 'db_path' in self.datasource_config:
                self.database_path = self.datasource_config['db_path']
            elif 'database' in self.connection_params:
                self.database_path = self.connection_params['database']
            else:
                self.database_path = self.get_default_database()

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

            if version and self.verbose:
                logger.info(f"SQLite connection successful: version {version[0]}")

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
        except:
            return False

    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute SQLite query with intent-specific handling."""
        cursor = None
        try:
            # Check connection health before executing
            if not self._is_connection_alive():
                raise _OperationalError("connection is closed")

            cursor = self.connection.cursor()

            # SQLite uses ? placeholders, but we might receive %(name)s format from templates
            # Convert named parameters to SQLite format
            import re

            # Check if query has parameter placeholders
            has_param_placeholders = bool(re.search(r'%\((\w+)\)s', query))

            if has_param_placeholders:
                # Convert %(name)s format to :name format for SQLite
                converted_query = re.sub(r'%\((\w+)\)s', r':\1', query)

                # Ensure we have params dict
                if not params:
                    params = {}
                elif not isinstance(params, dict):
                    params = {}

                cursor.execute(converted_query, params)
            else:
                # Handle ? placeholders (positional parameters)
                # Check if there are ? placeholders in the query
                placeholder_count = query.count('?')

                if placeholder_count > 0:
                    # Need to convert params dict to tuple/list for ? placeholders
                    if params and isinstance(params, dict):
                        # Extract parameter values in order (based on template parameter order)
                        # Common parameter names: limit, offset
                        param_values = []
                        for key in ['limit', 'offset']:  # Standard order for pagination
                            if key in params:
                                param_values.append(params[key])

                        # If we don't have enough params, try all dict values
                        if len(param_values) < placeholder_count:
                            param_values = list(params.values())

                        cursor.execute(query, tuple(param_values))
                    elif params and isinstance(params, (list, tuple)):
                        cursor.execute(query, params)
                    else:
                        # No params provided but query has placeholders - use None values
                        cursor.execute(query, tuple([None] * placeholder_count))
                else:
                    # No placeholders, execute without params
                    cursor.execute(query)

            if query.strip().upper().startswith("SELECT"):
                # Convert Row objects to dictionaries
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]

        except Exception as e:
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
            if self.verbose:
                logger.info("Closed SQLite connection")


# Register the intent SQLite retriever
RetrieverFactory.register_retriever('intent_sqlite', IntentSQLiteRetriever)