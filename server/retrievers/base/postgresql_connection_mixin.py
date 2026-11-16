"""
Shared PostgreSQL connection creation/teardown for the intent/ and
relational/ PostgreSQL retrievers.

Extracted per docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md
Item 1, Postgres follow-up to step 5. Explicit decision (confirmed with the
user, 2026-11-15): this mixin stays pooling-agnostic -- it supports both the
pooled path (intent/, via psycopg_pool) and the unpooled path (relational/)
as configurable options, but does not itself decide whether a given
retriever should pool. postgres_datasource.py's own independent pool is
untouched by this mixin either way.
"""

import logging
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional dependency for tests
    psycopg = None
    dict_row = None

try:
    import psycopg_pool
except ImportError:  # pragma: no cover - optional dependency; only needed when use_pool=True
    psycopg_pool = None

logger = logging.getLogger(__name__)


class PostgreSQLConnectionMixin:
    """Mixin providing shared PostgreSQL connection creation and teardown."""

    async def _create_postgresql_connection(
        self,
        *,
        sslmode: str = 'prefer',
        connect_timeout: int | None = None,
        statement_timeout: int | None = None,
        autocommit: bool | None = None,
        use_pool: bool = False,
        pool_size: int = 10,
        install_extras: str = 'binary',
    ) -> Any:
        """
        Create a PostgreSQL connection, or a pooled connection if use_pool is
        True.

        Args:
            sslmode: psycopg sslmode.
            connect_timeout: Connection timeout in seconds, applied if not None.
            statement_timeout: Statement timeout in ms; only used to build the
                pool's conninfo (matches the intent/ variant's pooled behavior).
            autocommit: Set on the connection after connecting, if not None;
                only applies to the unpooled path (matches the intent/
                variant's non-pooled behavior of forcing autocommit=False).
            use_pool: If True, create (or reuse) a psycopg_pool.ConnectionPool
                stored on self.connection_pool and get a connection from it.
                NOTE -- intentional behavior change from the pre-extraction
                intent/ variant, not a preserved-as-is extraction: the
                original code only got a pooled connection on the *first*
                call (`if self.use_connection_pool and not self.connection_pool`);
                once a pool existed, every later call fell through to the
                `else` branch and opened a brand-new standalone (non-pooled)
                connection instead of reusing the pool. That looked like an
                unintentional bug, not a deliberate design choice, so this
                extraction fixes it: every call with use_pool=True now always
                gets a connection from the pool, creating the pool once and
                reusing it thereafter. Flagged here explicitly since this is
                the one place this extraction does NOT preserve exact
                pre-existing behavior.
            pool_size: Pool max_size, only used when use_pool is True.
            install_extras: psycopg install extras named in the ImportError
                message (e.g. "binary" or "binary,pool").
        """
        if psycopg is None:
            raise ImportError(f"psycopg not available. Install with: pip install 'psycopg[{install_extras}]'")
        if use_pool and psycopg_pool is None:
            raise ImportError("psycopg_pool not available. Install with: pip install 'psycopg[pool]'")

        try:
            if use_pool:
                if not getattr(self, 'connection_pool', None):
                    conninfo_kwargs: dict[str, Any] = {
                        'host': self.connection_params['host'],
                        'port': self.connection_params['port'],
                        'dbname': self.connection_params['database'],
                        'user': self.connection_params['username'],
                        'password': self.connection_params['password'],
                        'sslmode': sslmode,
                    }
                    if connect_timeout is not None:
                        conninfo_kwargs['connect_timeout'] = connect_timeout
                    if statement_timeout is not None:
                        conninfo_kwargs['options'] = f'-c statement_timeout={statement_timeout}'

                    conninfo = psycopg.conninfo.make_conninfo(**conninfo_kwargs)
                    self.connection_pool = psycopg_pool.ConnectionPool(
                        conninfo=conninfo,
                        min_size=2,
                        max_size=pool_size,
                        kwargs={"row_factory": dict_row},
                    )
                    logger.debug(f"Created PostgreSQL connection pool with size {pool_size}")

                connection = self.connection_pool.getconn()
            else:
                connect_kwargs: dict[str, Any] = {
                    'host': self.connection_params['host'],
                    'port': self.connection_params['port'],
                    'dbname': self.connection_params['database'],
                    'user': self.connection_params['username'],
                    'password': self.connection_params['password'],
                    'sslmode': sslmode,
                    'row_factory': dict_row,
                }
                if connect_timeout is not None:
                    connect_kwargs['connect_timeout'] = connect_timeout

                connection = psycopg.connect(**connect_kwargs)

                if autocommit is not None:
                    connection.autocommit = autocommit

            cursor = connection.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()

            if version:
                logger.debug(f"PostgreSQL connection successful: {version['version']}")

            return connection

        except ImportError:
            logger.error(f"psycopg not available. Install with: pip install 'psycopg[{install_extras}]'")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def _is_postgresql_connection_alive(self) -> bool:
        """Check if the PostgreSQL connection is still alive."""
        try:
            if not self.connection:
                return False
            if self.connection.closed:
                return False
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:  # noqa: BLE001 - psycopg driver boundary; liveness check must fail safe
            return False

    async def _close_postgresql_connection(self, use_pool: bool = False) -> None:
        """Close the connection, or return it to the pool if use_pool is True."""
        if self.connection:
            if use_pool and getattr(self, 'connection_pool', None):
                self.connection_pool.putconn(self.connection)
                logger.debug("Returned connection to pool")
            else:
                self.connection.close()

        if use_pool and getattr(self, 'connection_pool', None):
            self.connection_pool.close()
            self.connection_pool = None
            logger.debug("Closed PostgreSQL connection pool")
