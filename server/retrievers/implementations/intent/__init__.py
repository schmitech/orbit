"""Intent retriever implementation for SQL datasources."""

import logging

from .domain.extraction import DomainParameterExtractor
from .domain.response import DomainResponseGenerator
from .template_reranker import TemplateReranker
from .domain import DomainConfig

logger = logging.getLogger(__name__)

try:  # Optional dependency on psycopg2
    from .intent_postgresql_retriever import IntentPostgreSQLRetriever
except ModuleNotFoundError:  # pragma: no cover - optional import guard
    IntentPostgreSQLRetriever = None
    logger.debug("psycopg2 not installed; IntentPostgreSQLRetriever unavailable")

# Conditionally import MySQL retriever only if mysql.connector is available
try:
    from .intent_mysql_retriever import IntentMySQLRetriever
    _mysql_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentMySQLRetriever = None
    _mysql_available = False
    logger.debug("MySQL client libraries not installed; IntentMySQLRetriever unavailable")

# Import SQLite retriever (sqlite3 is built-in to Python)
try:
    from .intent_sqlite_retriever import IntentSQLiteRetriever
    _sqlite_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentSQLiteRetriever = None
    _sqlite_available = False
    logger.debug("SQLite retriever import failed; IntentSQLiteRetriever unavailable")

# Import DuckDB retriever (requires duckdb package)
try:
    from .intent_duckdb_retriever import IntentDuckDBRetriever
    _duckdb_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentDuckDBRetriever = None
    _duckdb_available = False
    logger.debug("duckdb not installed; IntentDuckDBRetriever unavailable")

# Import Elasticsearch retriever (requires elasticsearch package)
try:
    from .intent_elasticsearch_retriever import IntentElasticsearchRetriever
    _elasticsearch_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentElasticsearchRetriever = None
    _elasticsearch_available = False
    logger.debug("Elasticsearch client libraries not installed; IntentElasticsearchRetriever unavailable")

# Import HTTP JSON retriever (requires httpx package)
try:
    from .intent_http_json_retriever import IntentHTTPJSONRetriever
    _http_json_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentHTTPJSONRetriever = None
    _http_json_available = False
    logger.debug("HTTP client libraries not installed; IntentHTTPJSONRetriever unavailable")

# Import Firecrawl retriever (requires httpx package)
try:
    from .intent_firecrawl_retriever import IntentFirecrawlRetriever
    _firecrawl_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentFirecrawlRetriever = None
    _firecrawl_available = False
    logger.debug("HTTP client libraries not installed; IntentFirecrawlRetriever unavailable")

# Import GraphQL retriever (requires httpx package)
try:
    from .intent_graphql_retriever import IntentGraphQLRetriever
    _graphql_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentGraphQLRetriever = None
    _graphql_available = False
    logger.debug("HTTP client libraries not installed; IntentGraphQLRetriever unavailable")

# Import Agent retriever (requires httpx package)
try:
    from .intent_agent_retriever import IntentAgentRetriever
    _agent_available = True
except ImportError:  # pragma: no cover - optional import guard
    IntentAgentRetriever = None
    _agent_available = False
    logger.debug("Agent retriever import failed; IntentAgentRetriever unavailable")

__all__ = [
    'DomainParameterExtractor',
    'DomainResponseGenerator',
    'TemplateReranker',
    'DomainConfig'
]

if IntentPostgreSQLRetriever is not None:
    __all__.append('IntentPostgreSQLRetriever')

if _mysql_available and IntentMySQLRetriever is not None:
    __all__.append('IntentMySQLRetriever')

if _sqlite_available and IntentSQLiteRetriever is not None:
    __all__.append('IntentSQLiteRetriever')

if _duckdb_available and IntentDuckDBRetriever is not None:
    __all__.append('IntentDuckDBRetriever')

if _elasticsearch_available and IntentElasticsearchRetriever is not None:
    __all__.append('IntentElasticsearchRetriever')

if _http_json_available and IntentHTTPJSONRetriever is not None:
    __all__.append('IntentHTTPJSONRetriever')

if _firecrawl_available and IntentFirecrawlRetriever is not None:
    __all__.append('IntentFirecrawlRetriever')

if _graphql_available and IntentGraphQLRetriever is not None:
    __all__.append('IntentGraphQLRetriever')

if _agent_available and IntentAgentRetriever is not None:
    __all__.append('IntentAgentRetriever')
