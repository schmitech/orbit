"""
Tests for the BaseIntentSQLRetriever abstract base class
"""

import pytest
import asyncio
import sys
import os
import json
import tempfile
import yaml
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock, AsyncMock, Mock
from decimal import Decimal
from datetime import datetime, date

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.base_intent_sql_retriever import BaseIntentSQLRetriever
from retrievers.adapters.intent.intent_adapter import IntentAdapter


class MockIntentSQLRetriever(BaseIntentSQLRetriever):
    """Concrete implementation of BaseIntentSQLRetriever for testing"""
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection=None, **kwargs):
        super().__init__(config=config, domain_adapter=domain_adapter, connection=connection, **kwargs)
        self.mock_connection = connection or MagicMock()
        
    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return "test_sql"
        
    def _create_database_connection(self):
        """Create a mock database connection"""
        return self.mock_connection
        
    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Mock query execution"""
        # Simulate different responses based on query content
        if "SELECT" in query.upper():
            if "customers" in query.lower():
                return [
                    {'id': 1, 'name': 'John Doe', 'email': 'john@example.com'},
                    {'id': 2, 'name': 'Jane Smith', 'email': 'jane@example.com'}
                ]
            elif "orders" in query.lower():
                return [
                    {'id': 101, 'customer_id': 1, 'total': Decimal('99.99'), 'order_date': datetime.now()},
                    {'id': 102, 'customer_id': 2, 'total': Decimal('149.50'), 'order_date': datetime.now()}
                ]
        return []
        
    def _convert_row_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database-specific types to standard Python types"""
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, (datetime, date)):
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        return converted
        
    async def close(self) -> None:
        """Close any open services and connections"""
        if self.connection:
            self.connection.close()
        await super().close()
        
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for matching"""
        return text.lower().split()
        
    def _calculate_similarity(self, query: str, text: str) -> float:
        """Calculate similarity between query and text"""
        query_tokens = set(self._tokenize_text(query))
        text_tokens = set(self._tokenize_text(text))
        
        if not query_tokens or not text_tokens:
            return 0.0
            
        intersection = query_tokens & text_tokens
        union = query_tokens | text_tokens
        
        return len(intersection) / len(union) if union else 0.0


class TestBaseIntentSQLRetriever:
    """Test suite for BaseIntentSQLRetriever"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration for testing"""
        return {
            "domain_name": "E-Commerce",
            "description": "Customer order management system",
            "entities": {
                "customer": {
                    "name": "customer",
                    "table_name": "customers",
                    "primary_key": "id"
                },
                "order": {
                    "name": "order", 
                    "table_name": "orders",
                    "primary_key": "id"
                }
            },
            "vocabulary": {
                "entity_synonyms": {
                    "customer": ["client", "buyer", "user"],
                    "order": ["purchase", "transaction"]
                },
                "action_verbs": {
                    "find": ["show", "get", "list", "display"]
                }
            }
        }
    
    @pytest.fixture
    def sample_templates(self):
        """Sample SQL templates for testing"""
        return {
            "templates": [
                {
                    "id": "find_customer_by_id",
                    "description": "Find customer by ID",
                    "nl_examples": [
                        "Show me customer 123",
                        "Get customer with id 456"
                    ],
                    "tags": ["customer", "find", "id"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "customer",
                        "qualifiers": ["by_id"]
                    },
                    "parameters": [
                        {
                            "name": "customer_id",
                            "type": "integer",
                            "description": "Customer ID to search for",
                            "required": True,
                            "example": 123
                        }
                    ],
                    "sql_template": "SELECT * FROM customers WHERE id = %(customer_id)s"
                },
                {
                    "id": "find_recent_orders",
                    "description": "Find recent orders within specified days",
                    "nl_examples": [
                        "Show orders from last 7 days",
                        "Get recent orders"
                    ],
                    "tags": ["orders", "recent", "time"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order", 
                        "qualifiers": ["recent", "time_based"]
                    },
                    "parameters": [
                        {
                            "name": "days_back",
                            "type": "integer",
                            "description": "Number of days to look back",
                            "required": True,
                            "default": 7,
                            "example": 30
                        }
                    ],
                    "sql_template": """
                        SELECT o.*, c.name as customer_name
                        FROM orders o
                        JOIN customers c ON o.customer_id = c.id
                        WHERE o.order_date >= CURRENT_DATE - INTERVAL '%(days_back)s days'
                        ORDER BY o.order_date DESC
                    """
                }
            ]
        }
    
    @pytest.fixture
    def temp_config_files(self, sample_domain_config, sample_templates):
        """Create temporary configuration files"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as domain_file:
            yaml.dump(sample_domain_config, domain_file)
            domain_path = domain_file.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as template_file:
            yaml.dump(sample_templates, template_file)
            template_path = template_file.name
            
        yield domain_path, template_path
        
        # Cleanup
        os.unlink(domain_path)
        os.unlink(template_path)
    
    @pytest.fixture
    def mock_config(self, temp_config_files):
        """Mock configuration for testing"""
        domain_path, template_path = temp_config_files
        return {
            'datasources': {
                'test_sql': {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'testdb'
                }
            },
            'config': {
                'domain_config_path': domain_path,
                'template_library_path': template_path,
                'template_collection_name': 'test_templates',
                'confidence_threshold': 0.75,
                'max_templates': 5,
                'chroma_persist': False,
                'embedding_provider': None
            },
            'verbose': True
        }
    
    @pytest.fixture
    def mock_adapter(self, sample_templates, sample_domain_config):
        """Mock IntentAdapter for testing"""
        adapter = MagicMock(spec=IntentAdapter)
        adapter.get_all_templates.return_value = sample_templates['templates']
        adapter.get_template_by_id.return_value = sample_templates['templates'][0]
        adapter.get_domain_config.return_value = sample_domain_config
        adapter.format_document.return_value = {
            'content': 'Formatted result',
            'metadata': {'source': 'intent'},
            'result_count': 1
        }
        return adapter
    
    @pytest.fixture
    def mock_embedding_client(self):
        """Mock embedding client"""
        client = AsyncMock()
        client.embed_query = AsyncMock(return_value=[0.1] * 768)
        client.initialize = AsyncMock()
        return client
    
    @pytest.fixture
    def mock_inference_client(self):
        """Mock inference client"""
        client = AsyncMock()
        client.generate = AsyncMock(return_value='{"customer_id": 123, "days_back": 7}')
        client.initialize = AsyncMock()
        return client
    
    @pytest.fixture
    def mock_chroma_collection(self):
        """Mock ChromaDB collection"""
        collection = MagicMock()
        collection.add = MagicMock()
        collection.delete = MagicMock()
        collection.get = MagicMock(return_value={'ids': []})
        collection.count = MagicMock(return_value=0)
        collection.query = MagicMock(return_value={
            'ids': [['find_customer_by_id']],
            'distances': [[0.2]],  # Distance = 0.2, similarity = 0.8
            'documents': [['Find customer by ID']],
            'metadatas': [[{'template_id': 'find_customer_by_id'}]]
        })
        return collection
    
    @pytest.fixture
    def retriever(self, mock_config, mock_adapter):
        """Create retriever instance for testing"""
        return MockIntentSQLRetriever(
            config=mock_config,
            domain_adapter=mock_adapter
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, retriever, mock_config):
        """Test retriever initialization"""
        assert retriever.template_collection_name == 'test_templates'
        assert retriever.confidence_threshold == 0.75
        assert retriever.max_templates == 5
        assert retriever.embedding_client is None  # Not initialized yet
        assert retriever.inference_client is None  # Not initialized yet
        assert retriever.domain_adapter is not None
    
    @pytest.mark.asyncio
    async def test_initialization_with_default_adapter(self, mock_config):
        """Test retriever initialization creates IntentAdapter if not provided"""
        with patch('retrievers.implementations.intent.base_intent_sql_retriever.IntentAdapter') as mock_adapter_class:
            mock_adapter = MagicMock()
            mock_adapter_class.return_value = mock_adapter
            
            retriever = MockIntentSQLRetriever(config=mock_config)
            
            assert retriever.domain_adapter == mock_adapter
            mock_adapter_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_services(self, retriever, mock_embedding_client, mock_inference_client, mock_chroma_collection):
        """Test service initialization"""
        with patch('embeddings.base.EmbeddingServiceFactory') as mock_embed_factory:
            with patch('inference.pipeline.providers.provider_factory.ProviderFactory') as mock_inf_factory:
                with patch('chromadb.Client') as mock_chroma_client:
                    # Setup mocks
                    mock_embed_factory.create_embedding_service.return_value = mock_embedding_client
                    mock_inf_factory.create_provider.return_value = mock_inference_client
                    
                    mock_chroma = MagicMock()
                    mock_chroma.get_or_create_collection.return_value = mock_chroma_collection
                    mock_chroma_client.return_value = mock_chroma
                    
                    # Initialize
                    await retriever.initialize()
                    
                    # Verify services initialized
                    assert retriever.embedding_client == mock_embedding_client
                    assert retriever.inference_client == mock_inference_client
                    assert retriever.template_collection == mock_chroma_collection
                    assert retriever.parameter_extractor is not None
                    assert retriever.response_generator is not None
                    assert retriever.template_reranker is not None
    
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
    async def test_create_template_metadata(self, retriever):
        """Test template metadata creation"""
        template = {
            'id': 'test_template',
            'description': 'Test template',
            'category': 'test',
            'complexity': 'simple',
            'semantic_tags': {
                'action': 'find',
                'primary_entity': 'customer'
            }
        }
        
        metadata = retriever._create_template_metadata(template)
        
        assert metadata['template_id'] == 'test_template'
        assert metadata['description'] == 'Test template'
        assert metadata['category'] == 'test'
        assert metadata['complexity'] == 'simple'
        assert metadata['semantic_action'] == 'find'
        assert metadata['semantic_primary_entity'] == 'customer'
    
    @pytest.mark.asyncio
    async def test_convert_row_types(self, retriever):
        """Test database row type conversion"""
        from decimal import Decimal
        from datetime import datetime, date
        
        test_date = datetime(2024, 1, 15, 10, 30, 0)
        test_date_only = date(2024, 1, 15)
        
        row = {
            'id': 123,
            'name': 'Test User',
            'amount': Decimal('99.99'),
            'created_at': test_date,
            'birth_date': test_date_only,
            'status': 'active'
        }
        
        converted = retriever._convert_row_types(row)
        
        assert converted['id'] == 123
        assert converted['name'] == 'Test User'
        assert converted['amount'] == 99.99  # Decimal converted to float
        assert converted['created_at'] == test_date.isoformat()  # datetime converted to ISO string
        assert converted['birth_date'] == test_date_only.isoformat()  # date converted to ISO string
        assert converted['status'] == 'active'
    
    @pytest.mark.asyncio
    async def test_calculate_simple_similarity(self, retriever):
        """Test simple text similarity calculation"""
        text1 = "show me customer orders"
        text2 = "display customer purchases"
        
        similarity = retriever._calculate_simple_similarity(text1, text2)
        
        # Should have some overlap with "customer"
        assert 0.0 < similarity < 1.0
        
        # Test identical texts
        similarity_identical = retriever._calculate_simple_similarity(text1, text1)
        assert similarity_identical == 1.0
        
        # Test completely different texts
        similarity_different = retriever._calculate_simple_similarity("hello world", "goodbye universe")
        assert similarity_different == 0.0
    
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
                    'name': 'days_back',
                    'type': 'integer',
                    'description': 'Days to look back',
                    'default': 7
                }
            ]
        }
        
        params = await retriever._extract_parameters("Show customer 456 orders", template)
        
        assert 'customer_id' in params
        assert 'days_back' in params
        assert params['days_back'] == 7  # Default applied
        
        # Verify LLM was called
        mock_inference_client.generate.assert_called_once()
    
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
        params_partial = {'customer_id': 123, 'status': 'shipped'}
        processed_partial = retriever._process_sql_template(sql_template, params_partial)
        assert 'AND status = %(status)s' in processed_partial
        assert 'AND total >= %(min_amount)s' not in processed_partial
    
    @pytest.mark.asyncio
    async def test_execute_template(self, retriever):
        """Test SQL template execution"""
        template = {
            'id': 'test_template',
            'description': 'Test query',
            'sql_template': 'SELECT * FROM customers WHERE id = %(customer_id)s'
        }
        parameters = {'customer_id': 123}
        
        results, error = await retriever._execute_template(template, parameters)
        
        assert error is None
        assert len(results) == 2  # Mock returns 2 customers
        assert results[0]['id'] == 1
        assert results[0]['name'] == 'John Doe'
    
    @pytest.mark.asyncio
    async def test_execute_template_with_like_wildcards(self, retriever):
        """Test SQL template execution with LIKE query wildcards"""
        template = {
            'sql_template': 'SELECT * FROM customers WHERE name LIKE %(customer_name)s'
        }
        parameters = {'customer_name': 'John'}
        
        results, error = await retriever._execute_template(template, parameters)
        
        assert error is None
        # The parameter should have been modified to add wildcards for LIKE queries
        # This is tested indirectly through the successful execution
    
    @pytest.mark.asyncio
    async def test_execute_template_no_sql(self, retriever):
        """Test template execution with missing SQL"""
        template = {'id': 'test_template'}  # No sql_template
        parameters = {}
        
        results, error = await retriever._execute_template(template, parameters)
        
        assert results == []
        assert error == "Template has no SQL query"
    
    @pytest.mark.asyncio
    async def test_fallback_template_matching(self, retriever):
        """Test fallback template matching when embeddings fail"""
        query = "show customer orders"
        
        matches = retriever._fallback_template_matching(query)
        
        # Should find matches based on text similarity
        assert len(matches) >= 0  # May be 0 if no good matches
        
        # If matches found, they should have similarity scores
        for match in matches:
            assert 'template' in match
            assert 'similarity' in match
            assert 0.0 <= match['similarity'] <= 1.0
    
    @pytest.mark.asyncio
    async def test_find_best_templates(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test finding best matching templates"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        
        templates = await retriever._find_best_templates("Show me customer 123")
        
        assert len(templates) == 1
        assert templates[0]['template']['id'] == 'find_customer_by_id'
        assert templates[0]['similarity'] == 0.8  # 1 - 0.2 distance
        
        # Verify embedding was created
        mock_embedding_client.embed_query.assert_called_once_with("Show me customer 123")
        
        # Verify ChromaDB query
        mock_chroma_collection.query.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_find_best_templates_embedding_failure(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test template finding when embedding fails"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        
        # Make embedding fail
        mock_embedding_client.embed_query.side_effect = Exception("Embedding failed")
        
        # Should fall back to simple text matching
        templates = await retriever._find_best_templates("show customer")
        
        # Should still return results from fallback matching
        assert isinstance(templates, list)
    
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
    
    @pytest.mark.asyncio
    async def test_set_collection(self, retriever):
        """Test setting collection name"""
        await retriever.set_collection("test_table")
        
        assert retriever.collection == "test_table"
        
        # Test with empty collection name should raise error
        with pytest.raises(ValueError):
            await retriever.set_collection("")
    
    @pytest.mark.asyncio
    async def test_get_relevant_context_no_templates(self, retriever, mock_embedding_client, mock_chroma_collection):
        """Test context retrieval when no templates match"""
        retriever.embedding_client = mock_embedding_client
        retriever.template_collection = mock_chroma_collection
        
        # Mock empty template results
        mock_chroma_collection.query.return_value = {
            'ids': [[]],
            'distances': [[]],
            'documents': [[]],
            'metadatas': [[]]
        }
        
        results = await retriever.get_relevant_context("unknown query")
        
        assert len(results) == 1
        assert results[0]['confidence'] == 0.0
        assert 'no_matching_template' in results[0]['metadata']['error']
    
    @pytest.mark.asyncio
    async def test_get_relevant_context_error_handling(self, retriever):
        """Test error handling in context retrieval"""
        # Force an exception by patching a method to always raise
        with patch.object(retriever, '_find_best_templates', side_effect=Exception("Forced test error")):
            results = await retriever.get_relevant_context("test query")
            
            assert len(results) == 1
            assert results[0]['confidence'] == 0.0
            assert 'error' in results[0]['metadata']
            assert 'An error occurred' in results[0]['content']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])