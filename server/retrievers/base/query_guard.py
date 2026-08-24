"""
SQL query safety guard for intent templates.

Intent templates are pre-approved, but the rendered SQL a template produces is
still hand-written by a template author. This module is the enforcement point
that makes "no free-form text-to-SQL" a verifiable property of what actually
executes, not just a property of the source templates: it runs against the
fully-rendered SQL (placeholders intact, values not yet bound) immediately
before execution and rejects anything that isn't a single, read-only,
row-capped query.
"""

import logging
import math
import re
from decimal import Decimal
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.tokens import TokenType

logger = logging.getLogger(__name__)

# Datasource name (as returned by each retriever's _get_datasource_name(), e.g.
# "mysql", "postgres", "sqlite") -> sqlglot dialect, so placeholder syntax
# (%(name)s, :name, ?) and vendor-specific grammar parse correctly. This is the
# SQL backend, not the template vector store (store_name in adapter config,
# which is unrelated — it identifies where template embeddings live, typically
# "chroma", regardless of which SQL database the templates query). Falls back
# to sqlglot's generic dialect for anything not listed.
DATASOURCE_TO_DIALECT = {
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "tsql",
    "sqlserver": "tsql",
    "sqlite": "sqlite",
    "duckdb": "duckdb",
    "oracle": "oracle",
    "athena": "athena",
}

# Deny-list for nodes nested inside an otherwise-read-only query (e.g. a
# mutating CTE). Not the only line of defense — assert_read_only additionally
# requires the top-level statement itself to be a Query (SELECT/UNION/...),
# which is what actually catches TruncateTable, Copy, Execute, Set, and the
# Command catch-all sqlglot falls back to for syntax it doesn't model
# explicitly, none of which are Query subclasses.
_WRITE_OP_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
    exp.Create, exp.Grant, exp.Merge, exp.Command, exp.TruncateTable,
    exp.Copy, exp.Execute, exp.Set,
)


class QueryGuardError(ValueError):
    """Raised when a rendered SQL query fails a safety check."""


def _row_count_expression(existing_limit):
    """
    Return the row-count expression node from a parsed `Limit`/`Fetch` node,
    regardless of which one it is. `exp.Limit` (LIMIT, TOP) holds it under
    `.expression`; `exp.Fetch` (SQL Server's `OFFSET ... FETCH NEXT n ROWS
    ONLY`) holds it under `.args["count"]` instead — a different AST shape
    for what's functionally the same row-count clause. Returns None if
    `existing_limit` is neither.
    """
    if isinstance(existing_limit, exp.Fetch):
        return existing_limit.args.get("count")
    return getattr(existing_limit, "expression", None)


def resolve_dialect(datasource_name: Optional[str]) -> Optional[str]:
    """Map a retriever's SQL datasource name (from _get_datasource_name()) to a
    sqlglot dialect, if known."""
    if not datasource_name:
        return None
    return DATASOURCE_TO_DIALECT.get(datasource_name.lower())


