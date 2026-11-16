"""
Regression-baseline tests for PostgreSQLRetriever's (relational/) *current*
connection lifecycle behavior, pinned after extracting the shared
PostgreSQLConnectionMixin (base/postgresql_connection_mixin.py).

Unlike the intent/ variant, the relational variant never pools at the
retriever level and never forces autocommit -- these tests confirm the
extraction preserved that (plan Item 1, Postgres pooling decision: the
mixin is pooling-agnostic, each variant decides for itself).

These do not test against a live PostgreSQL server; psycopg is mocked so the
suite can run without a database.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.relational.postgresql_retriever import PostgreSQLRetriever


class ConcretePostgreSQLRetriever(PostgreSQLRetriever):
    """
    PostgreSQLRetriever leaves set_collection() abstract (inherited from
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
        "port": 5432,
        "database": "testdb",
        "username": "postgres",
        "password": "secret",
        "collection": "contacts",
    }
    datasource.update(datasource_overrides)
    return {
        "datasources": {"postgresql": datasource},
        "general": {},
    }


def make_mock_connection(fetchone_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result or {"version": "PostgreSQL 16.0"}
    cursor.fetchall.return_value = []
    cursor.rowcount = 1

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection, cursor


class AutocommitTrackingConnection:
    """
    A connection test double that records whether `.autocommit` was ever
    explicitly assigned, unlike a MagicMock (which silently accepts any
    attribute write and so can't distinguish "never touched" from
    "set to a value that happens to look unchanged").
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.close = MagicMock()
        self.autocommit_was_set = False
        self._autocommit = None

    def cursor(self):
        return self._cursor

    @property
    def autocommit(self):
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value):
        self.autocommit_was_set = True
        self._autocommit = value


@pytest.fixture
def mock_domain_adapter():
    adapter = MagicMock()
    adapter.get_domain_config.return_value = {}
    return adapter


@pytest.mark.asyncio
async def test_create_connection_never_pools_and_never_sets_autocommit(mock_domain_adapter):
    """
    Unlike the intent/ variant, the relational variant must never create a
    connection pool and must never assign to connection.autocommit at all
    (not even to its current value) -- verified with a tracking connection
    double, not just by checking psycopg.connect()'s call kwargs, since a
    later `connection.autocommit = ...` statement wouldn't show up there.
    """
    config = make_config(sslmode="require")
    retriever = ConcretePostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    _, cursor = make_mock_connection()
    connection = AutocommitTrackingConnection(cursor)
    with patch("psycopg.connect", return_value=connection) as mock_connect, \
         patch("psycopg_pool.ConnectionPool") as mock_pool_cls:
        result = await retriever.create_connection()

    assert result is connection
    _, kwargs = mock_connect.call_args
    assert kwargs["sslmode"] == "require"
    mock_pool_cls.assert_not_called()
    assert "autocommit" not in kwargs
    assert connection.autocommit_was_set is False


@pytest.mark.asyncio
async def test_create_connection_works_without_psycopg_pool_installed(mock_domain_adapter):
    """
    Regression test for a dependency-entanglement bug found in review: the
    mixin's original combined `import psycopg; import psycopg_pool` block
    set BOTH to None if either was missing, so the unpooled relational path
    failed even with psycopg[binary] installed and only psycopg_pool absent.
    psycopg and psycopg_pool are now imported in separate try/except blocks
    so psycopg_pool's absence can't break the unpooled path.
    """
    config = make_config()
    retriever = ConcretePostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    with patch("retrievers.base.postgresql_connection_mixin.psycopg_pool", None), \
         patch("psycopg.connect", return_value=connection):
        result = await retriever.create_connection()

    assert result is connection


@pytest.mark.asyncio
async def test_non_select_query_always_commits(mock_domain_adapter):
    config = make_config()
    retriever = ConcretePostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    result = await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.commit.assert_called_once()
    assert result == [{"affected_rows": 1}]


@pytest.mark.asyncio
async def test_query_error_rolls_back(mock_domain_adapter):
    config = make_config()
    retriever = ConcretePostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, cursor = make_mock_connection()
    cursor.execute.side_effect = RuntimeError("boom")
    retriever._connection = connection

    with pytest.raises(RuntimeError):
        await retriever._execute_raw_query("UPDATE contacts SET name = 'x' WHERE id = 1")

    connection.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_close_connection_closes_directly_never_pool_aware(mock_domain_adapter):
    """The relational variant's close must never reference a connection pool."""
    config = make_config()
    retriever = ConcretePostgreSQLRetriever(config=config, domain_adapter=mock_domain_adapter)

    connection, _cursor = make_mock_connection()
    retriever._connection = connection

    await retriever._close_connection()

    connection.close.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_calls_create_connection_when_datasource_has_none(mock_domain_adapter):
    """
    Confirms the lifecycle-audit finding: PostgreSQLRetriever.initialize() is
    a production call site for create_connection() (relational/postgresql_retriever.py:127),
    same pattern as the MySQL relational variant. Also confirms the
    read-only-`connection`-property bug fix (base/sql_retriever.py
    `@connection.setter`) applies here too.
    """
    config = make_config()

    mock_datasource = MagicMock()
    mock_datasource.is_initialized = True
    mock_datasource.get_connection.return_value = None  # datasource has no connection yet

    retriever = ConcretePostgreSQLRetriever(
        config=config, datasource=mock_datasource, domain_adapter=mock_domain_adapter
    )
    retriever._verify_database_structure = AsyncMock()

    connection, _cursor = make_mock_connection()
    with patch.object(
        PostgreSQLRetriever, "create_connection", new=AsyncMock(return_value=connection)
    ) as mock_create:
        await retriever.initialize()

    mock_create.assert_awaited_once()
    assert retriever.connection is connection
    retriever._verify_database_structure.assert_awaited_once()
