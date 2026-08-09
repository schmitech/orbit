"""Unit tests for the SQL query safety guard (server/retrievers/base/query_guard.py)."""

import pytest

from retrievers.base.query_guard import (
    QueryGuardError,
    assert_read_only,
    assert_single_statement,
    enforce_row_cap,
    resolve_dialect,
)


class TestResolveDialect:
    def test_known_datasource_names_map_to_expected_dialects(self):
        # These are the exact strings each retriever's _get_datasource_name()
        # returns (intent_postgresql_retriever.py, intent_mysql_retriever.py, etc.)
        assert resolve_dialect("postgres") == "postgres"
        assert resolve_dialect("sqlite") == "sqlite"
        assert resolve_dialect("duckdb") == "duckdb"
        assert resolve_dialect("mysql") == "mysql"
        assert resolve_dialect("athena") == "athena"
        assert resolve_dialect("mariadb") == "mysql"
        assert resolve_dialect("mssql") == "tsql"

    def test_case_insensitive(self):
        assert resolve_dialect("SQLite") == "sqlite"

    def test_unknown_or_missing_datasource_returns_none(self):
        assert resolve_dialect("some_custom_datasource") is None
        assert resolve_dialect(None) is None
        assert resolve_dialect("") is None

    def test_not_the_template_vector_store_name(self):
        # store_name (adapter config) identifies where template embeddings
        # live, e.g. "chroma" — it is not a SQL dialect and must not resolve.
        assert resolve_dialect("chroma") is None


class TestAssertSingleStatement:
    def test_single_select_passes(self):
        assert_single_statement("SELECT 1", dialect="sqlite")

    def test_stacked_statements_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_single_statement("SELECT 1; DROP TABLE x", dialect="sqlite")

    def test_trailing_semicolon_is_still_single(self):
        assert_single_statement("SELECT 1;", dialect="sqlite")

    def test_unparseable_sql_raises(self):
        with pytest.raises(QueryGuardError):
            assert_single_statement("SELECT FROM WHERE ===", dialect="sqlite")


class TestAssertReadOnly:
    def test_select_passes(self):
        assert_read_only("SELECT * FROM employees WHERE dept = ?", dialect="sqlite")

    def test_delete_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("DELETE FROM employees", dialect="sqlite")

    def test_update_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("UPDATE employees SET salary = 0", dialect="sqlite")

    def test_insert_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("INSERT INTO employees (name) VALUES ('x')", dialect="sqlite")

    def test_drop_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("DROP TABLE employees", dialect="sqlite")

    def test_write_inside_cte_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only(
                "WITH t AS (DELETE FROM employees RETURNING *) SELECT * FROM t",
                dialect="postgres",
            )

    def test_truncate_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("TRUNCATE TABLE employees", dialect="mysql")

    def test_copy_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("COPY employees TO STDOUT", dialect="postgres")

    def test_execute_rejected(self):
        with pytest.raises(QueryGuardError):
            assert_read_only("EXEC some_proc", dialect="tsql")

    def test_unmodeled_syntax_falling_back_to_command_rejected(self):
        # sqlglot parses statements it doesn't model explicitly as a generic
        # Command node rather than raising — those must not slip through as
        # "read-only" just because no specific write node matched.
        with pytest.raises(QueryGuardError):
            assert_read_only("LOCK TABLES employees WRITE", dialect="mysql")


class TestEnforceRowCap:
    def test_injects_limit_when_absent(self):
        result = enforce_row_cap("SELECT * FROM employees", cap=1000, dialect="sqlite")
        assert "LIMIT 1000" in result.upper()

    def test_clamps_limit_larger_than_cap(self):
        result = enforce_row_cap("SELECT * FROM employees LIMIT 99999", cap=1000, dialect="sqlite")
        assert "LIMIT 1000" in result.upper()
        assert "99999" not in result

    def test_leaves_limit_smaller_than_cap_alone(self):
        result = enforce_row_cap("SELECT * FROM employees LIMIT 10", cap=1000, dialect="sqlite")
        assert "LIMIT 10" in result.upper()

    def test_leaves_placeholder_limit_alone(self):
        result = enforce_row_cap("SELECT * FROM employees LIMIT ?", cap=1000, dialect="sqlite")
        assert "LIMIT ?" in result.upper()

    def test_unparseable_sql_returns_unchanged(self):
        bad_sql = "SELECT FROM WHERE ==="
        assert enforce_row_cap(bad_sql, cap=1000, dialect="sqlite") == bad_sql

    @pytest.mark.parametrize("dialect", ["postgres", "mysql", "tsql", "sqlite", "duckdb", "oracle"])
    def test_each_dialect_parses(self, dialect):
        result = enforce_row_cap("SELECT * FROM employees", cap=1000, dialect=dialect)
        assert "employees" in result.lower()
