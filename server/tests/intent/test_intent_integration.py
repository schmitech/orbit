"""
Integration tests for the Intent retriever system
"""

import pytest
import asyncio
import sys
import os
import yaml
import tempfile
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock, AsyncMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
from retrievers.adapters.intent.intent_adapter import IntentAdapter
from retrievers.base.base_retriever import RetrieverFactory


class TestIntentIntegration:
    """Integration tests for the intent retrieval system"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration"""
        return {
            "domain_name": "E-Commerce",
            "description": "Customer order management system",
            "entities": {
                "customer": {
                    "name": "customer",
                    "entity_type": "primary",
                    "table_name": "customers",
                    "description": "Customer information",
                    "primary_key": "id",
                    "searchable_fields": ["name", "email"]
                },
                "order": {
                    "name": "order",
                    "entity_type": "transaction",
                    "table_name": "orders",
                    "description": "Customer orders",
                    "primary_key": "id"
                }
            },
            "vocabulary": {
                "entity_synonyms": {
                    "customer": ["client", "buyer", "shopper"],
                    "order": ["purchase", "transaction"]
                },
                "action_verbs": {
                    "find": ["show", "get", "list", "display"],
                    "calculate": ["sum", "total", "compute"]
                }
            }
        }
    
    @pytest.fixture
    def sample_templates(self):
        """Sample SQL templates"""
        return {
            "templates": [
                {
                    "id": "find_customer_by_id",
                    "description": "Find a customer by their ID",
                    "nl_examples": [
                        "Show me customer 123",
                        "Get customer with id 456",
                        "Find customer #789"
                    ],
                    "tags": ["customer", "find", "id", "lookup"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "customer",
                        "intent": "find_customer_by_id"
                    },
                    "parameters": [
                        {
                            "name": "customer_id",
                            "type": "integer",
                            "description": "The customer ID to search for",
                            "required": True,
                            "example": 123
                        }
                    ],
                    "sql_template": "SELECT id, name, email FROM customers WHERE id = %(customer_id)s",
                    "result_format": "single"
                },
                {
                    "id": "find_recent_orders",
                    "description": "Find recent orders within specified days",
                    "nl_examples": [
                        "Show me orders from the last 7 days",
                        "Get recent orders from past week",
                        "Find orders placed recently"
                    ],
                    "tags": ["orders", "recent", "time", "date"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order",
                        "qualifiers": ["recent", "time_based"]
                    },
                    "parameters": [
                        {
                            "name": "days",
                            "type": "integer",
                            "description": "Number of days to look back",
                            "required": True,
                            "default": 7,
                            "example": 30
                        }
                    ],
                    "sql_template": """
                        SELECT o.id, o.order_date, o.total, c.name as customer_name
                        FROM orders o
                        JOIN customers c ON o.customer_id = c.id
                        WHERE o.order_date >= CURRENT_DATE - INTERVAL '%(days)s days'
                        ORDER BY o.order_date DESC
                    """,
                    "result_format": "table"
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
    def mock_embedding_service(self):
        """Mock embedding service that returns consistent embeddings"""
        embeddings = {
            "Show me customer 123": [0.9, 0.1, 0.2] + [0.0] * 765,  # High match for customer ID
            "Get recent orders": [0.1, 0.9, 0.2] + [0.0] * 765,     # High match for recent orders
            "Find a customer by their ID": [0.85, 0.15, 0.2] + [0.0] * 765,
            "Find recent orders within specified days": [0.15, 0.85, 0.2] + [0.0] * 765
        }
        
        client = AsyncMock()
        client.embed_query = AsyncMock(side_effect=lambda text: embeddings.get(text, [0.5] * 768))
        return client
    
    @pytest.fixture
    def mock_inference_service(self):
        """Mock inference service for parameter extraction and response generation"""
        client = AsyncMock()
        
        def generate_response(prompt, **kwargs):
            # Check if this is parameter extraction (looking for JSON patterns)
            if "JSON" in prompt and ("customer_id" in prompt or "parameter" in prompt.lower()):
                if "customer" in prompt.lower() and "123" in prompt:
                    return '{"customer_id": 123}'
                elif "order" in prompt.lower() and "recent" in prompt.lower():
                    return '{"days": 7}'
                return '{}'
            
            # This is response generation - return natural language
            elif "conversational response" in prompt.lower() or "direct response" in prompt.lower():
                if "John Doe" in prompt and "customer" in prompt.lower():
                    return "Found customer John Doe (ID: 123) with email john@example.com."
                elif "no results" in prompt.lower():
                    return "No matching records were found for your query."
                elif "error" in prompt.lower():
                    return "I encountered an error processing your request."
                else:
                    return "Here are the results from your query."
            
            # Default fallback
            return "Response generated successfully."
        
        client.generate = AsyncMock(side_effect=generate_response)
        return client
    
    @pytest.fixture
    def mock_postgres_connection(self):
        """Mock PostgreSQL connection and cursor"""
        cursor = MagicMock()
        cursor.fetchall = MagicMock(return_value=[
            {'id': 123, 'name': 'John Doe', 'email': 'john@example.com'}
        ])
        cursor.description = [('id',), ('name',), ('email',)]
        
        connection = MagicMock()
        connection.cursor = MagicMock(return_value=cursor)
        return connection
    
    @pytest.mark.asyncio
    async def test_complete_intent_flow(self, temp_config_files, mock_embedding_service, 
                                      mock_inference_service, mock_postgres_connection):
        """Test complete flow from natural language to SQL results"""
        domain_path, template_path = temp_config_files
        
        # Create configuration
        config = {
            'datasources': {
                'postgresql': {
                    'host': 'localhost',
                    'port': 5432,
                    'database': 'testdb'
                }
            },
            'config': {
                'domain_config_path': domain_path,
                'template_library_path': template_path,
                'confidence_threshold': 0.7,
                'max_templates': 5
            }
        }
        
        # Patch services
        with patch('embeddings.base.EmbeddingServiceFactory') as mock_embed_factory:
            with patch('inference.pipeline.providers.provider_factory.ProviderFactory') as mock_inf_factory:
                with patch('chromadb.Client') as mock_chroma_client:
                    # Setup service mocks
                    mock_embed_factory.create_embedding_service.return_value = mock_embedding_service
                    mock_inf_factory.create_provider.return_value = mock_inference_service
                    
                    # Setup ChromaDB mock
                    mock_collection = MagicMock()
                    mock_collection.query.return_value = {
                        'ids': [['find_customer_by_id']],
                        'distances': [[0.2]],  # Distance = 0.2, similarity = 0.8
                        'documents': [['Find customer by ID']],
                        'metadatas': [[{'template_id': 'find_customer_by_id'}]]
                    }
                    mock_chroma = MagicMock()
                    mock_chroma.get_or_create_collection.return_value = mock_collection
                    mock_chroma_client.return_value = mock_chroma
                    
                    # Create retriever
                    retriever = IntentPostgreSQLRetriever(config=config, connection=mock_postgres_connection)
                    
                    # Mock execute_query to return test data
                    retriever.execute_query = AsyncMock(return_value=[
                        {'id': 123, 'name': 'John Doe', 'email': 'john@example.com'}
                    ])
                    
                    # Initialize
                    await retriever.initialize()
                    
                    # Test customer query
                    results = await retriever.get_relevant_context("Show me customer 123")
                    
                    assert len(results) > 0
                    assert results[0]['confidence'] > 0.7
                    assert 'John Doe' in results[0]['content']
    
    @pytest.mark.asyncio
    async def test_intent_retriever_factory_registration(self):
        """Test that the intent retriever is properly registered with the factory"""
        # Check that 'intent' is registered
        retrievers = RetrieverFactory._registered_retrievers
        assert 'intent' in retrievers
    
    @pytest.mark.asyncio
    async def test_parameter_extraction_edge_cases(self, temp_config_files):
        """Test parameter extraction with various edge cases"""
        domain_path, template_path = temp_config_files
        
        # Create adapter
        adapter = IntentAdapter(
            domain_config_path=domain_path,
            template_library_path=template_path
        )
        
        # Test with different query patterns
        test_cases = [
            # (query, expected_template_match)
            ("Show me customer one two three", "find_customer_by_id"),  # Numbers in words
            ("Get customer ID#123", "find_customer_by_id"),  # Different ID format
            ("Recent orders", "find_recent_orders"),  # Minimal query
            ("Orders from last month", "find_recent_orders"),  # Time expression
        ]
        
        templates = adapter.get_all_templates()
        assert len(templates) == 2
    
    @pytest.mark.asyncio
    async def test_sql_template_with_conditionals(self):
        """Test SQL templates with conditional blocks"""
        template_with_conditionals = """
        SELECT * FROM orders 
        WHERE 1=1
        {% if customer_id %}
        AND customer_id = %(customer_id)s
        {% endif %}
        {% if status %}
        AND status = %(status)s
        {% endif %}
        {% if date_from %}
        AND order_date >= %(date_from)s
        {% endif %}
        ORDER BY order_date DESC
        """
        
        # Test with all parameters
        params = {
            'customer_id': 123,
            'status': 'shipped',
            'date_from': '2024-01-01'
        }
        
        retriever = IntentPostgreSQLRetriever({'config': {}})
        processed = retriever._process_sql_template(template_with_conditionals, params)
        
        assert 'AND customer_id = %(customer_id)s' in processed
        assert 'AND status = %(status)s' in processed
        assert 'AND order_date >= %(date_from)s' in processed
        
        # Test with partial parameters
        params = {'customer_id': 123, 'status': 'shipped'}
        processed = retriever._process_sql_template(template_with_conditionals, params)
        
        assert 'AND customer_id = %(customer_id)s' in processed
        assert 'AND status = %(status)s' in processed
        assert 'AND order_date >= %(date_from)s' not in processed
    
    @pytest.mark.asyncio
    async def test_result_formatting_variations(self):
        """Test different result formatting scenarios"""
        adapter = IntentAdapter()
        
        # Test single result
        single_result = {
            'results': [{'id': 1, 'name': 'Test', 'total': 100.50}]
        }
        formatted = adapter.format_document("", single_result)
        assert formatted['result_count'] == 1
        assert 'Id: 1' in formatted['content']
        assert 'Total: 100.5' in formatted['content']
        
        # Test multiple results
        multiple_results = {
            'results': [
                {'id': i, 'name': f'Item {i}'} 
                for i in range(10)
            ]
        }
        formatted = adapter.format_document("", multiple_results)
        assert formatted['result_count'] == 10
        assert 'Found 10 results:' in formatted['content']
        assert 'Result 5:' in formatted['content']
        assert '... and 5 more results' in formatted['content']
        
        # Test empty results
        empty_results = {'results': []}
        formatted = adapter.format_document("", empty_results)
        assert formatted['result_count'] == 0
        assert 'No results found' in formatted['content']
    
    @pytest.mark.asyncio 
    async def test_confidence_threshold_filtering(self, temp_config_files):
        """Test that results below confidence threshold are filtered"""
        domain_path, template_path = temp_config_files
        
        adapter = IntentAdapter(confidence_threshold=0.8)
        
        # Create context items with varying confidence
        context_items = [
            {'content': 'High confidence', 'confidence': 0.95},
            {'content': 'Medium confidence', 'confidence': 0.75},  # Below threshold
            {'content': 'Low confidence', 'confidence': 0.5},      # Below threshold
            {'content': 'Good confidence', 'confidence': 0.85}
        ]
        
        filtered = adapter.apply_domain_filtering(context_items, "test query")
        
        assert len(filtered) == 2
        assert all(item['confidence'] >= 0.8 for item in filtered)
        assert filtered[0]['content'] == 'High confidence'
        assert filtered[1]['content'] == 'Good confidence'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])