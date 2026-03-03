"""
SQL Server Database Datasource Implementation
"""

import logging
import queue
import threading
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class SQLServerDatasource(BaseDatasource):
    """Microsoft SQL Server database datasource implementation with connection pooling."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'sqlserver'

    async def initialize(self) -> None:
        """Initialize the SQL Server database connection pool."""
        sqlserver_config = self.config.get('datasources', {}).get('sqlserver', {})

        try:
            import pymssql
        except ImportError:
            logger.warning("pymssql not available. Install with: pip install pymssql")
            self._client = None
            self._initialized = True
            return

        # Extract connection parameters
        host = sqlserver_config.get('host', 'localhost')
        port = sqlserver_config.get('port', 1433)
        database = sqlserver_config.get('database', 'master')
        username = sqlserver_config.get('username', 'sa')
        password = sqlserver_config.get('password', '')

        # Pool settings
        pool_size = sqlserver_config.get('pool_size', 10)
        min_pool_size = sqlserver_config.get('min_pool_size', 2)
        connection_timeout = sqlserver_config.get('connection_timeout', 5)

        try:
            logger.info(f"Initializing SQL Server connection pool to {host}:{port}/{database} "
                        f"(pool_size={pool_size})")

            # pymssql doesn't have built-in pooling, use a simple thread-safe queue-based pool
            self._conn_params = {
                'server': host,
                'port': port,
                'database': database,
                'user': username,
                'password': password,
                'autocommit': True,
                'login_timeout': connection_timeout
            }
            self._pool_queue = queue.Queue(maxsize=pool_size)
            self._pool_lock = threading.Lock()
            self._pool_size = pool_size

            # Pre-create minimum connections
            for _ in range(min_pool_size):
                conn = pymssql.connect(**self._conn_params)
                self._pool_queue.put(conn)

            # Test a connection
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT @@VERSION")
                version = cursor.fetchone()
                cursor.close()

                if version:
                    logger.info(f"SQL Server connection successful: {version[0][:50]}...")
            finally:
                self.return_connection(conn)

            # Expose a single client for backward compatibility
            self._client = self.get_connection()

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to connect to SQL Server database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise

    def get_connection(self):
        """Get a connection from the pool."""
        if not hasattr(self, '_pool_queue'):
            return self._client

        try:
            conn = self._pool_queue.get_nowait()
            # Validate connection
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                import pymssql
                conn = pymssql.connect(**self._conn_params)
            return conn
        except queue.Empty:
            # Pool exhausted, create a new connection
            import pymssql
            return pymssql.connect(**self._conn_params)

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if hasattr(self, '_pool_queue'):
            try:
                self._pool_queue.put_nowait(conn)
            except queue.Full:
                conn.close()

    async def health_check(self) -> bool:
        """Perform a health check on the SQL Server connection pool."""
        if not self._initialized:
            return False

        try:
            conn = self.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            finally:
                self.return_connection(conn)
        except Exception as e:
            logger.error(f"SQL Server health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the SQL Server connection pool."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        if hasattr(self, '_pool_queue'):
            while not self._pool_queue.empty():
                try:
                    conn = self._pool_queue.get_nowait()
                    conn.close()
                except Exception:
                    pass
            self._pool_queue = None

        self._initialized = False
        logger.info("SQL Server connection pool closed")
