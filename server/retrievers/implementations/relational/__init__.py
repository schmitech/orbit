"""Relational database retriever implementations."""

import logging

from .sqlite_retriever import SQLiteRetriever

logger = logging.getLogger(__name__)

try:  # Optional dependency: psycopg2
    from .postgresql_retriever import PostgreSQLRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    PostgreSQLRetriever = None
    logger.debug("psycopg2 not installed; PostgreSQLRetriever unavailable")

try:  # Optional dependency: mysqlclient or mysql-connector
    from .mysql_retriever import MySQLRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    MySQLRetriever = None
    logger.debug("MySQL client libraries not installed; MySQLRetriever unavailable")

__all__ = [
    'SQLiteRetriever',
]

if PostgreSQLRetriever is not None:
    __all__.append('PostgreSQLRetriever')

if MySQLRetriever is not None:
    __all__.append('MySQLRetriever')
