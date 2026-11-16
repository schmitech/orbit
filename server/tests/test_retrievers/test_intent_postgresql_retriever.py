"""
Regression-baseline tests for IntentPostgreSQLRetriever's *current* connection
lifecycle behavior (pooled/unpooled connection creation, liveness check,
transaction commit/rollback, shutdown), pinned after extracting the shared
PostgreSQLConnectionMixin (base/postgresql_connection_mixin.py).

Per docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md Item 1:
the mixin is pooling-agnostic by explicit decision -- intent/ keeps choosing
to pool (or not) via use_connection_pool, exactly as before extraction.

These do not test against a live PostgreSQL server; psycopg/psycopg_pool are
mocked so the suite can run without a database.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.intent_postgresql_retriever import (
    IntentPostgreSQLRetriever,
    _OperationalError,
)


@pytest.fixture
def mock_domain_adapter():
    adapter = MagicMock()
    adapter.get_domain_config.return_value = {}
    return adapter


def make_config(**datasource_overrides):
    datasource = {
        "host": "localhost",
        "port": 5432,
        "database": "testdb",
        "username": "postgres",
        "password": "secret",
        "use_connection_pool": False,
    }
    datasource.update(datasource_overrides)
    return {
        "datasources": {"postgres": datasource},
        "general": {},
        "adapter_config": {"store_name": "test_store"},
    }


def make_mock_connection(fetchone_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result or {"version": "PostgreSQL 16.0"}
    cursor.fetchall.return_value = []
    cursor.rowcount = 1

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.closed = False
    return connection, cursor


@pytest.mark.asyncio
async def test_create_connection_unpooled_forces_autocommit_false(mock_domain_adapter):
    """Unpooled path must explicitly set connection.autocommit = False after connecting."""
    config = make_config(use_connection_pool=False)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    with patch(
        "psycopg.connect",
        return_value=connection,
    ) as mock_connect:
        result = await retriever.create_connection()

    assert result is connection
    _, kwargs = mock_connect.call_args
    assert kwargs["sslmode"] == "prefer"
    assert connection.autocommit is False


@pytest.mark.asyncio
async def test_create_connection_pooled_creates_pool_and_gets_connection(mock_domain_adapter):
    """Pooled path must create a psycopg_pool.ConnectionPool and get a connection from it."""
    config = make_config(use_connection_pool=True, pool_size=5)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    mock_pool = MagicMock()
    mock_pool.getconn.return_value = connection

    with patch("psycopg_pool.ConnectionPool", return_value=mock_pool) as mock_pool_cls:
        result = await retriever.create_connection()

    assert result is connection
    assert retriever.connection_pool is mock_pool
    mock_pool.getconn.assert_called_once()
    _, kwargs = mock_pool_cls.call_args
    assert kwargs["max_size"] == 5


@pytest.mark.asyncio
async def test_create_connection_pooled_raises_clear_error_without_psycopg_pool(mock_domain_adapter):
    """
    When use_pool=True but psycopg_pool isn't installed, create_connection()
    must raise a clear ImportError naming psycopg_pool specifically -- not
    silently fail elsewhere, and not be masked by psycopg itself appearing
    unavailable (the dependency-entanglement bug fixed in
    postgresql_connection_mixin.py's now-separate import blocks).
    """
    config = make_config(use_connection_pool=True)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    with patch("retrievers.base.postgresql_connection_mixin.psycopg_pool", None), \
         pytest.raises(ImportError, match="psycopg_pool"):
        await retriever.create_connection()


@pytest.mark.asyncio
async def test_create_connection_pooled_reuses_existing_pool(mock_domain_adapter):
    """
    If a pool already exists, create_connection() must not create a second
    one, and must get a connection from the existing pool.

    This pins an INTENTIONAL BEHAVIOR CHANGE from pre-extraction, not a
    preserved baseline: the original intent/ code only took the pooled path
    on the first call (`if self.use_connection_pool and not self.connection_pool`);
    once a pool existed, later calls fell through to the unpooled `else`
    branch and opened a brand-new standalone connection instead of reusing
    the pool. That looked like an unintentional bug (see
    postgresql_connection_mixin.py's `_create_postgresql_connection`
    docstring), so this extraction fixes it rather than preserving it.
    """
    config = make_config(use_connection_pool=True)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    existing_connection, _cursor = make_mock_connection()
    existing_pool = MagicMock()
    existing_pool.getconn.return_value = existing_connection
    retriever.connection_pool = existing_pool

    with patch("psycopg_pool.ConnectionPool") as mock_pool_cls:
        result = await retriever.create_connection()

    mock_pool_cls.assert_not_called()
    existing_pool.getconn.assert_called_once()
    assert result is existing_connection


@pytest.mark.asyncio
async def test_is_connection_alive_true_for_open_connection(mock_domain_adapter):
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    assert retriever._is_connection_alive() is True


@pytest.mark.asyncio
async def test_is_connection_alive_false_when_closed(mock_domain_adapter):
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    connection.closed = True
    retriever._connection = connection

    assert retriever._is_connection_alive() is False


@pytest.mark.asyncio
async def test_is_connection_alive_false_when_none(mock_domain_adapter):
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)
    retriever._connection = None

    assert retriever._is_connection_alive() is False


@pytest.mark.asyncio
async def test_execute_raw_query_raises_when_connection_not_alive(mock_domain_adapter):
    """_execute_raw_query must check liveness first and raise before touching the cursor."""
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    connection.closed = True
    retriever._connection = connection

    with pytest.raises(_OperationalError):
        await retriever._execute_raw_query("SELECT 1")

    cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_non_select_query_commits(mock_domain_adapter):
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    result = await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.commit.assert_called_once()
    assert result == [{"affected_rows": 1}]


@pytest.mark.asyncio
async def test_query_error_rolls_back_when_connection_still_open(mock_domain_adapter):
    config = make_config()
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()

    def execute_side_effect(query, *args, **kwargs):
        if query == "SELECT 1":
            return  # liveness check must still pass
        raise RuntimeError("boom")

    cursor.execute.side_effect = execute_side_effect
    retriever._connection = connection

    with pytest.raises(RuntimeError):
        await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_close_connection_unpooled_closes_directly(mock_domain_adapter):
    config = make_config(use_connection_pool=False)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    await retriever._close_connection()

    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_connection_pooled_returns_to_pool_and_closes_pool(mock_domain_adapter):
    config = make_config(use_connection_pool=True)
    retriever = IntentPostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    mock_pool = MagicMock()
    retriever._connection = connection
    retriever.connection_pool = mock_pool

    await retriever._close_connection()

    mock_pool.putconn.assert_called_once_with(connection)
    connection.close.assert_not_called()
    mock_pool.close.assert_called_once()
    assert retriever.connection_pool is None
