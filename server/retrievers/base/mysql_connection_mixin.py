"""
Shared MySQL connection creation/teardown for the intent/ and relational/
MySQL retrievers.

Extracted per docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md
Item 1, step 5. Supports the union of both variants' current connection
options (SSL toggle, autocommit, charset, sql_mode, dictionary cursor,
PyMySQL fallback) so each caller can reproduce its own existing default
behavior exactly -- this mixin changes no retriever's production behavior
by itself; each subclass still decides what to pass in.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MySQLConnectionMixin:
    """Mixin providing shared MySQL connection creation and teardown."""

    async def _create_mysql_connection(
        self,
        *,
        charset: str | None = None,
        sql_mode: str | None = None,
        ssl_disabled: bool = False,
        autocommit: bool | None = None,
        use_dictionary_cursor: bool = False,
        allow_pymysql_fallback: bool = False,
    ) -> Any:
        """
        Create a MySQL connection.

        Args:
            charset: Connection charset, omitted from connect() if None.
            sql_mode: Connection sql_mode, omitted from connect() if None.
            ssl_disabled: If False, passes use_ssl=True to mysql-connector.
            autocommit: Passed to connect() if not None; omitted otherwise.
            use_dictionary_cursor: Use a dict-style cursor for the post-connect
                version check (matches the intent/ variant's behavior).
            allow_pymysql_fallback: Fall back to PyMySQL if mysql-connector
                is not importable (matches the relational/ variant's behavior).
        """
        connect_kwargs: dict[str, Any] = {
            'host': self.connection_params['host'],
            'port': self.connection_params['port'],
            'database': self.connection_params['database'],
            'user': self.connection_params['username'],
            'password': self.connection_params['password'],
        }
        if charset is not None:
            connect_kwargs['charset'] = charset
        if sql_mode is not None:
            connect_kwargs['sql_mode'] = sql_mode
        if autocommit is not None:
            connect_kwargs['autocommit'] = autocommit
        if not ssl_disabled:
            connect_kwargs['use_ssl'] = True

        try:
            try:
                import mysql.connector
                connection = mysql.connector.connect(**connect_kwargs)
            except ImportError:
                if not allow_pymysql_fallback:
                    raise
                import pymysql
                pymysql_kwargs: dict[str, Any] = {
                    'host': connect_kwargs['host'],
                    'port': connect_kwargs['port'],
                    'database': connect_kwargs['database'],
                    'user': connect_kwargs['user'],
                    'password': connect_kwargs['password'],
                    'cursorclass': pymysql.cursors.DictCursor,
                }
                if charset is not None:
                    pymysql_kwargs['charset'] = charset
                connection = pymysql.connect(**pymysql_kwargs)

            cursor = connection.cursor(dictionary=True) if use_dictionary_cursor else connection.cursor()
            cursor.execute("SELECT VERSION() as version" if use_dictionary_cursor else "SELECT VERSION()")
            version = cursor.fetchone()
            cursor.close()

            if version:
                if use_dictionary_cursor:
                    version_str = version.get('version')
                else:
                    version_str = version.get('VERSION()') if isinstance(version, dict) else version[0]
                logger.debug(f"MySQL connection successful: {version_str}")

            return connection

        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    async def _close_mysql_connection(self) -> None:
        """Close the MySQL connection if one is set."""
        if self.connection:
            self.connection.close()
