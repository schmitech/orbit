"""
Shared SQL placeholder-style detection and conversion helpers.

Centralizes the dialect-conversion logic that `base/intent_sql_base.py`,
`intent_sqlite_retriever.py`, `intent_duckdb_retriever.py`, and
`intent_athena_retriever.py` each previously implemented independently with
their own regexes (see docs/roadmap/retrievers-implementations-cleanup.md,
Phase 2) -- there is now exactly one regex-based implementation of "find
named placeholders in a rendered SQL string, in order" instead of four.

Known limitation, inherited unchanged from the per-backend implementations
this replaces: style detection works on the rendered SQL text via regex, not
a real SQL parser, so a string literal or comment that happens to contain
'%(name)s' or ':name' could in principle be mistaken for a real placeholder.
This was already true of every implementation being consolidated here and is
not a regression.
"""

import re
from typing import Optional

PYFORMAT_RE = re.compile(r'%\((\w+)\)s')
# Negative lookbehind excludes PostgreSQL/DuckDB '::type' casts, which a bare
# `:(\w+)` would otherwise misread as a ':type'-named placeholder. A '?'
# lookahead is deliberately NOT added here: ':name::type' (a real ':name'
# placeholder immediately followed by a cast on the bound value) must still
# capture the full 'name', and a trailing lookahead would instead truncate it
# by forcing backtracking. The lookbehind alone is sufficient -- the second
# colon of a bare '::type' can never match '(\w+)' immediately after it
# (it's followed by another colon, not a word character), and is also
# directly excluded by the lookbehind once the first colon has been
# consumed by a preceding match.
COLON_RE = re.compile(r'(?<!:):(\w+)')


def detect_placeholder_style(sql: str) -> str:
    """
    Return the first kind of placeholder found in `sql`:
    'pyformat' (%(name)s), 'colon' (:name), 'qmark' (?), or 'none'.
    """
    if PYFORMAT_RE.search(sql):
        return 'pyformat'
    if COLON_RE.search(sql):
        return 'colon'
    if '?' in sql:
        return 'qmark'
    return 'none'


def extract_ordered_param_names(sql: str, style: str) -> list[str]:
    """
    Return the named placeholders in `sql`, in order of appearance, with
    duplicates preserved (a parameter referenced twice appears twice).
    """
    if style == 'pyformat':
        return PYFORMAT_RE.findall(sql)
    if style == 'colon':
        return COLON_RE.findall(sql)
    return []


def convert_named_style(sql: str, to_style: str) -> str:
    """
    Rewrite pyformat/colon named placeholders to `to_style` ('pyformat' or
    'colon'), preserving names and order. No-op if `sql` has no named
    placeholders, or is already in `to_style`.
    """
    style = detect_placeholder_style(sql)
    if style == to_style or style not in ('pyformat', 'colon'):
        return sql
    if to_style == 'colon':
        return PYFORMAT_RE.sub(r':\1', sql)
    if to_style == 'pyformat':
        return COLON_RE.sub(r'%(\1)s', sql)
    return sql


def convert_named_to_qmark(sql: str, style: Optional[str] = None) -> tuple[str, list[str]]:
    """
    Convert pyformat/colon named placeholders to '?' positional markers.

    Returns (converted_sql, ordered_param_names): one name per '?' in the
    output, in order, with duplicates preserved for a parameter referenced
    more than once (so a caller can zip this list against the values dict to
    build a correctly-ordered positional sequence).
    """
    style = style or detect_placeholder_style(sql)
    if style == 'pyformat':
        return PYFORMAT_RE.sub('?', sql), PYFORMAT_RE.findall(sql)
    if style == 'colon':
        return COLON_RE.sub('?', sql), COLON_RE.findall(sql)
    return sql, []


def convert_qmark_to_pyformat(
    sql: str,
    positional_param_names: Optional[list[str]] = None,
    max_replacements: Optional[int] = None,
) -> tuple[str, list[str]]:
    """
    Convert '?' positional placeholders to %(name)s.

    Uses `positional_param_names[i]` (the template's declared parameter order)
    as the name for the i-th '?' when available, falling back to a generated
    `p{i}` name otherwise.

    `max_replacements`, when given, caps how many '?' occurrences are
    converted -- any further '?' in the text (e.g. inside a string literal
    like `'?'` that isn't a real placeholder) is left untouched. Callers
    should pass the number of positional values they actually have to bind,
    not the number of '?' characters found in the text, since a query can
    contain more literal '?'s than real placeholders.
    """
    generated: list[str] = []

    def _replace(match: "re.Match[str]") -> str:
        idx = len(generated)
        if max_replacements is not None and idx >= max_replacements:
            return match.group(0)
        if positional_param_names and idx < len(positional_param_names):
            name = positional_param_names[idx]
        else:
            name = f"p{idx}"
        generated.append(name)
        return f"%({name})s"

    converted = re.sub(r'\?', _replace, sql)
    return converted, generated


def escape_literal_percents_for_pyformat(sql: str) -> str:
    """
    Escape literal percent signs for pyformat queries while preserving
    placeholders.

    Keeps:
    - `%(name)s` placeholders
    - existing `%%` escapes

    Escapes:
    - `%` in SQL string literals like `LIKE '%cloud%'`
    """
    out: list[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue

        # Already escaped percent
        if i + 1 < n and sql[i + 1] == "%":
            out.append("%%")
            i += 2
            continue

        # Placeholder start: %(name)s
        if i + 1 < n and sql[i + 1] == "(":
            end_paren = sql.find(")", i + 2)
            if end_paren != -1 and end_paren + 1 < n and sql[end_paren + 1] == "s":
                out.append(sql[i:end_paren + 2])
                i = end_paren + 2
                continue

        # Literal percent -> escape
        out.append("%%")
        i += 1

    return "".join(out)
