"""
Regression-baseline tests for IntentMySQLRetriever's *current* connection
lifecycle behavior (reconnection, transaction commit/rollback, shutdown).

These exist to establish a behavior baseline before any connection-mixin
extraction is attempted, per docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md
Item 1, step 4. They do not test against a live MySQL server; mysql.connector
is mocked so the suite can run without a database.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.intent_mysql_retriever import IntentMySQLRetriever


@pytest.fixture
def mock_domain_adapter():
    adapter = MagicMock()
    adapter.get_domain_config.return_value = {
        "domain_name": "Test",
        "description": "Test domain",
        "entities": {"contacts": {"table_name": "contacts"}},
    }
    return adapter


def make_config(**datasource_overrides):
    datasource = {
        "host": "localhost",
        "port": 3306,
        "database": "testdb",
        "username": "root",
        "password": "secret",
    }
    datasource.update(datasource_overrides)
    return {
        "datasources": {"mysql": datasource},
        "general": {},
        "adapter_config": {"store_name": "test_store"},
    }


def make_mock_connection(fetchone_result=None):
    """Build a mock mysql.connector connection with a mock cursor."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result or {"version": "8.0.0"}
    cursor.fetchall.return_value = []
    cursor.rowcount = 1

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.closed = False
    return connection, cursor


@pytest.mark.asyncio
async def test_create_connection_passes_autocommit_and_ssl_config(mock_domain_adapter):
    """create_connection() must forward autocommit and use_ssl exactly as configured."""
    config = make_config(autocommit=False, ssl_disabled=False)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    with patch(
        "mysql.connector.connect",
        return_value=connection,
    ) as mock_connect:
        result = await retriever.create_connection()

    assert result is connection
    _, kwargs = mock_connect.call_args
    assert kwargs["autocommit"] is False
    assert kwargs["use_ssl"] is True


@pytest.mark.asyncio
async def test_create_connection_ssl_disabled_omits_use_ssl(mock_domain_adapter):
    """When ssl_disabled is True, use_ssl must not be passed to mysql.connector.connect."""
    config = make_config(ssl_disabled=True)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    with patch(
        "mysql.connector.connect",
        return_value=connection,
    ) as mock_connect:
        await retriever.create_connection()

    _, kwargs = mock_connect.call_args
    assert "use_ssl" not in kwargs


@pytest.mark.asyncio
async def test_execute_raw_query_uses_dictionary_cursor(mock_domain_adapter):
    """_execute_raw_query must request a dictionary=True cursor (unlike the relational variant)."""
    config = make_config()
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.fetchall.return_value = [{"id": 1, "name": "Acme"}]
    retriever._connection = connection

    results = await retriever._execute_raw_query("SELECT * FROM contacts")

    connection.cursor.assert_called_once_with(dictionary=True)
    assert results == [{"id": 1, "name": "Acme"}]


@pytest.mark.asyncio
async def test_non_autocommit_commits_on_success(mock_domain_adapter):
    """With autocommit disabled, a non-SELECT query must be followed by an explicit commit."""
    config = make_config(autocommit=False)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    result = await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    assert result == [{"affected_rows": 1}]


@pytest.mark.asyncio
async def test_autocommit_true_never_commits_explicitly(mock_domain_adapter):
    """With autocommit enabled (the default), execute_raw_query must not call commit() itself."""
    config = make_config(autocommit=True)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.commit.assert_not_called()


@pytest.mark.asyncio
async def test_non_autocommit_rolls_back_on_query_error(mock_domain_adapter):
    """With autocommit disabled, a failing query must trigger rollback() before the error propagates."""
    config = make_config(autocommit=False)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.execute.side_effect = RuntimeError("boom")
    retriever._connection = connection

    with pytest.raises(RuntimeError):
        await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_autocommit_true_does_not_rollback_on_query_error(mock_domain_adapter):
    """With autocommit enabled, a failing query must NOT call rollback() (current behavior, not a recommendation)."""
    config = make_config(autocommit=True)
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.execute.side_effect = RuntimeError("boom")
    retriever._connection = connection

    with pytest.raises(RuntimeError):
        await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_close_connection_calls_connector_close(mock_domain_adapter):
    config = make_config()
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    await retriever._close_connection()

    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_connection_is_noop_when_no_connection(mock_domain_adapter):
    """_close_connection() must not raise when there is no connection to close."""
    config = make_config()
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)
    retriever._connection = None

    await retriever._close_connection()  # must not raise


@pytest.mark.asyncio
async def test_intent_mysql_retriever_has_no_liveness_check(mock_domain_adapter):
    """
    Confirms the lifecycle-audit finding: unlike Postgres/SQLite/DuckDB/Athena,
    IntentMySQLRetriever defines no _is_connection_alive() method.
    """
    config = make_config()
    retriever = IntentMySQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    assert not hasattr(retriever, "_is_connection_alive")
