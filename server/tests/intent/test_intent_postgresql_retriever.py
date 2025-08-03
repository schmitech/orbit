"""
Tests for the IntentPostgreSQLRetriever class
"""

import pytest
import asyncio
import sys
import os
import json
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock, AsyncMock, Mock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
from retrievers.adapters.intent.intent_adapter import IntentAdapter
from retrievers.implementations.intent.domain_aware_extractor import DomainAwareParameterExtractor
from retrievers.implementations.intent.domain_aware_response_generator import DomainAwareResponseGenerator
from retrievers.implementations.intent.template_reranker import TemplateReranker


class TestIntentPostgreSQLRetriever:
    """Test suite for IntentPostgreSQLRetriever"""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing"""
        return {
            'datasources': {
                'postgres': {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'testdb',
                    'username': 'test',
                    'password': 'test'
                }
            },
            'config': {
                'domain_config_path': 'test_domain.yaml',
                'template_library_path': 'test_templates.yaml',
                'template_collection_name': 'test_templates',
                'confidence_threshold': 0.75,
                'max_templates': 5,
                'embedding_provider': None
            },
            'verbose': True
        }
    
    @pytest.fixture
    def mock_adapter(self):
        """Mock IntentAdapter for testing"""
        adapter = MagicMock(spec=IntentAdapter)
        adapter.get_all_templates.return_value = [
            {
                'id': 'find_customer',
                'description': 'Find customer by ID',
                'nl_examples': ['Show customer 123'],
                'tags': ['customer', 'find'],
                'parameters': [
                    {
                        'name': 'customer_id',
                        'type': 'integer',
                        'description': 'Customer ID',
                        'required': True
                    }
                ],
                'sql_template': 'SELECT * FROM customers WHERE id = %(customer_id)s'
            }
        ]
        adapter.get_template_by_id.return_value = adapter.get_all_templates()[0]
        adapter.format_document.return_value = {
            'content': 'Formatted result',
            'metadata': {},
            'result_count': 1
        }
        return adapter
    
    @pytest.fixture
    def mock_embedding_client(self):
        """Mock embedding client"""
        client = AsyncMock()
        client.embed_query = AsyncMock(return_value=[0.1] * 768)  # Mock 768-dim embedding
        return client
    
    @pytest.fixture
    def mock_inference_client(self):
        """Mock inference client"""
        client = AsyncMock()
        client.generate = AsyncMock(return_value='{"customer_id": 123}')
        return client
    
    @pytest.fixture
    def mock_chroma_collection(self):
        """Mock ChromaDB collection"""
        collection = MagicMock()
        collection.add = MagicMock()
        collection.delete = MagicMock()
        collection.get = MagicMock(return_value={'ids': []})
        collection.query = MagicMock(return_value={
            'ids': [['find_customer']],
            'distances': [[0.2]],  # Distance = 0.2, similarity = 0.8
            'documents': [['Find customer by ID']],
            'metadatas': [[{'template_id': 'find_customer'}]]
        })
        return collection
    
    @pytest.fixture
    async def retriever(self, mock_config, mock_adapter):
        """Create retriever instance with mocks"""
        retriever = IntentPostgreSQLRetriever(
            config=mock_config,
            domain_adapter=mock_adapter
        )
        
        # Mock the abstract methods from BaseRetriever
        retriever._tokenize_text = MagicMock(return_value=['customer', '123'])
        retriever._calculate_similarity = MagicMock(return_value=0.8)
        
        return retriever
    
    @pytest.mark.asyncio
    async def test_initialization(self, retriever, mock_config):
        """Test retriever initialization"""
        assert retriever.template_collection_name == 'test_templates'
        assert retriever.confidence_threshold == 0.75
        assert retriever.max_templates == 5
        assert retriever.embedding_client is None  # Not initialized yet
        assert retriever.inference_client is None  # Not initialized yet
    
    @pytest.mark.asyncio
    async def test_initialize_services(self, retriever, mock_embedding_client, mock_inference_client, mock_chroma_collection):
        """Test service initialization"""
        with patch('embeddings.base.EmbeddingServiceFactory') as mock_embed_factory:
            with patch('inference.pipeline.providers.provider_factory.ProviderFactory') as mock_inf_factory:
                with patch('chromadb.Client') as mock_chroma_client:
                    with patch.object(retriever, 'create_connection') as mock_conn_create:
                        # Setup mocks
                        mock_embed_factory.create_embedding_service.return_value = mock_embedding_client
                        mock_inf_factory.create_provider.return_value = mock_inference_client
                        mock_conn_create.return_value = MagicMock()  # Mock connection
                        
                        mock_chroma = MagicMock()
                        mock_chroma.get_or_create_collection.return_value = mock_chroma_collection
                        mock_chroma_client.return_value = mock_chroma
                        
                        # Initialize
                        await retriever.initialize()
                        
                        # Verify services initialized
                        assert retriever.embedding_client == mock_embedding_client
                        assert retriever.inference_client == mock_inference_client
                        assert retriever.template_collection == mock_chroma_collection
    
    @pytest.mark.asyncio
    async def test_create_embedding_text(self, retriever):
        """Test embedding text creation from template"""
        template = {
            'description': 'Find customer by ID',
            'nl_examples': ['Show customer 123', 'Get customer 456'],
            'tags': ['customer', 'find', 'id'],
            'parameters': [
                {'name': 'customer_id'},
                {'name': 'order_date'}
            ],
            'semantic_tags': {
                'action': 'find',
                'primary_entity': 'customer',
                'secondary_entity': 'order',
                'qualifiers': ['recent', 'by_id']
            }
        }
        
        embedding_text = retriever._create_embedding_text(template)
        
        # Check all components are included
        assert 'Find customer by ID' in embedding_text
        assert 'Show customer 123' in embedding_text
        assert 'Get customer 456' in embedding_text
        assert 'customer' in embedding_text
        assert 'find' in embedding_text
        assert 'customer id' in embedding_text  # Parameter with underscore replaced
        assert 'order date' in embedding_text
        assert 'recent' in embedding_text
        assert 'by_id' in embedding_text
    
    @pytest.mark.asyncio
    async def test_find_best_templates(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test finding best matching templates"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        
        templates = await retriever._find_best_templates("Show me customer 123")
        
        assert len(templates) == 1
        assert templates[0]['template']['id'] == 'find_customer'
        assert templates[0]['similarity'] == 0.8  # 1 - 0.2 distance
        
        # Verify embedding was created
        mock_embedding_client.embed_query.assert_called_once_with("Show me customer 123")
        
        # Verify ChromaDB query
        mock_chroma_collection.query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_parameters(self, retriever, mock_inference_client):
        """Test parameter extraction using LLM"""
        retriever.inference_client = mock_inference_client
        
        template = {
            'parameters': [
                {
                    'name': 'customer_id',
                    'type': 'integer',
                    'description': 'Customer ID',
                    'example': 123
                },
                {
                    'name': 'order_date',
                    'type': 'date',
                    'description': 'Order date',
                    'default': '2024-01-01'
                }
            ]
        }
        
        params = await retriever._extract_parameters("Show customer 456 orders", template)
        
        assert params['customer_id'] == 123  # From mocked response
        assert params['order_date'] == '2024-01-01'  # Default applied
        
        # Verify LLM was called
        retriever.inference_client.generate.assert_called_once()
        call_args = retriever.inference_client.generate.call_args[0][0]
        assert 'customer_id' in call_args
        assert 'Show customer 456 orders' in call_args
    
    @pytest.mark.asyncio
    async def test_execute_template(self, retriever):
        """Test SQL template execution"""
        template = {
            'sql_template': 'SELECT * FROM customers WHERE id = %(customer_id)s'
        }
        parameters = {'customer_id': 123}
        
        # Mock execute_query method
        retriever.execute_query = AsyncMock(return_value=[
            {'id': 123, 'name': 'John Doe', 'email': 'john@example.com'}
        ])
        
        results, error = await retriever._execute_template(template, parameters)
        
        assert error is None
        assert len(results) == 1
        assert results[0]['id'] == 123
        
        # Verify query execution
        retriever.execute_query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_sql_template(self, retriever):
        """Test SQL template processing with conditionals"""
        sql_template = """
        SELECT * FROM orders 
        WHERE customer_id = %(customer_id)s
        {% if status %}
        AND status = %(status)s
        {% endif %}
        {% if min_amount %}
        AND total >= %(min_amount)s
        {% endif %}
        """
        
        # Test with all parameters
        params = {'customer_id': 123, 'status': 'shipped', 'min_amount': 100}
        processed = retriever._process_sql_template(sql_template, params)
        assert 'AND status = %(status)s' in processed
        assert 'AND total >= %(min_amount)s' in processed
        
        # Test with partial parameters
        params = {'customer_id': 123, 'status': 'shipped'}
        processed = retriever._process_sql_template(sql_template, params)
        assert 'AND status = %(status)s' in processed
        assert 'AND total >= %(min_amount)s' not in processed
    
    @pytest.mark.asyncio
    async def test_get_relevant_context_success(self, retriever, mock_embedding_client, 
                                              mock_inference_client, mock_chroma_collection,
                                              mock_adapter):
        """Test successful context retrieval"""
        # Setup services
        retriever.embedding_client = mock_embedding_client
        retriever.inference_client = mock_inference_client
        retriever.template_collection = mock_chroma_collection
        
        # Mock methods
        retriever.execute_query = AsyncMock(return_value=[
            {'id': 123, 'name': 'John Doe'}
        ])
        
        # Execute
        results = await retriever.get_relevant_context("Show customer 123")
        
        assert len(results) == 1
        assert results[0]['content'] == 'Formatted result'
        assert results[0]['confidence'] == 0.8
    
    @pytest.mark.asyncio
    async def test_get_relevant_context_no_templates(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test when no matching templates found"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        
        # Mock empty template results
        mock_chroma_collection.query.return_value = {
            'ids': [[]],
            'distances': [[]],
            'documents': [[]],
            'metadatas': [[]]
        }
        
        results = await retriever.get_relevant_context("Unknown query")
        
        assert len(results) == 1
        assert results[0]['confidence'] == 0.0
        assert 'no_matching_template' in results[0]['metadata']['error']
    
    @pytest.mark.asyncio
    async def test_get_relevant_context_low_confidence(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test when template confidence is below threshold"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        retriever.confidence_threshold = 0.9  # Set high threshold
        
        # Mock low confidence result (distance 0.5 = similarity 0.5)
        mock_chroma_collection.query.return_value = {
            'ids': [['find_customer']],
            'distances': [[0.5]],
            'documents': [['Find customer']],
            'metadatas': [[{'template_id': 'find_customer'}]]
        }
        
        results = await retriever.get_relevant_context("Show customer maybe")
        
        assert len(results) == 1
        assert results[0]['confidence'] == 0.0
        assert 'parameter_extraction_failed' in results[0]['metadata']['error']
    
    @pytest.mark.asyncio
    async def test_format_sql_results(self, retriever, mock_adapter):
        """Test SQL result formatting"""
        results = [
            {'id': 1, 'name': 'Item 1'},
            {'id': 2, 'name': 'Item 2'}
        ]
        template = {'id': 'test_template', 'description': 'Test query'}
        parameters = {'test_param': 'value'}
        similarity = 0.85
        
        formatted = retriever._format_sql_results(results, template, parameters, similarity)
        
        assert len(formatted) == 1
        assert formatted[0]['confidence'] == 0.85
        
        # Verify adapter was called
        mock_adapter.format_document.assert_called_once()
        call_args = mock_adapter.format_document.call_args
        assert 'test_template' in str(call_args)
    
    @pytest.mark.asyncio
    async def test_format_sql_results_empty(self, retriever):
        """Test formatting when no SQL results"""
        results = []
        template = {'id': 'test_template'}
        parameters = {}
        similarity = 0.9
        
        formatted = retriever._format_sql_results(results, template, parameters, similarity)
        
        assert len(formatted) == 1
        assert formatted[0]['content'] == "No results found for your query."
        assert formatted[0]['confidence'] == 0.9
        assert formatted[0]['metadata']['result_count'] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])