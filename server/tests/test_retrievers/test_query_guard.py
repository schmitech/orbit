"""Unit tests for the SQL query safety guard (server/retrievers/base/query_guard.py)."""

import math
from decimal import Decimal

import pytest
import sqlglot
from sqlglot import exp

from retrievers.base.query_guard import (
    QueryGuardError,
    assert_read_only,
    assert_single_statement,
    clamp_bound_limit_parameter,
    enforce_row_cap,
    find_outer_limit_bind_name,
    find_outer_limit_positional_index,
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

    def test_injected_limit_not_commented_out_by_trailing_line_comment(self):
        # Regression: a query ending in a "--" line comment has no trailing
        # newline of its own. Appending " LIMIT {cap}" on the same line would
        # make the injected clause part of the comment — a line comment
        # extends to end-of-line, so the query would execute genuinely
        # unbounded despite the guard believing it capped it.
        result = enforce_row_cap("SELECT * FROM employees -- audit", cap=1000, dialect="sqlite")
        lines = result.split("\n")
        assert any(line.strip() == "LIMIT 1000" for line in lines), result
        # Confirm it's not just present in the text but actually parses as a
        # real LIMIT clause, not part of the comment.
        parsed = sqlglot.parse_one(result, read="sqlite")
        assert int(parsed.args["limit"].expression.this) == 1000

    def test_injected_oracle_fetch_first_not_commented_out(self):
        result = enforce_row_cap("SELECT * FROM employees -- audit", cap=1000, dialect="oracle")
        lines = result.split("\n")
        assert any(line.strip() == "FETCH FIRST 1000 ROWS ONLY" for line in lines), result
        parsed = sqlglot.parse_one(result, read="oracle")
        assert int(parsed.args["limit"].args["count"].this) == 1000

    def test_terminator_before_trailing_comment_stripped_before_injecting(self):
        # Regression: "SELECT ...; -- audit" is a valid single statement —
        # the ";" terminates it and the comment trails after. Naively
        # checking only whether the rstripped text ends in ";" misses this
        # (the comment, not the ";", is the last character), so the
        # semicolon stayed in place and the injected clause became a
        # second, invalid statement rather than part of the first query.
        result = enforce_row_cap("SELECT * FROM sales; -- audit", cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM sales\nLIMIT 1000"
        statements = [s for s in sqlglot.parse(result, read="sqlite") if s is not None]
        assert len(statements) == 1, statements

    def test_terminator_before_trailing_comment_stripped_for_oracle(self):
        result = enforce_row_cap("SELECT * FROM sales; -- audit", cap=1000, dialect="oracle")
        assert result == "SELECT * FROM sales\nFETCH FIRST 1000 ROWS ONLY"
        statements = [s for s in sqlglot.parse(result, read="oracle") if s is not None]
        assert len(statements) == 1, statements

    def test_terminator_before_trailing_comment_does_not_break_clamping_an_existing_limit(self):
        # The same "; -- comment" tail previously made enforce_row_cap's own
        # initial parse produce a wrapper type instead of a plain Select,
        # failing the isinstance check and returning the query completely
        # unmodified — silently skipping the clamp of an already-oversized
        # literal LIMIT, not just the injection path.
        result = enforce_row_cap("SELECT * FROM sales LIMIT 99999; -- audit", cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM sales LIMIT 1000; -- audit"

    def test_oracle_injects_fetch_first_not_limit(self):
        # Regression: Oracle has no LIMIT keyword at all — appending "LIMIT
        # {cap}" (the default for every dialect except tsql) produces invalid
        # SQL for Oracle. Oracle's own ANSI row-limiting syntax is
        # "FETCH FIRST n ROWS ONLY", which _find_outer_row_count_token_indices
        # already recognizes for clamping an *existing* clause — this is the
        # missing-clause injection path using the same syntax.
        result = enforce_row_cap("SELECT * FROM employees", cap=1000, dialect="oracle")
        assert result == "SELECT * FROM employees\nFETCH FIRST 1000 ROWS ONLY"
        assert "LIMIT" not in result.upper()

    def test_oracle_injection_strips_trailing_semicolon(self):
        result = enforce_row_cap("SELECT * FROM employees;", cap=1000, dialect="oracle")
        assert result == "SELECT * FROM employees\nFETCH FIRST 1000 ROWS ONLY"

    def test_oracle_union_gets_a_single_fetch_first_covering_both_arms(self):
        # Unlike T-SQL's TOP, Oracle's FETCH FIRST correctly attaches to the
        # outer Union node (not just one arm), so no special-case rejection
        # is needed here the way it is for uncapped T-SQL unions.
        result = enforce_row_cap("SELECT * FROM a UNION ALL SELECT * FROM b", cap=1000, dialect="oracle")
        assert result == "SELECT * FROM a UNION ALL SELECT * FROM b\nFETCH FIRST 1000 ROWS ONLY"

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

    def test_computed_limit_expression_rejected(self):
        # Regression: a non-literal, non-placeholder row-count expression
        # (LIMIT 1 + 99999) previously hit the same except branch as a bound
        # placeholder and was returned unchanged — neither clamped as a
        # literal nor eligible for clamp_bound_limit_parameter (which only
        # recognizes exp.Placeholder), so it executed uncapped. There's no
        # value here to safely compare to the cap without evaluating
        # arbitrary SQL, so it must be rejected outright.
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT * FROM sales LIMIT 1 + 99999", cap=1000, dialect="postgres")

    def test_computed_top_expression_rejected(self):
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT TOP (50000 * 2) * FROM sales", cap=1000, dialect="tsql")

    def test_negative_literal_limit_rejected_not_treated_as_within_cap(self):
        # Regression: SQLite treats LIMIT -1 as "no limit at all" — the
        # opposite of what "-1 <= cap" would suggest if compared naively.
        # sqlglot represents a negative literal as Neg(Literal(1)), which
        # this rejects via the computed-expression path rather than ever
        # reaching a numeric comparison that could call it "safe".
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT * FROM sales LIMIT -1", cap=1000, dialect="sqlite")

    def test_genuine_placeholder_still_untouched_after_computed_expression_fix(self):
        # Make sure distinguishing "computed expression" from "placeholder"
        # didn't regress the placeholder case itself.
        result = enforce_row_cap("SELECT * FROM sales LIMIT ?", cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM sales LIMIT ?"

    def test_unparseable_sql_returns_unchanged(self):
        bad_sql = "SELECT FROM WHERE ==="
        assert enforce_row_cap(bad_sql, cap=1000, dialect="sqlite") == bad_sql

    @pytest.mark.parametrize("dialect", ["postgres", "mysql", "tsql", "sqlite", "duckdb", "oracle"])
    def test_each_dialect_parses(self, dialect):
        result = enforce_row_cap("SELECT * FROM employees", cap=1000, dialect=dialect)
        assert "employees" in result.lower()

    def test_duckdb_named_placeholders_not_rewritten_to_dollar_syntax(self):
        # Regression: sqlglot's DuckDB dialect parses ":name" but *serializes*
        # it back out as "$name" — re-rendering the whole AST here would
        # silently corrupt every other placeholder in the query, not just the
        # LIMIT one, and break the executor's placeholder-style detection.
        sql = "SELECT * FROM sales WHERE region = :region AND category = :category LIMIT :limit"
        result = enforce_row_cap(sql, cap=1000, dialect="duckdb")
        assert result == sql
        assert "$" not in result

    def test_duckdb_placeholders_preserved_when_clamping_a_literal_limit(self):
        sql = "SELECT * FROM sales WHERE region = :region LIMIT 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="duckdb")
        assert result == "SELECT * FROM sales WHERE region = :region LIMIT 1000"
        assert "$" not in result

    def test_duckdb_placeholders_preserved_when_injecting_a_missing_limit(self):
        sql = "SELECT * FROM sales WHERE region = :region AND category = :category"
        result = enforce_row_cap(sql, cap=1000, dialect="duckdb")
        assert result == "SELECT * FROM sales WHERE region = :region AND category = :category\nLIMIT 1000"
        assert "$" not in result

    def test_injecting_limit_strips_trailing_semicolon(self):
        result = enforce_row_cap("SELECT * FROM employees;", cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM employees\nLIMIT 1000"

    def test_clamping_only_replaces_the_limit_literal_not_other_occurrences(self):
        # The clamped value (99999) also happens to appear as a WHERE literal —
        # only the LIMIT clause's occurrence must be touched.
        sql = "SELECT * FROM sales WHERE id != 99999 LIMIT 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM sales WHERE id != 99999 LIMIT 1000"

    def test_nested_subquery_limit_not_clamped_only_outer_limit_is(self):
        # Regression: a naive first-match text search would clamp the
        # subquery's LIMIT (which appears first in source order) and leave the
        # outer query's LIMIT — the one the AST actually reports and the one
        # that governs how many rows the caller gets back — untouched.
        sql = "SELECT * FROM (SELECT * FROM sales LIMIT 99999) s LIMIT 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM (SELECT * FROM sales LIMIT 99999) s LIMIT 1000"

    def test_limit_text_inside_string_literal_not_mistaken_for_clause(self):
        sql = "SELECT * FROM sales WHERE note = 'LIMIT 99999' LIMIT 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="sqlite")
        assert result == "SELECT * FROM sales WHERE note = 'LIMIT 99999' LIMIT 1000"

    def test_mysql_comma_form_clamps_count_not_offset(self):
        # Regression: MySQL's "LIMIT offset, count" puts the offset first —
        # naively clamping the first number after LIMIT would rewrite the
        # offset and leave the actual row count (99999) uncapped.
        sql = "SELECT * FROM sales LIMIT 20, 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="mysql")
        assert result == "SELECT * FROM sales LIMIT 20, 1000"

    def test_limit_count_offset_form_clamps_count_only(self):
        sql = "SELECT * FROM sales LIMIT 99999 OFFSET 20"
        result = enforce_row_cap(sql, cap=1000, dialect="mysql")
        assert result == "SELECT * FROM sales LIMIT 1000 OFFSET 20"

    @pytest.mark.parametrize("dialect", ["postgres", "mysql", "sqlite", None])
    def test_postgres_limit_all_is_rewritten_to_cap(self, dialect):
        # Regression: PostgreSQL's "LIMIT ALL" is explicitly unbounded, not
        # merely absent. sqlglot's postgres dialect drops it from the AST
        # entirely (indistinguishable from no LIMIT at all without the
        # dedicated check), while other dialects parse it as a Limit node
        # wrapping a non-numeric Column("ALL") that the numeric-comparison
        # path can't interpret either. Both must still get capped.
        sql = "SELECT * FROM sales LIMIT ALL"
        result = enforce_row_cap(sql, cap=1000, dialect=dialect)
        assert result == "SELECT * FROM sales LIMIT 1000"

    def test_limit_all_with_placeholders_preserves_them(self):
        sql = "SELECT * FROM sales WHERE region = :region LIMIT ALL"
        result = enforce_row_cap(sql, cap=1000, dialect="postgres")
        assert result == "SELECT * FROM sales WHERE region = :region LIMIT 1000"

    def test_outer_limit_all_wins_over_nested_subquery_limit_all(self):
        sql = "SELECT * FROM (SELECT * FROM sales LIMIT ALL) s LIMIT 99999"
        result = enforce_row_cap(sql, cap=1000, dialect="postgres")
        assert result == "SELECT * FROM (SELECT * FROM sales LIMIT ALL) s LIMIT 1000"


class TestEnforceRowCapTSqlTop:
    """SQL Server has no LIMIT keyword at all — it uses TOP, which appears
    right after SELECT rather than at the end of the query, so it needs its
    own locator logic distinct from LIMIT's (see _find_outer_row_count_token_indices)."""

    def test_parenthesized_top_literal_clamped(self):
        result = enforce_row_cap("SELECT TOP (99999) * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP (1000) * FROM sales"

    def test_bare_top_literal_clamped(self):
        result = enforce_row_cap("SELECT TOP 99999 * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP 1000 * FROM sales"

    def test_top_within_cap_left_alone(self):
        result = enforce_row_cap("SELECT TOP (10) * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP (10) * FROM sales"

    def test_bound_top_placeholder_left_unchanged_by_enforce_row_cap(self):
        # enforce_row_cap only clamps literals — a bound TOP is
        # clamp_bound_limit_parameter's job, not this function's.
        result = enforce_row_cap("SELECT TOP (?) * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP (?) * FROM sales"

    def test_missing_clause_injects_top_after_select(self):
        result = enforce_row_cap("SELECT * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP (1000) * FROM sales"

    def test_missing_clause_injects_top_after_distinct(self):
        result = enforce_row_cap("SELECT DISTINCT * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT DISTINCT TOP (1000) * FROM sales"

    def test_outer_top_not_confused_with_cte_top(self):
        sql = "WITH cte AS (SELECT TOP (5) * FROM y) SELECT TOP (99999) * FROM cte"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == "WITH cte AS (SELECT TOP (5) * FROM y) SELECT TOP (1000) * FROM cte"

    def test_missing_outer_clause_with_nested_subquery_top_present(self):
        # Regression: a naive "first TOP token in the whole stream" locator
        # would target the subquery's TOP instead of injecting one for the
        # outer query, which has none.
        sql = "SELECT * FROM (SELECT TOP (5) * FROM y) s"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == "SELECT TOP (1000) * FROM (SELECT TOP (5) * FROM y) s"

    def test_top_percent_rejected_even_within_numeric_cap(self):
        # Regression: TOP (n) PERCENT's count is a percentage of the result
        # set, not a row count — "100 <= cap" looks safe numerically but
        # TOP (100) PERCENT returns the entire table. Must reject outright,
        # not silently pass a numeric comparison that doesn't mean anything.
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT TOP (100) PERCENT * FROM sales", cap=1000, dialect="tsql")

    def test_top_percent_rejected_when_above_cap_too(self):
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT TOP (99999) PERCENT * FROM sales", cap=1000, dialect="tsql")

    def test_bare_top_percent_rejected(self):
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT TOP 50 PERCENT * FROM sales", cap=1000, dialect="tsql")

    def test_top_with_ties_rejected(self):
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT TOP (10) WITH TIES * FROM sales ORDER BY y", cap=1000, dialect="tsql")

    def test_top_percent_with_ties_rejected(self):
        with pytest.raises(QueryGuardError):
            enforce_row_cap(
                "SELECT TOP (10) PERCENT WITH TIES * FROM sales ORDER BY y", cap=1000, dialect="tsql"
            )

    def test_ordinary_top_still_clamps_normally(self):
        result = enforce_row_cap("SELECT TOP (99999) * FROM sales", cap=1000, dialect="tsql")
        assert result == "SELECT TOP (1000) * FROM sales"

    def test_uncapped_tsql_union_rejected(self):
        # Regression: T-SQL has no syntax to cap a UNION's combined result —
        # TOP belongs to a SELECT, not a set operation. Injecting TOP into
        # only the first depth-zero SELECT (the naive approach) leaves every
        # other arm of the union completely unbounded, so the combined
        # result can exceed the cap regardless of what's injected.
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT * FROM x UNION ALL SELECT * FROM y", cap=1000, dialect="tsql")

    def test_uncapped_tsql_union_rejected_even_with_one_arm_capped(self):
        # One arm already having its own TOP doesn't help — the *other* arm
        # is still unbounded, so the union as a whole still isn't capped.
        with pytest.raises(QueryGuardError):
            enforce_row_cap(
                "SELECT TOP (5) * FROM x UNION ALL SELECT * FROM y", cap=1000, dialect="tsql"
            )

    def test_tsql_union_wrapped_in_capped_subquery_is_not_rejected(self):
        # The escape hatch: wrapping the union in a subquery with its own
        # outer TOP parses as a plain Select (not a Union) and hits the
        # ordinary clamp path — this must keep working, not get swept into
        # the union rejection.
        sql = "SELECT TOP (99999) * FROM (SELECT * FROM x UNION ALL SELECT * FROM y) u"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == "SELECT TOP (1000) * FROM (SELECT * FROM x UNION ALL SELECT * FROM y) u"

    def test_non_tsql_union_without_limit_still_gets_one_appended(self):
        # Standard SQL's LIMIT-after-UNION genuinely bounds the combined
        # result, unlike T-SQL's TOP — this dialect path is unaffected.
        result = enforce_row_cap("SELECT * FROM x UNION ALL SELECT * FROM y", cap=1000, dialect="postgres")
        assert result == "SELECT * FROM x UNION ALL SELECT * FROM y\nLIMIT 1000"

    def test_capped_union_result_cannot_exceed_the_cap(self):
        """The literal assertion the review asked for: a query the guard
        allows through (or fails to reject) must not be able to return more
        than `cap` rows. For a T-SQL union, the only way this function lets
        the query proceed at all is via the wrapped-subquery escape hatch,
        which does genuinely bound the combined result — verified by parsing
        the guard's own output and confirming a real outer TOP is present."""
        sql = "SELECT TOP (99999) * FROM (SELECT * FROM x UNION ALL SELECT * FROM y) u"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")

        outer = sqlglot.parse_one(result, read="tsql")
        assert isinstance(outer, exp.Select)
        assert int(outer.args["limit"].expression.this) == 1000

        # And the genuinely uncapped, unwrapped form is rejected outright —
        # it is never allowed to reach execution with an unbounded arm.
        with pytest.raises(QueryGuardError):
            enforce_row_cap("SELECT * FROM x UNION ALL SELECT * FROM y", cap=1000, dialect="tsql")


class TestEnforceRowCapTSqlFetch:
    """SQL Server's OFFSET ... FETCH NEXT n ROWS ONLY — sqlglot represents
    this as a distinct exp.Fetch node (count under .args["count"]), not the
    same exp.Limit node LIMIT/TOP use (count under .expression), so it needs
    its own extraction path via _row_count_expression()."""

    def test_literal_fetch_next_clamped(self):
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT 99999 ROWS ONLY"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT 1000 ROWS ONLY"

    def test_fetch_next_within_cap_left_alone(self):
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == sql

    def test_bound_fetch_next_placeholder_left_unchanged_by_enforce_row_cap(self):
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == sql

    def test_bound_fetch_next_value_clamped_via_clamp_bound_limit_parameter(self):
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
        params = {"limit": 99999}
        clamp_bound_limit_parameter(sql, params, cap=1000, dialect="tsql", positional_param_names=["limit"])
        assert params["limit"] == 1000

    def test_named_bound_fetch_next_value_clamped(self):
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH NEXT :limit ROWS ONLY"
        params = {"limit": 99999}
        clamp_bound_limit_parameter(sql, params, cap=1000, dialect="tsql", positional_param_names=["limit"])
        assert params["limit"] == 1000

    def test_union_with_fetch_attached_to_last_arm_still_rejected(self):
        # sqlglot attaches a trailing ORDER BY/OFFSET/FETCH after a UNION to
        # the last arm's Select rather than the Union node itself, so the
        # top-level parsed.args["limit"] is still None here — this must fall
        # through to the same uncapped-union rejection as the plain case,
        # not silently slip through because a nested Fetch node exists
        # somewhere in the tree.
        sql = "SELECT * FROM a UNION ALL SELECT * FROM b ORDER BY 1 OFFSET 0 ROWS FETCH NEXT 99999 ROWS ONLY"
        with pytest.raises(QueryGuardError):
            enforce_row_cap(sql, cap=1000, dialect="tsql")

    def test_fetch_first_variant_clamped(self):
        # FETCH FIRST is the ISO/Oracle-style synonym for FETCH NEXT; sqlglot
        # accepts either.
        sql = "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH FIRST 99999 ROWS ONLY"
        result = enforce_row_cap(sql, cap=1000, dialect="tsql")
        assert result == "SELECT * FROM sales ORDER BY id OFFSET 0 ROWS FETCH FIRST 1000 ROWS ONLY"


class TestEnforceRowCapFetchPercentAndWithTies:
    """PERCENT and WITH TIES aren't SQL-Server/TOP-specific — PostgreSQL and
    Oracle support the same modifiers on the ANSI FETCH FIRST ... ROWS
    syntax, and sqlglot exposes them under the same `limit_options` arg
    regardless of whether a Limit (TOP) or Fetch (FETCH FIRST) node carries
    it, so the same rejection in enforce_row_cap must cover both node types
    across every dialect, not just tsql."""

    @pytest.mark.parametrize("dialect", ["postgres", "oracle"])
    def test_fetch_first_with_ties_rejected(self, dialect):
        # Regression: WITH TIES can return more rows than its stated count
        # whenever the ORDER BY column has ties — even a count within cap
        # is not a hard bound.
        sql = "SELECT * FROM sales ORDER BY y FETCH FIRST 10 ROWS WITH TIES"
        with pytest.raises(QueryGuardError):
            enforce_row_cap(sql, cap=1000, dialect=dialect)

    @pytest.mark.parametrize("dialect", ["postgres", "oracle"])
    def test_fetch_first_percent_rejected(self, dialect):
        sql = "SELECT * FROM sales FETCH FIRST 50 PERCENT ROWS ONLY"
        with pytest.raises(QueryGuardError):
            enforce_row_cap(sql, cap=1000, dialect=dialect)

    @pytest.mark.parametrize("dialect", ["postgres", "oracle"])
    def test_fetch_first_with_ties_error_names_fetch_not_top(self, dialect):
        # The error message must describe the clause that's actually in the
        # query — postgres/oracle have no TOP keyword at all, so a message
        # hardcoding "TOP" would be actively misleading here.
        sql = "SELECT * FROM sales ORDER BY y FETCH FIRST 10 ROWS WITH TIES"
        with pytest.raises(QueryGuardError, match="FETCH"):
            enforce_row_cap(sql, cap=1000, dialect=dialect)

    def test_tsql_top_with_ties_error_still_names_top(self):
        with pytest.raises(QueryGuardError, match="TOP"):
            enforce_row_cap("SELECT TOP (10) WITH TIES * FROM sales ORDER BY y", cap=1000, dialect="tsql")

    def test_ordinary_fetch_first_still_clamps_normally_for_postgres_and_oracle(self):
        for dialect in ("postgres", "oracle"):
            result = enforce_row_cap(
                "SELECT * FROM sales ORDER BY y FETCH FIRST 99999 ROWS ONLY", cap=1000, dialect=dialect
            )
            assert result == "SELECT * FROM sales ORDER BY y FETCH FIRST 1000 ROWS ONLY", (dialect, result)


class TestFindOuterLimitBindName:
    def test_colon_name_form(self):
        assert find_outer_limit_bind_name("SELECT * FROM x LIMIT :limit", dialect="duckdb") == "limit"

    def test_percent_name_form(self):
        assert find_outer_limit_bind_name("SELECT * FROM x LIMIT %(limit)s", dialect="postgres") == "limit"

    def test_positional_returns_none(self):
        assert find_outer_limit_bind_name("SELECT * FROM x LIMIT ?", dialect="sqlite") is None

    def test_literal_limit_returns_none(self):
        assert find_outer_limit_bind_name("SELECT * FROM x LIMIT 10", dialect="sqlite") is None

    def test_no_limit_returns_none(self):
        assert find_outer_limit_bind_name("SELECT * FROM x", dialect="sqlite") is None


class TestFindOuterLimitPositionalIndex:
    def test_single_placeholder(self):
        assert find_outer_limit_positional_index("SELECT * FROM x LIMIT ?", dialect="sqlite") == 0

    def test_limit_is_not_the_first_placeholder(self):
        sql = "SELECT * FROM x WHERE a = ? AND b = ? LIMIT ?"
        assert find_outer_limit_positional_index(sql, dialect="sqlite") == 2

    def test_named_placeholder_returns_none(self):
        assert find_outer_limit_positional_index("SELECT * FROM x LIMIT :limit", dialect="duckdb") is None

    def test_mysql_comma_form_resolves_to_the_second_placeholder(self):
        # Regression: MySQL's "LIMIT offset, count" puts the offset
        # placeholder first — naively taking "the ? immediately after LIMIT"
        # would resolve to the offset's slot, not the count's.
        assert find_outer_limit_positional_index("SELECT * FROM x LIMIT ?, ?", dialect="mysql") == 1

    def test_mysql_comma_form_with_a_preceding_where_placeholder(self):
        sql = "SELECT * FROM x WHERE region = ? LIMIT ?, ?"
        assert find_outer_limit_positional_index(sql, dialect="mysql") == 2

    def test_parenthesized_top_placeholder(self):
        assert find_outer_limit_positional_index("SELECT TOP (?) * FROM x", dialect="tsql") == 0

    def test_top_placeholder_not_confused_with_cte_top(self):
        sql = "WITH cte AS (SELECT TOP (5) * FROM y) SELECT TOP (?) * FROM cte"
        assert find_outer_limit_positional_index(sql, dialect="tsql") == 0


class TestClampBoundLimitParameter:
    def test_named_colon_form_clamped(self):
        params = {"revenue_threshold": 10000.0, "limit": 99999}
        clamped = clamp_bound_limit_parameter(
            "SELECT * FROM sales HAVING x < :revenue_threshold LIMIT :limit",
            params, cap=1000, dialect="duckdb",
            positional_param_names=["revenue_threshold", "limit"],
        )
        assert params == {"revenue_threshold": 10000.0, "limit": 1000}
        assert clamped is True

    def test_return_value_is_true_only_when_a_value_was_actually_clamped(self):
        # Regression: the return value is what callers (e.g.
        # intent_sql_base.py's row-cap metric) use to distinguish "a bound
        # LIMIT was clamped" from every other case — it must be an honest
        # bool, not None/truthy-by-accident.
        clamped_params = {"limit": 99999}
        assert clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", clamped_params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        ) is True

        within_cap_params = {"limit": 10}
        assert clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", within_cap_params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        ) is False

        no_bound_limit_params = {"limit": 99999}
        assert clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT 99999", no_bound_limit_params, cap=1000, dialect="sqlite",
            positional_param_names=["limit"],
        ) is False

        unresolvable_positional_params = {"limit": 99999}
        assert clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT ?", unresolvable_positional_params, cap=1000, dialect="sqlite",
            positional_param_names=None,
        ) is False

    def test_named_percent_form_clamped(self):
        params = {"limit": 50000}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT %(limit)s", params, cap=1000, dialect="postgres",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_positional_form_clamped_via_param_order(self):
        params = {"region": "west", "limit": 50000}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales WHERE region = ? LIMIT ?", params, cap=1000, dialect="sqlite",
            positional_param_names=["region", "limit"],
        )
        assert params == {"region": "west", "limit": 1000}

    def test_mysql_comma_form_clamps_count_not_offset(self):
        params = {"offset": 20, "count": 99999}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT ?, ?", params, cap=1000, dialect="mysql",
            positional_param_names=["offset", "count"],
        )
        assert params == {"offset": 20, "count": 1000}

    def test_tsql_top_named_form_clamped(self):
        params = {"limit": 99999}
        clamp_bound_limit_parameter(
            "SELECT TOP (:limit) * FROM sales", params, cap=1000, dialect="tsql",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_tsql_top_positional_form_clamped(self):
        params = {"limit": 99999}
        clamp_bound_limit_parameter(
            "SELECT TOP (?) * FROM sales", params, cap=1000, dialect="tsql",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_value_within_cap_left_alone(self):
        params = {"limit": 10}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 10

    def test_literal_limit_is_a_noop_here(self):
        # enforce_row_cap already handles a literal LIMIT — this function only
        # has something to do when the count is a bound placeholder.
        params = {"limit": 99999}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT 99999", params, cap=1000, dialect="sqlite",
            positional_param_names=["limit"],
        )
        assert params == {"limit": 99999}

    def test_positional_without_param_names_leaves_value_unclamped(self):
        # Can't resolve which slot is the LIMIT without the ordered param
        # names — must not guess, and must not silently pretend it clamped.
        params = {"limit": 99999}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT ?", params, cap=1000, dialect="sqlite",
            positional_param_names=None,
        )
        assert params == {"limit": 99999}

    def test_numeric_string_named_value_clamped(self):
        # Regression: a parameter extractor can hand this function "99999"
        # (str) instead of 99999 (int) — several DB drivers happily coerce a
        # numeric string when binding a LIMIT/TOP/FETCH parameter, so leaving
        # it as a string here would execute the oversized value uncapped.
        params = {"limit": "99999"}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_numeric_string_positional_value_clamped(self):
        params = {"limit": "99999"}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT ?", params, cap=1000, dialect="sqlite",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_numeric_string_within_cap_left_as_is(self):
        # Not clamped — and not coerced to int either, since there's nothing
        # to clamp; the value should reach the driver exactly as extraction
        # produced it.
        params = {"limit": "10"}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == "10"

    def test_float_string_value_clamped(self):
        params = {"limit": "99999.0"}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_non_numeric_string_left_unchanged(self):
        # Nothing safe to clamp — and not this function's job to reject a
        # value that will fail at the database driver on its own.
        params = {"limit": "abc"}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == "abc"

    def test_bool_value_not_treated_as_numeric(self):
        # bool is a subclass of int in Python — must not be compared against
        # the cap as if it were a row count.
        params = {"limit": True}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] is True

    def test_nan_and_non_whole_float_left_unchanged(self):
        params = {"limit": float("nan")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert math.isnan(params["limit"])

        params2 = {"limit": 99999.5}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params2, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params2["limit"] == 99999.5

    def test_decimal_named_value_clamped(self):
        # Regression: decimal.Decimal is a common numeric type for
        # parameters sourced from a database/ORM, and several drivers accept
        # or coerce it directly in a row-count bind position — left
        # unhandled, it would execute the oversized value uncapped.
        params = {"limit": Decimal("99999")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_decimal_positional_value_clamped(self):
        params = {"limit": Decimal("99999")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT ?", params, cap=1000, dialect="sqlite",
            positional_param_names=["limit"],
        )
        assert params["limit"] == 1000

    def test_decimal_within_cap_left_as_is(self):
        params = {"limit": Decimal("10")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == Decimal("10")

    def test_fractional_decimal_left_unchanged(self):
        params = {"limit": Decimal("99999.5")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == Decimal("99999.5")

    def test_non_finite_decimal_left_unchanged(self):
        params = {"limit": Decimal("Infinity")}
        clamp_bound_limit_parameter(
            "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="duckdb",
            positional_param_names=["limit"],
        )
        assert params["limit"] == Decimal("Infinity")

    def test_negative_named_bound_value_rejected(self):
        # Regression: SQLite treats a bound LIMIT of -1 as "no limit at
        # all" — "value > cap" is False for -1, so a naive comparison would
        # leave it alone as if it were safely small.
        params = {"limit": -1}
        with pytest.raises(QueryGuardError):
            clamp_bound_limit_parameter(
                "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="sqlite",
                positional_param_names=["limit"],
            )

    def test_negative_positional_bound_value_rejected(self):
        params = {"limit": -1}
        with pytest.raises(QueryGuardError):
            clamp_bound_limit_parameter(
                "SELECT * FROM sales LIMIT ?", params, cap=1000, dialect="sqlite",
                positional_param_names=["limit"],
            )

    def test_negative_numeric_string_bound_value_rejected(self):
        params = {"limit": "-1"}
        with pytest.raises(QueryGuardError):
            clamp_bound_limit_parameter(
                "SELECT * FROM sales LIMIT :limit", params, cap=1000, dialect="sqlite",
                positional_param_names=["limit"],
            )
