"""
Unit tests for the new reranker architecture integration.

Tests cover:
- Reranker service manager singleton pattern
- Document reranking pipeline step
- Service registration
- Adapter-level reranker override support
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import modules to test
import sys
import os
from pathlib import Path

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

from services.reranker_service_manager import RerankingServiceManager
from inference.pipeline.steps.document_reranking import DocumentRerankingStep
from inference.pipeline.service_container import ServiceContainer
from inference.pipeline.base import ProcessingContext
from ai_services.base import ServiceType
from ai_services.factory import AIServiceFactory


class TestRerankingServiceManager:
    """Tests for RerankingServiceManager singleton factory."""

    def setup_method(self):
        """Clear cache and register services before each test."""
        RerankingServiceManager.clear_cache()
        # Register AI services before testing
        from ai_services.registry import register_all_services
        register_all_services()

    def test_singleton_pattern(self):
        """Test that the same instance is returned for identical configs."""
        config = {
            'reranker': {'provider': 'ollama'},
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'test-model'
                }
            }
        }

        # Create two instances with same config
        instance1 = RerankingServiceManager.create_reranker_service(config, 'ollama')
        instance2 = RerankingServiceManager.create_reranker_service(config, 'ollama')

        # Should be the same instance (singleton)
        assert instance1 is instance2

    def test_cache_key_creation(self):
        """Test that cache keys are created correctly."""
        config = {
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'test-model'
                }
            }
        }

        cache_key = RerankingServiceManager._create_cache_key('ollama', config)
        assert 'ollama' in cache_key
        assert 'http://localhost:11434' in cache_key
        assert 'test-model' in cache_key

    def test_different_configs_create_different_instances(self):
        """Test that different configs create different instances."""
        config1 = {
            'reranker': {'provider': 'ollama'},
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'model1'
                }
            }
        }

        config2 = {
            'reranker': {'provider': 'ollama'},
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'model2'
                }
            }
        }

        instance1 = RerankingServiceManager.create_reranker_service(config1, 'ollama')
        instance2 = RerankingServiceManager.create_reranker_service(config2, 'ollama')

        # Should be different instances (different models)
        assert instance1 is not instance2

    def test_clear_cache(self):
        """Test that cache clearing works."""
        config = {
            'reranker': {'provider': 'ollama'},
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'test-model'
                }
            }
        }

        instance1 = RerankingServiceManager.create_reranker_service(config, 'ollama')
        RerankingServiceManager.clear_cache()
        instance2 = RerankingServiceManager.create_reranker_service(config, 'ollama')

        # Should be different instances after cache clear
        assert instance1 is not instance2


class TestDocumentRerankingStep:
    """Tests for DocumentRerankingStep pipeline step."""

    def setup_method(self):
        """Setup common test fixtures."""
        self.config = {
            'reranker': {'enabled': True, 'provider': 'ollama'},
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'test-model',
                    'top_n': 5
                }
            }
        }
        self.container = ServiceContainer()
        self.container.register_singleton('config', self.config)

    def test_step_creation(self):
        """Test that the step can be created."""
        step = DocumentRerankingStep(self.container)
        assert step.get_name() == 'DocumentRerankingStep'

    def test_should_execute_no_documents(self):
        """Test that step skips when no documents are present."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})
        context.retrieved_docs = []

        assert step.should_execute(context) is False

    def test_should_execute_with_documents_reranker_disabled(self):
        """Test that step skips when reranker is disabled."""
        config = self.config.copy()
        config['reranker']['enabled'] = False
        self.container.register_singleton('config', config)

        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})
        context.retrieved_docs = [{'content': 'test doc'}]

        assert step.should_execute(context) is False

    def test_should_execute_with_documents_reranker_enabled(self):
        """Test that step executes when documents present and reranker enabled."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})
        context.retrieved_docs = [{'content': 'test doc'}]

        # Mock adapter_manager
        mock_adapter_manager = Mock()
        mock_adapter_manager.get_adapter_config.return_value = {}
        self.container.register_singleton('adapter_manager', mock_adapter_manager)

        assert step.should_execute(context) is True

    def test_should_execute_blocked_context(self):
        """Test that step skips when context is blocked."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})
        context.retrieved_docs = [{'content': 'test doc'}]
        context.is_blocked = True

        assert step.should_execute(context) is False

    def test_extract_document_texts(self):
        """Test document text extraction from various formats."""
        step = DocumentRerankingStep(self.container)

        docs = [
            {'content': 'text1'},
            {'text': 'text2'},
            {'page_content': 'text3'},
            {'content': 'text4', 'metadata': {}}
        ]

        texts = step._extract_document_texts(docs)
        assert texts == ['text1', 'text2', 'text3', 'text4']

    def test_get_top_n_config_from_adapter(self):
        """Test getting top_n from adapter config."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})

        # Mock adapter_manager with top_n in config
        mock_adapter_manager = Mock()
        mock_adapter_manager.get_adapter_config.return_value = {
            'config': {'reranker_top_n': 3}
        }
        self.container.register_singleton('adapter_manager', mock_adapter_manager)

        top_n = step._get_top_n_config(context)
        assert top_n == 3

    def test_get_top_n_config_from_global(self):
        """Test getting top_n from global config."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})

        # No adapter manager, should fall back to global
        top_n = step._get_top_n_config(context)
        assert top_n == 5  # From self.config

    def test_apply_reranking_results(self):
        """Test applying reranking results to original documents."""
        step = DocumentRerankingStep(self.container)

        original_docs = [
            {'content': 'doc1', 'metadata': {'source': 'src1'}},
            {'content': 'doc2', 'metadata': {'source': 'src2'}},
            {'content': 'doc3', 'metadata': {'source': 'src3'}}
        ]

        reranked_results = [
            {'index': 2, 'score': 0.9},  # doc3
            {'index': 0, 'score': 0.7},  # doc1
            {'index': 1, 'score': 0.5}   # doc2
        ]

        reranked_docs = step._apply_reranking_results(original_docs, reranked_results)

        assert len(reranked_docs) == 3
        assert reranked_docs[0]['content'] == 'doc3'
        assert reranked_docs[0]['relevance'] == 0.9
        assert reranked_docs[0]['reranked'] is True
        assert reranked_docs[1]['content'] == 'doc1'
        assert reranked_docs[1]['relevance'] == 0.7

    def test_format_context(self):
        """Test formatting reranked documents into context string."""
        step = DocumentRerankingStep(self.container)

        docs = [
            {
                'content': 'content1',
                'metadata': {'source': 'source1'},
                'relevance': 0.9
            },
            {
                'content': 'content2',
                'metadata': {'source': 'source2'},
                'relevance': 0.7
            }
        ]

        context = step._format_context(docs)

        assert 'source1' in context
        assert 'source2' in context
        assert 'content1' in context
        assert 'content2' in context
        assert '0.90' in context  # relevance score
        assert '0.70' in context

    @pytest.mark.asyncio
    async def test_process_graceful_degradation(self):
        """Test that errors in reranking don't break the pipeline."""
        step = DocumentRerankingStep(self.container)
        context = ProcessingContext('test query', 'test-adapter', {})
        context.retrieved_docs = [{'content': 'test doc'}]

        # Mock reranker service that raises an error
        mock_reranker = AsyncMock()
        mock_reranker.rerank.side_effect = Exception('Reranker failed')
        self.container.register_singleton('reranker_service', mock_reranker)

        # Mock adapter_manager
        mock_adapter_manager = Mock()
        mock_adapter_manager.get_adapter_config.return_value = {}
        self.container.register_singleton('adapter_manager', mock_adapter_manager)

        # Process should not raise, just log and continue
        result_context = await step.process(context)

        # Context should be returned unchanged (original docs preserved)
        assert result_context.retrieved_docs == [{'content': 'test doc'}]
        assert not result_context.has_error()


