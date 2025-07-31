"""
Test to validate that all intent components can be imported correctly
"""

import pytest
import sys
import os

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


def test_intent_adapter_import():
    """Test that IntentAdapter can be imported"""
    from retrievers.adapters.intent.intent_adapter import IntentAdapter
    assert IntentAdapter is not None


def test_intent_retriever_import():
    """Test that IntentPostgreSQLRetriever can be imported"""
    from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
    assert IntentPostgreSQLRetriever is not None


def test_domain_aware_extractor_import():
    """Test that DomainAwareParameterExtractor can be imported"""
    from retrievers.implementations.intent.domain_aware_extractor import DomainAwareParameterExtractor
    assert DomainAwareParameterExtractor is not None


def test_domain_aware_response_generator_import():
    """Test that DomainAwareResponseGenerator can be imported"""
    from retrievers.implementations.intent.domain_aware_response_generator import DomainAwareResponseGenerator
    assert DomainAwareResponseGenerator is not None


def test_template_reranker_import():
    """Test that TemplateReranker can be imported"""
    from retrievers.implementations.intent.template_reranker import TemplateReranker
    assert TemplateReranker is not None


def test_plugin_system_import():
    """Test that plugin system components can be imported"""
    from retrievers.implementations.intent.intent_plugin_system import (
        IntentPluginManager, QueryNormalizationPlugin, ResultEnrichmentPlugin
    )
    assert IntentPluginManager is not None
    assert QueryNormalizationPlugin is not None
    assert ResultEnrichmentPlugin is not None


def test_intent_package_import():
    """Test that the intent package can be imported as a whole"""
    from retrievers.implementations.intent import (
        IntentPostgreSQLRetriever,
        DomainAwareParameterExtractor,
        DomainAwareResponseGenerator,
        TemplateReranker
    )
    assert IntentPostgreSQLRetriever is not None
    assert DomainAwareParameterExtractor is not None
    assert DomainAwareResponseGenerator is not None
    assert TemplateReranker is not None


def test_intent_retriever_instantiation():
    """Test that IntentPostgreSQLRetriever can be instantiated"""
    from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
    
    config = {
        'datasources': {
            'postgresql': {
                'host': 'localhost',
                'port': 5432,
                'database': 'test'
            }
        },
        'config': {
            'template_collection_name': 'test_templates',
            'confidence_threshold': 0.75
        }
    }
    
    # This should not raise any import or syntax errors
    retriever = IntentPostgreSQLRetriever(config=config)
    assert retriever is not None
    assert retriever.template_collection_name == 'test_templates'
    assert retriever.confidence_threshold == 0.75


if __name__ == "__main__":
    pytest.main([__file__, "-v"])