"""
DuckDB Intent Retriever using the unified base classes.
Similar to IntentSQLiteRetriever but for DuckDB databases.
"""

import logging
from typing import Dict, Any, List, Optional

try:
    import duckdb
    _OperationalError = Exception  # DuckDB doesn't have a specific OperationalError
except ImportError:  # pragma: no cover - optional dependency for tests
    duckdb = None

    class _OperationalError(Exception):
        """Fallback when duckdb is unavailable."""

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.base.base_retriever import RetrieverFactory

logger = logging.getLogger(__name__)


class IntentDuckDBRetriever(IntentSQLRetriever):
    """
    DuckDB-specific intent retriever using unified base.
    Inherits all intent functionality and DuckDB connection handling.
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """Initialize DuckDB intent retriever."""
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)

        # DuckDB-specific settings
        # Priority: adapter_config > datasource_config > defaults
        self.database_path = None
        self.read_only = self.intent_config.get('read_only', 
                        self.datasource_config.get('read_only', False))
        self.access_mode = self.intent_config.get('access_mode',
                          self.datasource_config.get('access_mode', 'automatic'))
        self.threads = self.intent_config.get('threads',
                     self.datasource_config.get('threads', None))

    def _get_datasource_name(self) -> str:
        """Return the datasource name."""
        return "duckdb"

    def get_default_port(self) -> int:
        """DuckDB doesn't use ports, return None."""
        return None

    def get_default_database(self) -> str:
        """DuckDB default database path."""
        return ':memory:'

    def get_default_username(self) -> str:
        """DuckDB doesn't use usernames."""
        return None

    async def create_connection(self) -> Any:
        """Create DuckDB connection."""
        try:
            if duckdb is None:
                raise ImportError("duckdb not available. Install with: pip install duckdb")

            # DuckDB uses a file path or :memory: instead of host/port
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

            # Configure connection parameters
            config_params = {}
            if self.access_mode and self.access_mode != 'automatic':
                config_params['access_mode'] = self.access_mode
            if self.threads is not None:
                config_params['threads'] = self.threads

            # Log connection settings for debugging
            logger.debug(f"DuckDB connection settings: read_only={self.read_only}, access_mode={self.access_mode}, database={self.database_path}")

            # Create connection with read-only and access_mode settings
            if config_params:
                connection = duckdb.connect(
                    self.database_path,
                    read_only=self.read_only,
                    config=config_params
                )
            else:
                connection = duckdb.connect(
                    self.database_path,
                    read_only=self.read_only
                )
            
            logger.debug(f"DuckDB connection created: read_only={self.read_only}, access_mode={self.access_mode if config_params else 'automatic'}")

            # Load HTTP/S remote file support (for CSV/Parquet reads)
            # Note: INSTALL requires write access, so skip in read-only mode
            if not self.read_only:
                try:
                    connection.execute("INSTALL httpfs;")
                    connection.execute("LOAD httpfs;")
                    logger.debug("DuckDB httpfs extension loaded for remote file support")
                except Exception as extension_error:
                    logger.warning(f"Failed to load DuckDB httpfs extension: {extension_error}")
            else:
                # In read-only mode, try to load without installing (if already installed)
                try:
                    connection.execute("LOAD httpfs;")
                    logger.debug("DuckDB httpfs extension loaded (read-only mode)")
                except Exception:
                    logger.error("DuckDB httpfs extension not available (read-only mode)")

            # Test connection
            result = connection.execute("SELECT version();").fetchone()

            if result:
                logger.debug(f"DuckDB connection successful: version {result[0]}")

            # Verify database has tables (if not in-memory)
            if self.database_path != ':memory:':
                tables_result = connection.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'main'
                    ORDER BY table_name;
                """).fetchall()

                if tables_result:
                    table_names = [row[0] for row in tables_result]
                    logger.info(f"Connected to DuckDB database with {len(table_names)} tables: {', '.join(table_names[:5])}")
                else:
                    logger.warning(f"DuckDB database at '{self.database_path}' has no tables!")

            # Set the connection on self so it can be accessed via the connection property
            self._connection = connection
            
            return connection

        except ImportError:
            logger.error("duckdb not available. Install with: pip install duckdb")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to DuckDB: {e}")
            raise

    def get_test_query(self) -> str:
        """DuckDB test query."""
        return "SELECT 1 as test"

    def _is_connection_alive(self) -> bool:
        """Check if DuckDB connection is still alive."""
        try:
            if not self.connection:
                return False
            # Try a simple query to verify connection is working
            self.connection.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    async def _execute_raw_query(self, query: str, params: Optional[Any] = None) -> List[Any]:
        """Execute DuckDB query with intent-specific handling."""
        try:
            # Check connection health before executing
            if not self._is_connection_alive():
                raise _OperationalError("connection is closed")

            # DuckDB uses standard parameterized queries
            # Can handle both named parameters (%(name)s) and positional (?)
            # DuckDB's execute() method accepts parameters as a dict for named or tuple for positional
            
            # DuckDB uses ? for positional parameters
            # Convert named parameters to positional parameters
            import re
            
            if params and isinstance(params, dict):
                # Check if query has %(name)s format (PostgreSQL-style from templates)
                has_postgres_style = bool(re.search(r'%\((\w+)\)s', query))
                
                if has_postgres_style:
                    # Convert %(name)s to ? placeholders
                    # Extract parameter names in order
                    param_names = re.findall(r'%\((\w+)\)s', query)
                    # Replace with ? placeholders
                    converted_query = re.sub(r'%\((\w+)\)s', '?', query)
                    # Build positional parameter list in order of appearance
                    param_values = [params[name] for name in param_names if name in params]
                    result = self.connection.execute(converted_query, param_values)
                else:
                    # Check if query has :name format (named parameters)
                    has_named_params = bool(re.search(r':(\w+)', query))
                    
                    if has_named_params:
                        # Convert :name to ? placeholders
                        # Extract parameter names in order
                        param_names = re.findall(r':(\w+)', query)
                        # Replace with ? placeholders
                        converted_query = re.sub(r':(\w+)', '?', query)
                        # Build positional parameter list in order of appearance
                        param_values = [params[name] for name in param_names if name in params]
                        result = self.connection.execute(converted_query, param_values)
                    else:
                        # Query uses ? placeholders already, convert dict to tuple
                        param_values = tuple(params.values())
                        result = self.connection.execute(query, param_values)
            elif params and isinstance(params, (list, tuple)):
                # Positional parameters - already in correct format
                result = self.connection.execute(query, params)
            else:
                # No parameters
                result = self.connection.execute(query)

            query_upper = query.strip().upper()
            if query_upper.startswith("SELECT") or query_upper.startswith("WITH"):
                # Fetch all results and convert to list of dicts
                rows = result.fetchall()
                
                # DuckDB stores description on the connection object after query execution
                # Try to get column names from connection.description
                column_names = []
                try:
                    if hasattr(self.connection, 'description') and self.connection.description:
                        column_names = [desc[0] for desc in self.connection.description]
                    # Alternative: get column names from result.columns if available
                    elif hasattr(result, 'columns'):
                        column_names = result.columns
                    # Alternative: get column names from result.description if available
                    elif hasattr(result, 'description') and result.description:
                        column_names = [desc[0] for desc in result.description]
                except Exception:
                    pass
                
                # Convert to list of dictionaries
                if column_names and rows:
                    return [dict(zip(column_names, row)) for row in rows]
                elif rows:
                    # Fallback: use column index numbers if no names available
                    return [dict(zip([f'col_{i}' for i in range(len(rows[0]))], row)) for row in rows]
                return []
            else:
                # Non-SELECT query (INSERT, UPDATE, DELETE, etc.)
                # DuckDB doesn't have rowcount in the same way, return success indicator
                return [{"affected_rows": 1}]

        except Exception as e:
            logger.error(f"DuckDB query execution error: {e}")
            raise

    async def _close_connection(self) -> None:
        """Close DuckDB connection."""
        if self.connection:
            try:
                self.connection.close()
                logger.debug("Closed DuckDB connection")
            except Exception as e:
                logger.warning(f"Error closing DuckDB connection: {e}")
            finally:
                # Clear the connection reference
                self._connection = None


# Register the intent DuckDB retriever
RetrieverFactory.register_retriever('intent_duckdb', IntentDuckDBRetriever)

