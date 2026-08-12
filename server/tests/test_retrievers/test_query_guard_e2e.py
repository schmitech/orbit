"""
End-to-end regression test: a real IntentDuckDBRetriever must not return more
rows than query_guard_max_rows, even when the executed template's LIMIT count
is bound to a placeholder (e.g. `LIMIT :limit`, exactly the shape used by
examples/intent-templates/duckdb-intent-template/examples/analytics/) rather
than a literal.

enforce_row_cap() alone can't close this gap — a bound LIMIT's actual value
isn't in the rendered SQL text at all, it's in the resolved parameters dict,
which is why clamp_bound_limit_parameter() exists. This test exercises the
real _execute_template() path against a real DuckDB database to prove the row
count the caller actually gets back is capped, not just that the SQL text or
the parameter dict looks right in isolation.
"""

import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

duckdb = pytest.importorskip("duckdb", reason="duckdb dependency is required for this test")

from retrievers.base.intent_sql_base import IntentSQLRetriever
from retrievers.implementations.intent.intent_duckdb_retriever import IntentDuckDBRetriever

ROW_COUNT = 5000


@pytest.fixture
def test_config(tmp_path):
    db_path = tmp_path / "test.duckdb"
    return {
        "datasources": {
            "duckdb": {
                "database": str(db_path),
                "read_only": False,
                "access_mode": "automatic",
                "threads": None,
            }
        },
        "general": {},
        "adapter_config": {
            "store_name": "chroma",
            "query_guard_max_rows": 50,
        },
    }


@pytest.fixture
async def test_database(tmp_path):
    db_path = tmp_path / "test.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE sales (id INTEGER PRIMARY KEY, amount DOUBLE)")
        conn.executemany(
            "INSERT INTO sales (id, amount) VALUES (?, ?)",
            [(i, float(i)) for i in range(1, ROW_COUNT + 1)],
        )
        yield str(db_path)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_bound_named_limit_above_cap_is_capped_at_execution(test_config, test_database):
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()

    template = {
        "id": "find_all_sales_bound_limit",
        "sql": "SELECT id, amount FROM sales ORDER BY id LIMIT :limit",
        "parameters": [{"name": "limit", "type": "integer", "required": False, "default": 100}],
    }

    try:
        results, error = await retriever._execute_template(template, {"limit": ROW_COUNT})
        assert error is None, error
        assert len(results) <= test_config["adapter_config"]["query_guard_max_rows"]
        assert len(results) == 50
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_bound_limit_within_cap_is_unaffected(test_config, test_database):
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()

    template = {
        "id": "find_some_sales_bound_limit",
        "sql": "SELECT id, amount FROM sales ORDER BY id LIMIT :limit",
        "parameters": [{"name": "limit", "type": "integer", "required": False, "default": 100}],
    }

    try:
        results, error = await retriever._execute_template(template, {"limit": 10})
        assert error is None, error
        assert len(results) == 10
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_underperforming_products_shape_multiple_bound_params_and_limit(test_config, test_database):
    """The exact template shape from the original bug report: several named
    bound parameters, one of which (`:limit`) governs row count."""
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()

    template = {
        "id": "underperforming_products",
        "sql": (
            "SELECT id, amount FROM sales "
            "WHERE amount > :revenue_threshold "
            "ORDER BY id LIMIT :limit"
        ),
        "parameters": [
            {"name": "revenue_threshold", "type": "decimal", "required": False, "default": 0},
            {"name": "limit", "type": "integer", "required": False, "default": 20},
        ],
    }

    try:
        results, error = await retriever._execute_template(
            template, {"revenue_threshold": 0, "limit": ROW_COUNT}
        )
        assert error is None, error
        assert len(results) <= test_config["adapter_config"]["query_guard_max_rows"]
        assert len(results) == 50
    finally:
        await retriever.close()


class _MockMySQLLimitOffsetRetriever(IntentSQLRetriever):
    """
    A minimal IntentSQLRetriever standing in for IntentMySQLRetriever — no
    real MySQL server is available in this environment, but `execute_query`
    is the one method a live MySQL driver would implement, so replacing only
    that keeps `_execute_template` (the code under test, including the guard
    and the positional-LIMIT clamp) running for real.
    """

    def __init__(self, config):
        super().__init__(config=config, domain_adapter=Mock())
        self.executed_sql = None
        self.executed_params = None

    def _get_datasource_name(self) -> str:
        return "mysql"

    def get_test_query(self) -> str:
        return "SELECT 1 as test"

    async def _execute_raw_query(self, query, params=None):
        return await self.execute_query(query, params)

    async def execute_query(self, sql, params=None):
        self.executed_sql = sql
        self.executed_params = params
        offset, count = params
        return [{"id": i} for i in range(offset, offset + count)]


@pytest.mark.asyncio
async def test_mysql_limit_offset_comma_form_oversized_count_is_capped():
    """
    Regression: MySQL's `LIMIT offset, count` with both slots bound
    positionally (`LIMIT ?, ?`) — the offset placeholder comes first, the
    count placeholder second. A naive "clamp the first `?`" implementation
    would clamp the offset and leave the actual row count (99999) uncapped.
    """
    config = {
        "datasources": {"mysql": {}},
        "general": {},
        "adapter_config": {"store_name": "chroma", "query_guard_max_rows": 1000},
    }
    retriever = _MockMySQLLimitOffsetRetriever(config)

    template = {
        "id": "find_sales_paginated",
        "sql": "SELECT id FROM sales LIMIT ?, ?",
        "parameters": [
            {"name": "offset", "type": "integer", "required": False, "default": 0},
            {"name": "count", "type": "integer", "required": False, "default": 20},
        ],
    }

    results, error = await retriever._execute_template(template, {"offset": 20, "count": 99999})

    assert error is None, error
    assert retriever.executed_params == (20, 1000), retriever.executed_params
    assert len(results) == 1000


@pytest.mark.asyncio
async def test_missing_bound_limit_falls_back_to_oversized_template_default_and_is_still_capped(
    test_config, test_database
):
    """
    Regression: the query guard's bound-LIMIT clamp used to run on
    formatted_parameters *before* template defaults were resolved into it —
    that resolution only happened afterward, per placeholder style, while
    binding. So a caller passing {} (omitting `limit` entirely) meant the
    clamp saw no value at all and did nothing; the oversized template
    default (99999) was then inserted unclamped when the query actually
    bound. Template defaults must be resolved before the guard ever sees
    formatted_parameters, not after.
    """
    retriever = IntentDuckDBRetriever(config=test_config)
    await retriever.create_connection()

    template = {
        "id": "find_all_sales_default_limit",
        "sql": "SELECT id, amount FROM sales ORDER BY id LIMIT :limit",
        "parameters": [{"name": "limit", "type": "integer", "required": False, "default": ROW_COUNT}],
    }

    try:
        # Caller supplies no parameters at all — only the template's own
        # (oversized) default is available.
        results, error = await retriever._execute_template(template, {})
        assert error is None, error
        assert len(results) <= test_config["adapter_config"]["query_guard_max_rows"]
        assert len(results) == 50
    finally:
        await retriever.close()
