"""
Tests for the shared SQL placeholder-style detection/conversion helpers
(retrievers/base/sql_param_binding.py).

This module consolidates placeholder-conversion logic that
intent_sqlite_retriever.py, intent_duckdb_retriever.py, and
intent_athena_retriever.py each used to reimplement independently (see
docs/roadmap/retrievers-implementations-cleanup.md, Phase 2). These tests
cover the specific cases the roadmap called out as required before relying
on the shared implementation: repeated placeholders, PostgreSQL/DuckDB-style
casts, and literal '%' escaping.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.base.sql_param_binding import (
    convert_named_style,
    convert_named_to_qmark,
    convert_qmark_to_pyformat,
    detect_placeholder_style,
    escape_literal_percents_for_pyformat,
    extract_ordered_param_names,
)


class TestDetectPlaceholderStyle:
    def test_pyformat(self):
        assert detect_placeholder_style("SELECT * FROM t WHERE id = %(id)s") == 'pyformat'

    def test_colon(self):
        assert detect_placeholder_style("SELECT * FROM t WHERE id = :id") == 'colon'

    def test_qmark(self):
        assert detect_placeholder_style("SELECT * FROM t WHERE id = ?") == 'qmark'

    def test_none(self):
        assert detect_placeholder_style("SELECT * FROM t") == 'none'

    def test_pyformat_takes_priority_when_mixed(self):
        # Shouldn't happen in practice, but pyformat is checked first.
        sql = "SELECT * FROM t WHERE id = %(id)s AND name = :name"
        assert detect_placeholder_style(sql) == 'pyformat'

    def test_postgres_style_double_colon_cast_is_not_a_placeholder(self):
        """
        A bare `::type` cast (no real named placeholder anywhere) must not be
        misread as a ':type' placeholder.
        """
        sql = "SELECT col::INTEGER FROM t"
        assert detect_placeholder_style(sql) == 'none'

    def test_qmark_detected_alongside_double_colon_cast(self):
        sql = "SELECT col::INTEGER FROM t WHERE id = ?"
        assert detect_placeholder_style(sql) == 'qmark'


class TestExtractOrderedParamNames:
    def test_pyformat_preserves_order_and_duplicates(self):
        sql = "SELECT * FROM t WHERE a = %(x)s OR b = %(y)s OR c = %(x)s"
        assert extract_ordered_param_names(sql, 'pyformat') == ['x', 'y', 'x']

    def test_colon_preserves_order_and_duplicates(self):
        sql = "SELECT * FROM t WHERE a = :x OR b = :y OR c = :x"
        assert extract_ordered_param_names(sql, 'colon') == ['x', 'y', 'x']

    def test_colon_style_skips_double_colon_cast(self):
        sql = "SELECT col::INTEGER FROM t WHERE id = :id"
        assert extract_ordered_param_names(sql, 'colon') == ['id']

    def test_colon_param_immediately_followed_by_cast(self):
        """A real `:param` immediately followed by a `::type` cast on the
        bound value (e.g. `:param::integer`) must yield just the one real
        placeholder name, not a spurious second one from the cast."""
        sql = "SELECT * FROM t WHERE id = :param::integer"
        assert extract_ordered_param_names(sql, 'colon') == ['param']

    def test_qmark_style_has_no_named_params(self):
        assert extract_ordered_param_names("SELECT * FROM t WHERE id = ?", 'qmark') == []


class TestConvertNamedStyle:
    def test_pyformat_to_colon(self):
        sql = "SELECT * FROM t WHERE a = %(x)s AND b = %(y)s"
        assert convert_named_style(sql, to_style='colon') == "SELECT * FROM t WHERE a = :x AND b = :y"

    def test_colon_to_pyformat(self):
        sql = "SELECT * FROM t WHERE a = :x AND b = :y"
        assert convert_named_style(sql, to_style='pyformat') == "SELECT * FROM t WHERE a = %(x)s AND b = %(y)s"

    def test_noop_when_already_target_style(self):
        sql = "SELECT * FROM t WHERE a = :x"
        assert convert_named_style(sql, to_style='colon') == sql

    def test_noop_for_qmark_sql(self):
        sql = "SELECT * FROM t WHERE a = ?"
        assert convert_named_style(sql, to_style='pyformat') == sql

    def test_repeated_placeholder_converted_consistently(self):
        sql = "SELECT * FROM t WHERE a = %(x)s OR b = %(x)s"
        assert convert_named_style(sql, to_style='colon') == "SELECT * FROM t WHERE a = :x OR b = :x"

    def test_double_colon_cast_preserved_when_converting_to_pyformat(self):
        sql = "SELECT col::INTEGER FROM t WHERE id = :id"
        assert convert_named_style(sql, to_style='pyformat') == "SELECT col::INTEGER FROM t WHERE id = %(id)s"


class TestConvertNamedToQmark:
    def test_pyformat_to_qmark(self):
        sql = "SELECT * FROM t WHERE a = %(x)s AND b = %(y)s"
        converted, names = convert_named_to_qmark(sql)
        assert converted == "SELECT * FROM t WHERE a = ? AND b = ?"
        assert names == ['x', 'y']

    def test_colon_to_qmark(self):
        sql = "SELECT * FROM t WHERE a = :x AND b = :y"
        converted, names = convert_named_to_qmark(sql)
        assert converted == "SELECT * FROM t WHERE a = ? AND b = ?"
        assert names == ['x', 'y']

    def test_repeated_placeholder_yields_one_name_per_occurrence(self):
        """Same named parameter referenced twice must produce two ordered
        entries (one per '?' it becomes), not be deduplicated -- the
        resulting '?' count must match the resulting names count so a
        caller can zip them into a positional value list."""
        sql = "SELECT * FROM t WHERE a = %(x)s OR b = %(y)s OR c = %(x)s"
        converted, names = convert_named_to_qmark(sql)
        assert converted.count('?') == 3
        assert names == ['x', 'y', 'x']

    def test_already_qmark_is_a_noop(self):
        sql = "SELECT * FROM t WHERE a = ?"
        converted, names = convert_named_to_qmark(sql)
        assert converted == sql
        assert names == []

    def test_double_colon_cast_not_treated_as_placeholder(self):
        sql = "SELECT col::INTEGER FROM t WHERE id = :id"
        converted, names = convert_named_to_qmark(sql)
        assert converted == "SELECT col::INTEGER FROM t WHERE id = ?"
        assert names == ['id']


class TestConvertQmarkToPyformat:
    def test_uses_provided_positional_names_in_order(self):
        sql = "SELECT * FROM t WHERE a = ? AND b = ?"
        converted, names = convert_qmark_to_pyformat(sql, positional_param_names=['limit', 'offset'])
        assert converted == "SELECT * FROM t WHERE a = %(limit)s AND b = %(offset)s"
        assert names == ['limit', 'offset']

    def test_generates_names_when_none_provided(self):
        sql = "SELECT * FROM t WHERE a = ? AND b = ?"
        converted, names = convert_qmark_to_pyformat(sql)
        assert converted == "SELECT * FROM t WHERE a = %(p0)s AND b = %(p1)s"
        assert names == ['p0', 'p1']

    def test_falls_back_to_generated_name_past_end_of_provided_list(self):
        sql = "SELECT * FROM t WHERE a = ? AND b = ?"
        converted, names = convert_qmark_to_pyformat(sql, positional_param_names=['limit'])
        assert converted == "SELECT * FROM t WHERE a = %(limit)s AND b = %(p1)s"
        assert names == ['limit', 'p1']

    def test_repeated_occurrence_count_matches_names_count(self):
        sql = "SELECT * FROM t WHERE a = ? OR b = ? OR c = ?"
        converted, names = convert_qmark_to_pyformat(sql)
        assert converted.count('%(') == 3
        assert len(names) == 3


class TestEscapeLiteralPercentsForPyformat:
    def test_preserves_named_placeholder(self):
        sql = "SELECT * FROM t WHERE name = %(name)s"
        assert escape_literal_percents_for_pyformat(sql) == sql

    def test_escapes_literal_percent_in_like_pattern(self):
        sql = "SELECT * FROM t WHERE name LIKE '%cloud%'"
        assert escape_literal_percents_for_pyformat(sql) == "SELECT * FROM t WHERE name LIKE '%%cloud%%'"

    def test_preserves_existing_double_percent_escape(self):
        sql = "SELECT * FROM t WHERE name LIKE '%%cloud%%'"
        assert escape_literal_percents_for_pyformat(sql) == sql

    def test_mixed_placeholder_and_literal_percent(self):
        sql = "SELECT * FROM t WHERE name LIKE %(pattern)s AND tag LIKE '%cloud%'"
        expected = "SELECT * FROM t WHERE name LIKE %(pattern)s AND tag LIKE '%%cloud%%'"
        assert escape_literal_percents_for_pyformat(sql) == expected
