"""
Intent retriever implementation for SQL datasources
"""

from .intent_postgresql_retriever import IntentPostgreSQLRetriever
from .domain.extraction import DomainParameterExtractor
from .domain.response import DomainResponseGenerator
from .template_reranker import TemplateReranker
from .domain import DomainConfig

# Conditionally import MySQL retriever only if mysql.connector is available
try:
    from .intent_mysql_retriever import IntentMySQLRetriever
    _mysql_available = True
except ImportError:
    _mysql_available = False

__all__ = [
    'IntentPostgreSQLRetriever',
    'DomainParameterExtractor',
    'DomainResponseGenerator',
    'TemplateReranker',
    'DomainConfig'
]

# Add MySQL retriever to __all__ only if available
if _mysql_available:
    __all__.append('IntentMySQLRetriever')