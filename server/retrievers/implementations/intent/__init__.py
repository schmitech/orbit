"""
Intent retriever implementation for SQL datasources
"""

from .intent_postgresql_retriever import IntentPostgreSQLRetriever
from .domain_aware_extractor import DomainAwareParameterExtractor
from .domain_aware_response_generator import DomainAwareResponseGenerator
from .template_reranker import TemplateReranker

# Conditionally import MySQL retriever only if mysql.connector is available
try:
    from .intent_mysql_retriever import IntentMySQLRetriever
    _mysql_available = True
except ImportError:
    _mysql_available = False

__all__ = [
    'IntentPostgreSQLRetriever',
    'DomainAwareParameterExtractor', 
    'DomainAwareResponseGenerator',
    'TemplateReranker'
]

# Add MySQL retriever to __all__ only if available
if _mysql_available:
    __all__.append('IntentMySQLRetriever')