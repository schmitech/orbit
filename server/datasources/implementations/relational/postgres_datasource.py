"""
PostgreSQL Datasource Implementation
"""

import logging
from ...base.base_datasource import BaseDatasource

logger = logging.getLogger(__name__)


class PostgreSQLDatasource(BaseDatasource):
    """PostgreSQL database datasource implementation with connection pooling."""

    @property
    def datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return 'postgres'

    async def initialize(self) -> None:
        """Initialize the PostgreSQL database connection pool."""
        postgres_config = self.config.get('datasources', {}).get('postgres', {})

        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            # Extract connection parameters
            host = postgres_config.get('host', 'localhost')
            port = postgres_config.get('port', 5432)
            database = postgres_config.get('database', 'postgres')
            username = postgres_config.get('username', 'postgres')
            password = postgres_config.get('password', '')
            sslmode = postgres_config.get('sslmode', 'prefer')

            # Pool settings
            pool_size = postgres_config.get('pool_size', 10)
            min_pool_size = postgres_config.get('min_pool_size', 2)
            connection_timeout = postgres_config.get('connection_timeout', 5)
            statement_timeout = postgres_config.get('statement_timeout', 10000)
            validate_on_borrow = postgres_config.get('validate_on_borrow', True)

            logger.info(f"Initializing PostgreSQL connection pool to {host}:{port}/{database} "
                        f"(pool_size={pool_size}, min={min_pool_size})")

            # Build conninfo string for the pool
            conninfo = psycopg.conninfo.make_conninfo(
                host=host,
                port=port,
                dbname=database,
                user=username,
                password=password,
                sslmode=sslmode,
                connect_timeout=connection_timeout,
                options=f'-c statement_timeout={statement_timeout}'
            )

            # Create connection pool
            self._pool = ConnectionPool(
                conninfo=conninfo,
                min_size=min_pool_size,
                max_size=pool_size,
                kwargs={"row_factory": dict_row},
            )

            self._validate_on_borrow = validate_on_borrow

            # Test a connection from the pool
            conn = self._pool.getconn()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()
                cursor.close()

                if version:
                    logger.info(f"PostgreSQL connection successful: {version['version']}")
            finally:
                self._pool.putconn(conn)

            self._initialized = True

        except ImportError as e:
            self._client = None
            self._initialized = False
            raise RuntimeError("psycopg is required for PostgreSQLDatasource") from e
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise

    def get_connection(self):
        """Get a connection from the pool, validating if configured."""
        if not hasattr(self, '_pool') or not self._pool:
            return self._client

        conn = self._pool.getconn()

        if getattr(self, '_validate_on_borrow', False):
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            except Exception:
                # Connection is stale, close it and get a new one
                try:
                    conn.close()
                except Exception:
                    pass
                conn = self._pool.getconn()

        return conn

    def get_client(self):
        """Get a dedicated client connection for legacy callers."""
        if self._client is None and hasattr(self, '_pool') and self._pool:
            self._client = self.get_connection()
        return super().get_client()

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if hasattr(self, '_pool') and self._pool:
            self._pool.putconn(conn)

    async def health_check(self) -> bool:
        """Perform a health check on the PostgreSQL connection pool."""
        if not self._initialized:
            return False

        try:
            if hasattr(self, '_pool') and self._pool:
                conn = self._pool.getconn()
                try:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    return True
                finally:
                    self._pool.putconn(conn)
            elif self._client:
                cursor = self._client.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
                return True
            return False
        except Exception as e:
            logger.error(f"PostgreSQL health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the PostgreSQL connection pool."""
        if hasattr(self, '_pool') and self._pool:
            # Return the backward-compat client first
            if self._client:
                try:
                    self._pool.putconn(self._client)
                except Exception:
                    pass
                self._client = None
            self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")
        elif self._client:
            self._client.close()
            self._client = None
            logger.info("PostgreSQL connection closed")
        self._initialized = False