class TestServiceRegistration:
    """Tests for reranking service registration."""

    def test_ollama_reranking_service_registered(self):
        """Test that OllamaRerankingService is registered."""
        from ai_services.registry import register_all_services

        register_all_services()

        assert AIServiceFactory.is_service_registered(
            ServiceType.RERANKING,
            'ollama'
        )

    def test_reranking_services_in_available_list(self):
        """Test that reranking appears in available services."""
        from ai_services.registry import register_all_services

        register_all_services()

        available = AIServiceFactory.list_available_services()
        assert 'reranking' in available
        assert 'ollama' in available['reranking']


class TestDynamicAdapterManagerIntegration:
    """Tests for dynamic adapter manager reranker support."""

    def test_adapter_manager_has_reranker_method(self):
        """Test that DynamicAdapterManager has get_overridden_reranker method."""
        from services.dynamic_adapter_manager import DynamicAdapterManager

        assert hasattr(DynamicAdapterManager, 'get_overridden_reranker')

    def test_adapter_manager_has_reranker_cache(self):
        """Test that DynamicAdapterManager has reranker cache."""
        from services.dynamic_adapter_manager import DynamicAdapterManager

        config = {'adapters': []}
        manager = DynamicAdapterManager(config)

        # Check that reranker_cache manager exists
        assert hasattr(manager, 'reranker_cache')
        assert manager.reranker_cache is not None
        
        # Check that the cache manager has the expected attributes
        assert hasattr(manager.reranker_cache, '_cache')
        assert hasattr(manager.reranker_cache, '_cache_lock')
        assert hasattr(manager.reranker_cache, '_initializing')
        
        # Check backward compatibility property
        assert hasattr(manager, '_reranker_cache')

    def test_get_overridden_reranker_exception_handling(self):
        """Test that get_overridden_reranker handles missing provider gracefully."""
        from services.dynamic_adapter_manager import DynamicAdapterManager

        config = {
            'adapters': [],
            'rerankers': {
                'ollama': {
                    'base_url': 'http://localhost:11434',
                    'model': 'test-model'
                }
            }
        }

        manager = DynamicAdapterManager(config)

        # Should raise ValueError for empty provider
        with pytest.raises(ValueError, match="Reranker provider name cannot be empty"):
            asyncio.run(manager.get_overridden_reranker('', 'test-adapter'))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
