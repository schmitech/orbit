"""
Tests for IntentAthenaRetriever._execute_raw_query's parameter normalization.

Athena has no local/offline server, so these tests mock the pyathena
connection/cursor and assert what SQL text and params actually get passed to
cursor.execute() -- verifying the normalization now delegates to the shared
helpers in retrievers/base/sql_param_binding.py (see
docs/roadmap/retrievers-implementations-cleanup.md, Phase 2) without changing
Athena's documented behavior (convert :name/? to %(name)s, escape literal '%'
in LIKE patterns).
"""

import os
import sys
from unittest.mock import MagicMock, Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.intent_athena_retriever import IntentAthenaRetriever


@pytest.fixture
def test_config():
    return {
        "datasources": {
            "athena": {
                "region_name": "us-east-1",
                "work_group": "primary",
            }
        },
        "adapter_config": {
            "store_name": "test_store",
        },
        "general": {},
    }


def _make_retriever(test_config, select_rows=None):
    # A mock domain_adapter skips IntentAdapter construction (which would
    # otherwise require real domain/template config files not needed here --
    # these tests only exercise _execute_raw_query's parameter normalization).
    retriever = IntentAthenaRetriever(config=test_config, domain_adapter=Mock())

    cursor = MagicMock()
    cursor.fetchall.return_value = select_rows or []
    cursor.description = []
    cursor.rowcount = 0

    connection = MagicMock()
    connection.cursor.return_value = cursor

    retriever._connection = connection
    retriever._is_connection_alive = lambda: True
    return retriever, cursor


@pytest.mark.asyncio
async def test_colon_params_converted_to_pyformat(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE id = :id", {"id": 42}
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE id = %(id)s"
    assert executed_params == {"id": 42}


@pytest.mark.asyncio
async def test_pyformat_params_passed_through(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE id = %(id)s", {"id": 42}
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE id = %(id)s"
    assert executed_params == {"id": 42}


@pytest.mark.asyncio
async def test_positional_params_converted_to_pyformat(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE id = ? AND name = ?", (42, "alice")
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE id = %(p0)s AND name = %(p1)s"
    assert executed_params == {"p0": 42, "p1": "alice"}


@pytest.mark.asyncio
async def test_literal_percent_in_like_pattern_is_escaped(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE name LIKE '%cloud%' AND id = :id", {"id": 1}
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE name LIKE '%%cloud%%' AND id = %(id)s"
    assert executed_params == {"id": 1}


@pytest.mark.asyncio
async def test_repeated_named_placeholder(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE a = :x OR b = :x", {"x": 7}
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE a = %(x)s OR b = %(x)s"
    assert executed_params == {"x": 7}


@pytest.mark.asyncio
async def test_no_params_executes_without_binding(test_config):
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query("SELECT * FROM t")

    cursor.execute.assert_called_once_with("SELECT * FROM t")


@pytest.mark.asyncio
async def test_literal_question_mark_is_not_converted(test_config):
    """
    A '?' inside a string literal must not be treated as a real placeholder
    just because it's textually present -- conversion is capped at the
    number of positional values actually supplied, matching the one real
    placeholder here (not the two '?' characters in the query text).
    """
    retriever, cursor = _make_retriever(test_config)

    await retriever._execute_raw_query(
        "SELECT * FROM t WHERE id = ? AND note = '?'", (42,)
    )

    executed_sql, executed_params = cursor.execute.call_args[0]
    assert executed_sql == "SELECT * FROM t WHERE id = %(p0)s AND note = '?'"
    assert executed_params == {"p0": 42}