def _parse_statements(sql: str, dialect: Optional[str]):
    try:
        return [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except Exception as e:
        raise QueryGuardError(f"Could not parse rendered SQL: {e}") from e


def assert_single_statement(sql: str, dialect: Optional[str] = None) -> None:
    """Raise QueryGuardError if `sql` contains more than one statement."""
    statements = _parse_statements(sql, dialect)
    if len(statements) > 1:
        raise QueryGuardError(
            f"Rendered query contains {len(statements)} statements; only one is allowed."
        )


def assert_read_only(sql: str, dialect: Optional[str] = None) -> None:
    """Raise QueryGuardError if `sql` isn't a read-only query.

    Enforced two ways: the top-level statement must itself be a Query
    (SELECT/UNION/INTERSECT/EXCEPT/...) — this alone rejects TRUNCATE, COPY,
    EXECUTE, SET, and anything sqlglot can't model and falls back to parsing
    as a generic Command. And no write/DDL/DCL node (from _WRITE_OP_TYPES) may
    appear anywhere inside it, which catches the same operations smuggled
    inside a CTE.
    """
    for statement in _parse_statements(sql, dialect):
        if not isinstance(statement, exp.Query):
            raise QueryGuardError(
                f"Rendered query is not read-only ({type(statement).__name__} is not a query)."
            )
        for node in statement.walk():
            if isinstance(node, _WRITE_OP_TYPES):
                raise QueryGuardError(
                    f"Rendered query is not read-only ({type(node).__name__} found in query)."
                )


def _unwrap_single_statement(parsed):
    """
    sqlglot wraps a query ending in a statement terminator followed only by
    comments/whitespace (e.g. `SELECT ...; -- audit`) in a container
    alongside a synthetic comment-only node standing in for the empty tail
    after the `;` — not the plain `Select`/`Union` the rest of this module
    expects. Unwrap that back to the real statement so a trailing `; --
    comment` doesn't make `enforce_row_cap` bail out and treat an otherwise
    perfectly ordinary query as unrecognized (leaving it with no clamp, no
    injection, and no rejection at all).

    Returns `parsed` unchanged if it's already a `Select`/`Union`, the sole
    real statement inside a wrapper containing exactly one, or None if it's
    some other unrecognized shape.
    """
    if isinstance(parsed, (exp.Select, exp.Union)):
        return parsed
    expressions = getattr(parsed, "args", {}).get("expressions")
    if not isinstance(expressions, list):
        return None
    real_statements = [e for e in expressions if isinstance(e, (exp.Select, exp.Union))]
    if len(real_statements) == 1:
        return real_statements[0]
    return None


def enforce_row_cap(sql: str, cap: int, dialect: Optional[str] = None) -> str:
    """
    Ensure the outer query has a row-count cap no greater than `cap`,
    injecting one if absent or clamping it if larger. Supports LIMIT
    (postgres/mysql/sqlite/duckdb/oracle/athena), SQL Server's TOP, and SQL
    Server's `OFFSET n ROWS FETCH NEXT m ROWS ONLY` (mssql/tsql) — sqlglot
    represents TOP as the same `Limit` AST node as LIMIT, but FETCH as a
    distinct `Fetch` node with the count under a different attribute
    (`.args["count"]` instead of `.expression`); see `_row_count_expression`.
    A count bound to a placeholder (e.g. `?`, `%(limit)s`, `TOP (?)`,
    `FETCH NEXT ?`) is left
    alone — its actual value isn't known until bind time, so it can't be
    safely compared to the cap here (see `clamp_bound_limit_parameter`, which
    clamps the resolved bind value instead).

    Edits are applied as surgical text changes to the original `sql` string,
    never by re-serializing the parsed AST — sqlglot's printer normalizes
    placeholder syntax per dialect (e.g. DuckDB renders a parsed `:name` back
    out as `$name`), which would silently corrupt every other placeholder in
    the query and break the executor's placeholder-style detection. The AST is
    only used to decide *whether* and *what* to change; locating *where* to
    make the change (when clamping an existing count) uses sqlglot's
    tokenizer rather than a text search, so a subquery's own LIMIT/TOP, or
    "LIMIT n" inside a string literal or comment, can't be mistaken for the
    outer query's clause.

    Falls back to returning `sql` unchanged (logging a warning) if it can't be
    parsed, since failing open on a parse error is safer for availability than
    blocking every query a dialect quirk trips up; `assert_single_statement`/
    `assert_read_only` are the hard gates.

    Raises QueryGuardError for a `PERCENT` row-count modifier — the count is
    a percentage of the result set, not a row count, so no numeric
    comparison against `cap` bounds the actual row count at all
    (`TOP (100) PERCENT` / `FETCH FIRST 100 PERCENT ROWS ONLY` both return
    the entire table regardless of what `100` is compared against); and for
    `WITH TIES`, which can return more rows than the stated count whenever
    the ORDER BY column has ties, making even a correctly clamped count an
    advisory limit rather than a hard one. Both modifiers exist on SQL
    Server's `TOP` *and* on the ANSI `FETCH FIRST ... ROWS [WITH TIES]`
    syntax PostgreSQL and Oracle also support (sqlglot exposes both under
    the same `limit_options` arg regardless of which node — `Limit` or
    `Fetch` — carries it, so one check here covers every dialect). Both are
    rejected outright rather than silently stripped or rewritten, since
    either would change the query's semantics — and it's this function's
    job to enforce a row cap, not to reinterpret an author's SQL for them.
    """
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        logger.warning(f"Could not parse SQL to enforce row cap, returning unmodified: {e}")
        return sql

    parsed = _unwrap_single_statement(parsed)
    if parsed is None:
        return sql

    # PostgreSQL's `LIMIT ALL` means "no limit" — explicitly unbounded, not
    # merely absent. sqlglot's postgres dialect drops it from the AST
    # entirely (parsed.args["limit"] comes back None, indistinguishable from
    # no LIMIT clause at all), while other dialects parse it as a Limit node
    # wrapping a bare Column("ALL") (not a Literal, so the numeric-comparison
    # path below can't see it either way). Handle it before either of those
    # paths can either double-append a LIMIT or silently leave it unbounded.
    # TOP has no ALL equivalent, so this stays LIMIT-specific.
    limit_all_span = _find_limit_all_span(sql, dialect)
    if limit_all_span is not None:
        logger.info(f"Rewriting LIMIT ALL to row cap {cap}")
        start, end = limit_all_span
        return f"{sql[:start]}{cap}{sql[end:]}"

    existing_limit = parsed.args.get("limit")
    if existing_limit is None:
        if dialect == "tsql" and isinstance(parsed, exp.Union):
            # T-SQL has no syntax for a union-level row cap — TOP belongs to
            # a SELECT, not a set operation, so there's nowhere to inject one
            # that bounds the *combined* result. Injecting into just the
            # first arm (the naive approach) leaves every other arm
            # unbounded; injecting into every arm still doesn't cap the
            # union's total, only each arm's contribution to it. A query
            # that genuinely needs one should wrap the union in a subquery
            # with its own outer TOP, which parses as a plain Select and
            # hits the ordinary path above.
            raise QueryGuardError(
                "Rendered query is a UNION with no row cap and no dialect syntax exists to "
                "inject one that bounds the combined result; wrap it in a capped subquery."
            )
        return _inject_row_cap(sql, cap, dialect)

    limit_options = existing_limit.args.get("limit_options")
    if limit_options is not None:
        # "TOP" for a Limit node (SQL Server), "FETCH FIRST/NEXT" for a
        # Fetch node (PostgreSQL, Oracle, and SQL Server's own OFFSET/FETCH
        # form) — named accurately in the error rather than assuming TOP,
        # since PERCENT/WITH TIES are not SQL-Server-specific.
        clause_name = "FETCH" if isinstance(existing_limit, exp.Fetch) else "TOP"
        if limit_options.args.get("percent"):
            raise QueryGuardError(
                f"Rendered query uses {clause_name} ... PERCENT, which is not a bounded row "
                "count and cannot be safely capped."
            )
        if limit_options.args.get("with_ties"):
            raise QueryGuardError(
                f"Rendered query uses {clause_name} ... WITH TIES, which can return more rows "
                "than its count whenever the ORDER BY column has ties, and cannot be safely capped."
            )

    count_expr = _row_count_expression(existing_limit)
    if isinstance(count_expr, exp.Placeholder):
        # Bound placeholder (e.g. `LIMIT ?`, `TOP (?)`, `FETCH NEXT ?`) — its
        # value isn't known until bind time, so leave the text untouched;
        # clamp_bound_limit_parameter handles the resolved value separately.
        return sql

    try:
        limit_value = int(count_expr.this)
    except (AttributeError, TypeError, ValueError):
        # Some other, non-literal expression (e.g. `LIMIT 1 + 99999`,
        # `TOP (50000 * 2)`) — not a placeholder we can defer to bind-time
        # clamping, and not a literal we can compare to the cap. There is no
        # value here to safely evaluate without implementing a SQL
        # expression evaluator, so this is rejected outright rather than
        # treated as if it were a harmless bound placeholder.
        raise QueryGuardError(
            f"Rendered query's row-count clause is a computed expression "
            f"({type(count_expr).__name__}), not a literal or a bind placeholder, "
            "and cannot be safely capped."
        )

    if limit_value < 0:
        # SQLite treats a negative LIMIT (canonically -1) as "no limit at
        # all" rather than an error — the opposite of what a value <= cap
        # would suggest. Rejecting is the safe reading everywhere else too:
        # no dialect the guard needs to support assigns "clamp to 0 rows"
        # semantics to a negative row count.
        raise QueryGuardError(
            f"Rendered query's row-count clause is negative ({limit_value}); some dialects "
            "(e.g. SQLite's LIMIT -1) treat this as unbounded rather than a valid count."
        )

    if limit_value <= cap:
        return sql

    logger.info(f"Clamping row-count clause {limit_value} down to row cap {cap}")
    span = _find_outer_row_count_span(sql, dialect, limit_value)
    if span is None:
        logger.warning(
            f"Could not locate the outer LIMIT/TOP {limit_value} in the original SQL text "
            "to clamp it; returning unmodified."
        )
        return sql
    start, end = span
    return f"{sql[:start]}{cap}{sql[end:]}"


# A trailing statement terminator (`;`), optionally followed only by
# whitespace and/or trailing comments up to end of string — never anything
# that could be further SQL, since assert_single_statement already
# guarantees this is one statement, so nothing meaningful follows the `;`
# but comments/whitespace.
_TRAILING_TERMINATOR_RE = re.compile(r";\s*(?:--[^\n]*\n?\s*|/\*.*?\*/\s*)*$", re.DOTALL)


def _strip_trailing_terminator(sql: str) -> str:
    """
    Remove a terminal `;` before appending an injected row-count clause, even
    when comments or whitespace follow it (e.g. `SELECT ...; -- audit`).
    Rstrip-then-check-last-char alone misses this: the comment, not the
    semicolon, would be the last character, so the semicolon would be left
    in place — appending after it turns the injected clause into a second,
    invalid statement rather than part of the first query.
    """
    match = _TRAILING_TERMINATOR_RE.search(sql)
    if match:
        return sql[: match.start()].rstrip()
    return sql.rstrip()


def _inject_row_cap(sql: str, cap: int, dialect: Optional[str]) -> str:
    """
    Append `LIMIT {cap}` (most dialects), append `FETCH FIRST {cap} ROWS
    ONLY` (Oracle, which has no LIMIT keyword — this is Oracle's own ANSI
    row-limiting syntax, and unlike T-SQL's TOP, it correctly attaches to the
    outer query even across a UNION, so no special-casing is needed there),
    or inject `TOP ({cap})` right after the outer SELECT (SQL Server/tsql,
    which has neither LIMIT nor FETCH FIRST) when the query has no row-count
    clause. Falls back to `sql` unchanged, with a warning, if the outer
    SELECT can't be located for the TOP case — silently leaving a query
    genuinely uncapped would be worse than logging it.
    """
    if dialect == "oracle":
        # A newline, not a space, before the appended clause — the query may
        # end in a "--" line comment with no trailing newline of its own
        # (e.g. "SELECT * FROM sales -- audit"), and a line comment extends
        # to end-of-line, so appending on the same line would comment out the
        # injected clause and leave the query genuinely unbounded.
        return f"{_strip_trailing_terminator(sql)}\nFETCH FIRST {cap} ROWS ONLY"

    if dialect not in ("tsql",):
        return f"{_strip_trailing_terminator(sql)}\nLIMIT {cap}"

    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except Exception:
        return sql

    select_positions = _depth_zero_token_indices(tokens, TokenType.SELECT)
    if not select_positions:
        logger.warning("Could not locate the outer SELECT to inject TOP; returning unmodified.")
        return sql
    insert_after = select_positions[0]

    # Skip a DISTINCT/ALL modifier immediately after SELECT — TOP goes after it.
    if insert_after + 1 < len(tokens) and tokens[insert_after + 1].token_type in (
        TokenType.DISTINCT, TokenType.ALL,
    ):
        insert_after += 1

    insert_pos = tokens[insert_after].end + 1
    return f"{sql[:insert_pos]} TOP ({cap}){sql[insert_pos:]}"


def _depth_zero_token_indices(tokens, token_type) -> list:
    """Indices of `token_type` tokens that appear outside any parentheses —
    i.e. belonging to the outer statement, not a subquery or CTE definition."""
    depth = 0
    indices = []
    for i, token in enumerate(tokens):
        if token.token_type == TokenType.L_PAREN:
            depth += 1
        elif token.token_type == TokenType.R_PAREN:
            depth -= 1
        elif depth == 0 and token.token_type == token_type:
            indices.append(i)
    return indices


def _find_outer_row_count_token_indices(tokens) -> list:
    """
    Return the ordered list of token indices making up the outer query's
    row-count clause — the NUMBER/PLACEHOLDER tokens after LIMIT, TOP, or
    FETCH NEXT/FIRST — or [] if none of those clauses is present.

    LIMIT and FETCH are both always a SELECT's final clause, so the outer
    query's LIMIT/FETCH is the *last* such token outside any parentheses (a
    subquery/CTE's own copy must close its parentheses first). TOP is the
    opposite: it appears immediately after the outer SELECT keyword, so the
    outer query's TOP is the *first* TOP token outside any parentheses (a
    subquery's TOP, nested inside a later FROM clause or an earlier CTE
    definition, is always inside parens relative to the outer statement).

    Handles MySQL's `LIMIT offset, count` comma form (collects the full
    comma-joined run rather than stopping at the first number/placeholder),
    TOP's optional parenthesization (`TOP (n)` vs `TOP n`), and FETCH's
    `NEXT`/`FIRST` keyword between FETCH and the count. TOP and FETCH have no
    comma form — each is just a single count.
    """
    limit_positions = _depth_zero_token_indices(tokens, TokenType.LIMIT)
    if limit_positions:
        keyword_idx, allow_comma = limit_positions[-1], True
    else:
        top_positions = _depth_zero_token_indices(tokens, TokenType.TOP)
        if top_positions:
            keyword_idx, allow_comma = top_positions[0], False
            if keyword_idx + 1 < len(tokens) and tokens[keyword_idx + 1].token_type == TokenType.L_PAREN:
                keyword_idx += 1  # scan resumes right after the paren, at the same target token
        else:
            fetch_positions = _depth_zero_token_indices(tokens, TokenType.FETCH)
            if not fetch_positions:
                return []
            keyword_idx, allow_comma = fetch_positions[-1], False
            # FETCH is always followed by NEXT or FIRST, then the count.
            if keyword_idx + 1 < len(tokens) and tokens[keyword_idx + 1].token_type in (
                TokenType.NEXT, TokenType.FIRST,
            ):
                keyword_idx += 1

    indices = []
    i = keyword_idx + 1
    while i < len(tokens) and tokens[i].token_type in (TokenType.NUMBER, TokenType.PLACEHOLDER):
        indices.append(i)
        i += 1
        if allow_comma and i < len(tokens) and tokens[i].token_type == TokenType.COMMA:
            i += 1
            continue
        break

    return indices


def _find_outer_row_count_span(sql: str, dialect: Optional[str], limit_value: int):
    """
    Find the char span of the row-*count* NUMBER token belonging to the
    outer query's LIMIT or TOP clause, using sqlglot's tokenizer (not a text
    regex) so string literals and comments containing "LIMIT <n>" can't be
    mistaken for it, and a subquery's own clause can't be mistaken for the
    outer one.

    Within a LIMIT clause the row count isn't always the first number:
    MySQL's `LIMIT offset, count` form (as opposed to standard `LIMIT count`
    or `LIMIT count OFFSET offset`) puts the offset first and the count
    second — sqlglot's parsed AST already resolves this correctly
    (`limit_value` here is read from `existing_limit.expression`, the count),
    so the last NUMBER in the comma-joined run is used, which is the count in
    both the single- and two-number forms. TOP has only ever one number.

    Returns None if no LIMIT/TOP clause with a matching count is found.
    """
    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except Exception:
        return None

    indices = _find_outer_row_count_token_indices(tokens)
    number_indices = [i for i in indices if tokens[i].token_type == TokenType.NUMBER]
    if not number_indices:
        return None

    count_token = tokens[number_indices[-1]]
    try:
        if int(count_token.text) != limit_value:
            return None
    except ValueError:
        return None

    return count_token.start, count_token.end + 1


def _find_limit_all_span(sql: str, dialect: Optional[str]):
    """
    Find the char span of a bare `ALL` immediately following the outer
    query's LIMIT keyword — PostgreSQL's `LIMIT ALL`, meaning explicitly
    unbounded. TOP has no ALL equivalent, so this stays LIMIT-specific. Uses
    the same "last depth-0 LIMIT token is the outer one" rule as
    `_find_outer_row_count_token_indices`. Returns None if the outer LIMIT
    (if any) isn't followed by `ALL`.
    """
    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except Exception:
        return None

    limit_positions = _depth_zero_token_indices(tokens, TokenType.LIMIT)
    if not limit_positions:
        return None
    limit_idx = limit_positions[-1]

    if limit_idx + 1 >= len(tokens):
        return None
    next_token = tokens[limit_idx + 1]
    if next_token.text.upper() == "ALL":
        return next_token.start, next_token.end + 1
    return None


def find_outer_limit_bind_name(sql: str, dialect: Optional[str] = None) -> Optional[str]:
    """
    If the outer query's LIMIT count is bound to a *named* placeholder
    (`:name` or `%(name)s`), return that name.

    `enforce_row_cap` only ever sees the rendered SQL text with placeholders
    still unresolved — it cannot itself clamp a value that isn't in the SQL
    at all. This is the lookup `clamp_bound_limit_parameter` uses to find
    which resolved bind value actually needs clamping.

    Returns None for a positional `?` placeholder (see
    `find_outer_limit_positional_index`), a literal LIMIT, `LIMIT ALL`, or no
    LIMIT.
    """
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return None

    if not isinstance(parsed, (exp.Select, exp.Union)):
        return None

    existing_limit = parsed.args.get("limit")
    if existing_limit is None:
        return None

    placeholder = _row_count_expression(existing_limit)
    if not isinstance(placeholder, exp.Placeholder):
        return None

    this = placeholder.this
    if this is None:
        return None  # positional `?` — no name to resolve
    if isinstance(this, exp.Identifier):
        return this.this
    return str(this)


def find_outer_limit_positional_index(sql: str, dialect: Optional[str] = None) -> Optional[int]:
    """
    If the outer query's row-count clause (LIMIT or SQL Server's TOP) is
    bound to a positional `?` placeholder, return its 0-based index among
    *all* `?` placeholders in the query — the same left-to-right ordering
    `_execute_template` already relies on to build its positional bind tuple.

    Handles MySQL's `LIMIT offset, count` form the same way
    `_find_outer_row_count_span` does for the numeric case: when both slots
    are positional (`LIMIT ?, ?`), the offset placeholder comes first and the
    count placeholder second, so this takes the *last* placeholder in the
    comma-joined run rather than assuming it's the first (and only) one. Also
    handles TOP's optional parenthesization (`TOP (?)` vs a bare `TOP ?`,
    the latter of which T-SQL doesn't actually accept, but the tokenizer
    handles either way).

    Returns None if the outer clause isn't a positional placeholder.
    """
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return None

    existing_limit = parsed.args.get("limit")
    if existing_limit is None:
        return None
    placeholder = _row_count_expression(existing_limit)
    if not isinstance(placeholder, exp.Placeholder):
        return None
    if placeholder.this is not None:
        return None  # named, not positional

    try:
        tokens = sqlglot.tokenize(sql, read=dialect)
    except Exception:
        return None

    indices = _find_outer_row_count_token_indices(tokens)
    placeholder_indices = [i for i in indices if tokens[i].token_type == TokenType.PLACEHOLDER]
    if not placeholder_indices:
        return None
    target_idx = placeholder_indices[-1]

    ordinal = -1
    for i, token in enumerate(tokens):
        if token.token_type == TokenType.PLACEHOLDER:
            ordinal += 1
            if i == target_idx:
                return ordinal

    return None


def _coerce_row_count_value(value) -> Optional[int]:
    """
    Coerce a resolved bind value into an int for comparison against the row
    cap, handling the shapes parameter extraction and database drivers
    actually hand this function: an int already, a `decimal.Decimal` (a
    common numeric type for parameters sourced from a database or an ORM,
    and one several drivers accept or coerce directly in a row-count bind
    position), or a numeric string (e.g. `"99999"`) — LLM- or regex-based
    extraction routinely produces strings before any type coercion happens.
    Left as any of these, a value would silently execute uncapped even
    though it's a perfectly clampable number.

    Returns None for anything that isn't a finite, whole number (`bool`,
    non-numeric strings, `NaN`/`inf`, a fractional float or `Decimal`) —
    there is nothing safe to clamp, so the value is left exactly as given
    rather than guessed at or rejected; a non-numeric value bound to a
    row-count slot will fail at the database driver on its own.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            return None
        return int(value)
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            return None
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return int(stripped)
        except ValueError:
            pass
        try:
            as_float = float(stripped)
        except ValueError:
            return None
        if not math.isfinite(as_float) or as_float != int(as_float):
            return None
        return int(as_float)
    return None


def clamp_bound_limit_parameter(
    sql: str,
    parameters: dict,
    cap: int,
    dialect: Optional[str] = None,
    positional_param_names: Optional[list] = None,
) -> bool:
    """
    Mutate `parameters` in place, clamping the value bound to the outer
    query's LIMIT clause down to `cap` if it exceeds it.

    Returns True if a value was actually clamped, False otherwise (no bound
    LIMIT found, value already within cap, or the positional case that can't
    be resolved to a name) — callers use this to distinguish a bound-LIMIT
    clamp from `enforce_row_cap`'s literal-text clamp/injection for metrics.

    `enforce_row_cap` intentionally leaves a bound LIMIT's *text* unchanged —
    the actual value isn't in the SQL to compare against the cap, it's in
    `parameters`, already resolved before the guard runs. Left unhandled, a
    template with `LIMIT :limit` (or any other bound form) executes with
    whatever value parameter extraction produced, uncapped, regardless of
    `query_guard_max_rows`.

    For a named placeholder (`:limit`, `%(limit)s`) the parameter is looked up
    directly by name. For a positional `?` placeholder, `positional_param_names`
    must be the ordered parameter names the caller will bind positionally
    (same order `_execute_template` already assumes for `?` elsewhere); without
    it, a positional bound LIMIT can't be resolved to a name and is left
    unclamped (logged as a warning — this is the one case the row cap cannot
    currently enforce).
    """
    name = find_outer_limit_bind_name(sql, dialect)
    if name is not None:
        value = _coerce_row_count_value(parameters.get(name))
        _reject_if_negative_row_count(value, name)
        if value is not None and value > cap:
            logger.info(f"Clamping bound LIMIT parameter '{name}' from {value} to row cap {cap}")
            parameters[name] = cap
            return True
        return False

    index = find_outer_limit_positional_index(sql, dialect)
    if index is None:
        return False

    if not positional_param_names or index >= len(positional_param_names):
        logger.warning(
            "Outer LIMIT is bound to a positional placeholder but its parameter name "
            "could not be resolved from the template's parameter list; row cap cannot "
            "be enforced on this value."
        )
        return False

    param_name = positional_param_names[index]
    value = _coerce_row_count_value(parameters.get(param_name))
    _reject_if_negative_row_count(value, param_name)
    if value is not None and value > cap:
        logger.info(f"Clamping bound LIMIT parameter '{param_name}' (positional) from {value} to row cap {cap}")
        parameters[param_name] = cap
        return True
    return False


def _reject_if_negative_row_count(value: Optional[int], param_name: str) -> None:
    """Raise QueryGuardError if a resolved bound row-count value is negative.

    Mirrors the literal-value check in `enforce_row_cap`: some dialects (e.g.
    SQLite's `LIMIT -1`) treat a negative row count as "unbounded" rather
    than a valid, small count, so a naive `value > cap` comparison would let
    it through as if it were safely within the cap.
    """
    if value is not None and value < 0:
        raise QueryGuardError(
            f"Bound LIMIT parameter '{param_name}' resolved to a negative value ({value}); "
            "some dialects (e.g. SQLite's LIMIT -1) treat this as unbounded rather than a "
            "valid count."
        )
