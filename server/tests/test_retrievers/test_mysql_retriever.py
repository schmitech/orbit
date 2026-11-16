"""
Regression-baseline tests for MySQLRetriever's (relational/) *current*
connection lifecycle behavior (reconnection, transaction commit/rollback,
shutdown).

These exist to establish a behavior baseline before any connection-mixin
extraction is attempted, per docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md
Item 1, step 4. They do not test against a live MySQL server; mysql.connector
is mocked so the suite can run without a database. Unlike the intent/ variant,
MySQLRetriever.initialize() is a confirmed production caller of
create_connection() (lifecycle audit, 2026-11-15).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.relational.mysql_retriever import MySQLRetriever


class ConcreteMySQLRetriever(MySQLRetriever):
    """
    MySQLRetriever leaves set_collection() abstract (inherited from
    BaseRetriever) with no implementation anywhere in the relational/
    hierarchy, so it cannot be instantiated directly in tests. This minimal
    override is test-only scaffolding and does not change the class under
    test's connection-lifecycle behavior.
    """

    async def set_collection(self, collection_name: str) -> None:
        self.collection = collection_name


def make_config(**datasource_overrides):
    datasource = {
        "host": "localhost",
        "port": 3306,
        "database": "testdb",
        "username": "root",
        "password": "secret",
        "collection": "contacts",
    }
    datasource.update(datasource_overrides)
    return {
        "datasources": {"mysql": datasource},
        "general": {},
    }


def make_mock_connection(fetchone_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result or {"VERSION()": "8.0.0"}
    cursor.fetchall.return_value = []
    cursor.rowcount = 1

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection, cursor


@pytest.fixture
def mock_domain_adapter():
    adapter = MagicMock()
    adapter.get_domain_config.return_value = {}
    return adapter


@pytest.mark.asyncio
async def test_create_connection_uses_charset_and_sql_mode(mock_domain_adapter):
    config = make_config(charset="utf8mb4", sql_mode="STRICT_TRANS_TABLES")
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    with patch(
        "mysql.connector.connect",
        return_value=connection,
    ) as mock_connect:
        result = await retriever.create_connection()

    assert result is connection
    _, kwargs = mock_connect.call_args
    assert kwargs["charset"] == "utf8mb4"
    assert kwargs["sql_mode"] == "STRICT_TRANS_TABLES"
    # Unlike the intent/ variant, the relational variant never passes autocommit/use_ssl.
    assert "autocommit" not in kwargs
    assert "use_ssl" not in kwargs


@pytest.mark.asyncio
async def test_execute_raw_query_uses_plain_cursor_not_dictionary(mock_domain_adapter):
    """Unlike the intent/ variant, the relational MySQL retriever does not request dictionary=True."""
    config = make_config()
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.fetchall.return_value = [(1, "Acme")]
    retriever._connection = connection

    await retriever._execute_raw_query("SELECT * FROM contacts")

    connection.cursor.assert_called_once_with()


@pytest.mark.asyncio
async def test_non_select_query_always_commits(mock_domain_adapter):
    """
    Unlike the intent/ variant (which only commits when autocommit is False),
    the relational variant commits unconditionally after a non-SELECT query.
    """
    config = make_config()
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    result = await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.commit.assert_called_once()
    assert result == [{"affected_rows": 1}]


@pytest.mark.asyncio
async def test_query_error_always_rolls_back(mock_domain_adapter):
    """
    Unlike the intent/ variant (which only rolls back when autocommit is False),
    the relational variant rolls back on any query error unconditionally.
    """
    config = make_config()
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.execute.side_effect = RuntimeError("boom")
    retriever._connection = connection

    with pytest.raises(RuntimeError):
        await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_calls_create_connection_when_datasource_has_none(mock_domain_adapter):
    """
    Confirms the lifecycle-audit finding: MySQLRetriever.initialize() is a
    production call site for create_connection() (relational/mysql_retriever.py:142),
    unlike the intent/ variant where create_connection() has zero production callers.

    Regression test for a bug found while building this baseline (fixed
    2026-11-15): `self.connection = await self.create_connection()` assigns to
    `connection`, which used to be a READ-ONLY property on AbstractSQLRetriever
    (base/sql_retriever.py, getter only, no setter). When the datasource had no
    connection to hand back yet (so `self.connection` was falsy, entering this
    branch), that assignment raised AttributeError instead of ever storing the
    newly created connection. A setter was added
    (base/sql_retriever.py, `@connection.setter`) that stores the value on
    `self._connection`. This test pins the now-fixed, working behavior.
    """
    config = make_config()

    mock_datasource = MagicMock()
    mock_datasource.is_initialized = True
    mock_datasource.get_connection.return_value = None  # datasource has no connection yet

    retriever = ConcreteMySQLRetriever(
        config=config, datasource=mock_datasource, domain_adapter=mock_domain_adapter
    )
    retriever._verify_database_structure = AsyncMock()

    connection, _cursor = make_mock_connection()
    with patch.object(
        MySQLRetriever, "create_connection", new=AsyncMock(return_value=connection)
    ) as mock_create:
        await retriever.initialize()

    mock_create.assert_awaited_once()
    assert retriever.connection is connection
    retriever._verify_database_structure.assert_awaited_once()


@pytest.mark.asyncio
async def test_initialize_does_not_recreate_existing_connection(mock_domain_adapter):
    """initialize() must not call create_connection() again if a connection is already set."""
    config = make_config()
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)
    retriever._verify_database_structure = AsyncMock()

    existing_connection, _cursor = make_mock_connection()
    retriever._connection = existing_connection

    with patch.object(
        MySQLRetriever, "create_connection", new=AsyncMock()
    ) as mock_create:
        await retriever.initialize()

    mock_create.assert_not_awaited()
    assert retriever.connection is existing_connection


@pytest.mark.asyncio
async def test_close_connection_calls_connector_close(mock_domain_adapter):
    config = make_config()
    retriever = ConcreteMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    await retriever._close_connection()

    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_execute_query_reconnects_through_datasource_not_create_connection(mock_domain_adapter):
    """
    Confirms the lifecycle-audit finding for the shared base class: when a
    'connection closed' error is raised, BaseSQLDatabaseRetriever.execute_query's
    reconnection path goes through the datasource registry
    (_datasource.close() -> initialize() -> get_connection()), never through
    the retriever's own create_connection().
    """
    config = make_config()

    mock_datasource = MagicMock()
    mock_datasource.is_initialized = True
    mock_datasource.close = AsyncMock()
    mock_datasource.initialize = AsyncMock()

    retriever = ConcreteMySQLRetriever(config=config, datasource=mock_datasource, domain_adapter=mock_domain_adapter)
    retriever._datasource_initialized = True

    good_connection, good_cursor = make_mock_connection()
    good_cursor.fetchall.return_value = [{"id": 1}]
    mock_datasource.get_connection.return_value = good_connection

    bad_connection, bad_cursor = make_mock_connection()
    bad_cursor.execute.side_effect = RuntimeError("MySQL connection not available (connection closed)")
    retriever._connection = bad_connection

    with patch.object(MySQLRetriever, "create_connection", new=AsyncMock()) as mock_create:
        results = await retriever.execute_query("SELECT * FROM contacts")

    mock_create.assert_not_awaited()
    mock_datasource.close.assert_awaited_once()
    mock_datasource.initialize.assert_awaited_once()
    assert retriever.connection is good_connection
    assert results == [{"id": 1}]
