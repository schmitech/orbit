"""
Oracle Database Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class OracleDatasource(BaseDatasource):
    """Oracle Database datasource implementation with connection pooling."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'oracle'

    async def initialize(self) -> None:
        """Initialize the Oracle database connection pool."""
        oracle_config = self.config.get('datasources', {}).get('oracle', {})

        try:
            import oracledb
        except ImportError as e:
            self._client = None
            self._initialized = False
            raise RuntimeError("oracledb is required for OracleDatasource") from e

        # Extract connection parameters
        host = oracle_config.get('host', 'localhost')
        port = oracle_config.get('port', 1521)
        service_name = oracle_config.get('service_name', 'XE')
        username = oracle_config.get('username', 'system')
        password = oracle_config.get('password', '')

        # Pool settings
        pool_size = oracle_config.get('pool_size', 10)
        min_pool_size = oracle_config.get('min_pool_size', 2)
        connection_timeout = oracle_config.get('connection_timeout', 5)
        statement_timeout = oracle_config.get('statement_timeout', 10000)

        try:
            # Create DSN using the modern oracledb syntax
            dsn = f"{host}:{port}/{service_name}"

            logger.info(f"Initializing Oracle connection pool to {host}:{port}/{service_name} "
                        f"(pool_size={pool_size}, min={min_pool_size})")

            # Create connection pool using oracledb
            self._pool = oracledb.create_pool(
                user=username,
                password=password,
                dsn=dsn,
                min=min_pool_size,
                max=pool_size,
                increment=1,
                timeout=connection_timeout
            )

            self._statement_timeout = statement_timeout

            # Test a connection from the pool
            conn = self._pool.acquire()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                cursor.close()
            finally:
                self._pool.release(conn)

            logger.info("Oracle connection pool successful")

            self._initialized = True

        except Exception as e:
            logger.error(f"Failed to connect to Oracle database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{service_name} (user: {username})")
            raise

    def get_connection(self):
        """Get a connection from the pool."""
        if hasattr(self, '_pool') and self._pool:
            return self._pool.acquire()
        return self._client

    def get_client(self):
        """Get a dedicated client connection for legacy callers."""
        if self._client is None and hasattr(self, '_pool') and self._pool:
            self._client = self.get_connection()
        return super().get_client()

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if hasattr(self, '_pool') and self._pool:
            self._pool.release(conn)

    async def health_check(self) -> bool:
        """Perform a health check on the Oracle connection pool."""
        if not self._initialized:
            return False

        try:
            if hasattr(self, '_pool') and self._pool:
                conn = self._pool.acquire()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM DUAL")
                    cursor.fetchone()
                    cursor.close()
                    return True
                finally:
                    self._pool.release(conn)
            elif self._client:
                cursor = self._client.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                cursor.close()
                return True
            return False
        except Exception as e:
            logger.error(f"Oracle health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the Oracle connection pool."""
        if hasattr(self, '_pool') and self._pool:
            if self._client:
                try:
                    self._pool.release(self._client)
                except Exception:
                    pass
                self._client = None
            self._pool.close()
            self._pool = None
            logger.info("Oracle connection pool closed")
        elif self._client:
            self._client.close()
            self._client = None
            logger.info("Oracle connection closed")
        self._initialized = False
