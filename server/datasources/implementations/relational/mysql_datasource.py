"""
MySQL Database Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class MySQLDatasource(BaseDatasource):
    """MySQL database datasource implementation with connection pooling."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'mysql'

    async def initialize(self) -> None:
        """Initialize the MySQL database connection pool."""
        mysql_config = self.config.get('datasources', {}).get('mysql', {})

        try:
            import mysql.connector
            from mysql.connector import pooling, Error
        except ImportError as e:
            self._client = None
            self._initialized = False
            raise RuntimeError("mysql-connector-python is required for MySQLDatasource") from e

        # Extract connection parameters
        host = mysql_config.get('host', 'localhost')
        port = mysql_config.get('port', 3306)
        database = mysql_config.get('database', 'mysql')
        username = mysql_config.get('username', 'root')
        password = mysql_config.get('password', '')

        # Pool settings
        pool_size = mysql_config.get('pool_size', 10)
        connection_timeout = mysql_config.get('connection_timeout', 5)
        statement_timeout = mysql_config.get('statement_timeout', 10000)

        try:
            logger.info(f"Initializing MySQL connection pool to {host}:{port}/{database} "
                        f"(pool_size={pool_size})")

            # Create connection pool
            self._pool = pooling.MySQLConnectionPool(
                pool_name="orbit_mysql_pool",
                pool_size=min(pool_size, 32),  # MySQL connector max is 32
                pool_reset_session=True,
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                autocommit=True,
                connect_timeout=connection_timeout
            )

            self._statement_timeout = statement_timeout

            # Test a connection from the pool
            conn = self._pool.get_connection()
            try:
                cursor = conn.cursor()
                # Set session timeout
                cursor.execute(f"SET SESSION wait_timeout = {statement_timeout // 1000}")
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                cursor.close()

                if version:
                    logger.info(f"MySQL connection successful: {version[0]}")
            finally:
                conn.close()

            self._initialized = True

        except Error as e:
            logger.error(f"Failed to connect to MySQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MySQL: {str(e)}")
            raise

    def get_connection(self):
        """Get a connection from the pool."""
        if hasattr(self, '_pool') and self._pool:
            conn = self._pool.get_connection()
            # Set statement timeout on each connection
            if hasattr(self, '_statement_timeout'):
                try:
                    cursor = conn.cursor()
                    cursor.execute(f"SET SESSION wait_timeout = {self._statement_timeout // 1000}")
                    cursor.close()
                except Exception:
                    pass
            return conn
        return self._client

    def get_client(self):
        """Get a dedicated client connection for legacy callers."""
        if self._client is None and hasattr(self, '_pool') and self._pool:
            self._client = self.get_connection()
        return super().get_client()

    def return_connection(self, conn):
        """Return a connection to the pool (MySQL connector auto-returns on close)."""
        if conn and hasattr(self, '_pool') and self._pool:
            conn.close()

    async def health_check(self) -> bool:
        """Perform a health check on the MySQL connection pool."""
        if not self._initialized or not (self._client or hasattr(self, '_pool')):
            return False

        try:
            if hasattr(self, '_pool') and self._pool:
                conn = self._pool.get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    return True
                finally:
                    conn.close()
            elif self._client:
                cursor = self._client.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            return False
        except Exception as e:
            logger.error(f"MySQL health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the MySQL connection pool."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        # Note: mysql.connector pool doesn't have a closeall() method;
        # connections are returned/closed individually
        if hasattr(self, '_pool'):
            self._pool = None
        self._initialized = False
        logger.info("MySQL connection pool closed")
