"""
Unit tests for SQLQueryExecutionMixin.is_select_query()
(server/retrievers/base/base_sql_database.py), extracted per
docs/roadmap/sql-connection-dedup-and-firecrawl-reconciliation.md Item 1,
step 6, to replace the identical SELECT/WITH dispatch check that was
duplicated across all 8 SQL retrievers (5 intent/, 3 relational/).
"""

import pytest
from retrievers.base.base_sql_database import SQLQueryExecutionMixin

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("query", [
    "SELECT * FROM contacts",
    "select * from contacts",
    "  SELECT 1",
    "WITH cte AS (SELECT 1) SELECT * FROM cte",
    "with cte as (select 1) select * from cte",
    "\n\tSELECT name FROM contacts",
])
def test_select_and_with_queries_are_read_queries(query):
    assert SQLQueryExecutionMixin.is_select_query(query) is True


@pytest.mark.parametrize("query", [
    "INSERT INTO contacts (name) VALUES ('x')",
    "UPDATE contacts SET name = 'x' WHERE id = 1",
    "DELETE FROM contacts WHERE id = 1",
    "CREATE TABLE contacts (id INTEGER)",
    "",
    "   ",
])
def test_non_select_queries_are_not_read_queries(query):
    assert SQLQueryExecutionMixin.is_select_query(query) is False
