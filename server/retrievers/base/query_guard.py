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
from typing import Optional

import sqlglot
from sqlglot import exp

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


def enforce_row_cap(sql: str, cap: int, dialect: Optional[str] = None) -> str:
    """
    Ensure the outer query has a LIMIT no greater than `cap`, injecting one if
    absent or clamping it if larger. A LIMIT bound to a placeholder (e.g. `?`,
    `%(limit)s`) is left alone — its actual value isn't known until bind time,
    so it can't be safely compared to the cap here.

    Falls back to returning `sql` unchanged (logging a warning) if it can't be
    parsed, since failing open on a parse error is safer for availability than
    blocking every query a dialect quirk trips up; `assert_single_statement`/
    `assert_read_only` are the hard gates.
    """
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:
        logger.warning(f"Could not parse SQL to enforce row cap, returning unmodified: {e}")
        return sql

    if not isinstance(parsed, (exp.Select, exp.Union)):
        return sql

    existing_limit = parsed.args.get("limit")
    if existing_limit is None:
        parsed.set("limit", exp.Limit(expression=exp.Literal.number(cap)))
    else:
        try:
            limit_value = int(existing_limit.expression.this)
        except (AttributeError, TypeError, ValueError):
            limit_value = None
        if limit_value is not None and limit_value > cap:
            logger.info(f"Clamping LIMIT {limit_value} down to row cap {cap}")
            parsed.set("limit", exp.Limit(expression=exp.Literal.number(cap)))

    return parsed.sql(dialect=dialect)
