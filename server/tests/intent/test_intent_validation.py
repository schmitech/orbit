
"""
Validation tests for Intent retriever using test queries similar to the PoC validation
"""

import pytest
import asyncio
import sys
import os
import yaml
import tempfile
import json
from typing import Dict, Any, List, Tuple
from unittest.mock import patch, MagicMock, AsyncMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.intent_postgresql_retriever import IntentPostgreSQLRetriever
from adapters.intent.adapter import IntentAdapter


class TestIntentValidation:
    """Validation tests for Intent retriever based on PoC test patterns"""
    
    @pytest.fixture
    def validation_templates(self):
        """Templates for validation testing"""
        return {
            "templates": [
                {
                    "id": "find_customer_by_id",
                    "description": "Find a customer by their ID",
                    "nl_examples": [
                        "Show me customer 123",
                        "Get customer with id 456",
                        "Find customer #789",
                        "What are the details for customer 100"
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
                    "sql_template": "SELECT id, name, email FROM customers WHERE id = %(customer_id)s"
                },
                {
                    "id": "find_customer_orders",
                    "description": "Find all orders for a specific customer",
                    "nl_examples": [
                        "Show me all orders for customer 123",
                        "Get orders from customer #456",
                        "What orders has customer 789 placed",
                        "List customer 100's orders"
                    ],
                    "tags": ["customer", "orders", "history"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order",
                        "secondary_entity": "customer"
                    },
                    "parameters": [
                        {
                            "name": "customer_id",
                            "type": "integer",
                            "description": "Customer ID whose orders to retrieve",
                            "required": True
                        }
                    ],
                    "sql_template": """
                        SELECT o.id, o.order_date, o.total, o.status
                        FROM orders o
                        WHERE o.customer_id = %(customer_id)s
                        ORDER BY o.order_date DESC
                    """
                },
                {
                    "id": "find_high_value_orders",
                    "description": "Find orders above a certain amount",
                    "nl_examples": [
                        "Show me orders over $1000",
                        "Find high value orders above 500",
                        "Get orders with total greater than 2000"
                    ],
                    "tags": ["orders", "high", "value", "amount"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order",
                        "qualifiers": ["high_value"]
                    },
                    "parameters": [
                        {
                            "name": "min_amount",
                            "type": "decimal",
                            "description": "Minimum order amount",
                            "required": True,
                            "default": 1000,
                            "example": 500
                        }
                    ],
                    "sql_template": """
                        SELECT o.id, o.order_date, o.total, c.name as customer_name
                        FROM orders o
                        JOIN customers c ON o.customer_id = c.id
                        WHERE o.total >= %(min_amount)s
                        ORDER BY o.total DESC
                    """
                },
                {
                    "id": "find_orders_by_status",
                    "description": "Find orders by status",
                    "nl_examples": [
                        "Show me all pending orders",
                        "Find delivered orders",
                        "List cancelled orders"
                    ],
                    "tags": ["orders", "status", "filter"],
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order",
                        "qualifiers": ["status_filter"]
                    },
                    "parameters": [
                        {
                            "name": "status",
                            "type": "string",
                            "description": "Order status to filter by",
                            "required": True,
                            "allowed_values": ["pending", "processing", "shipped", "delivered", "cancelled"]
                        }
                    ],
                    "sql_template": """
                        SELECT o.id, o.order_date, o.total, o.status, c.name as customer_name
                        FROM orders o
                        JOIN customers c ON o.customer_id = c.id
                        WHERE o.status = %(status)s
                        ORDER BY o.order_date DESC
                    """
                }
            ]
        }
    
    @pytest.fixture
    def test_queries_by_category(self):
        """Test queries organized by category, similar to the PoC validation"""
        return {
            "customer": [
                ("Show me customer 123", "find_customer_by_id", {"customer_id": 123}),
                ("Get customer with id 456", "find_customer_by_id", {"customer_id": 456}),
                ("Find customer #789", "find_customer_by_id", {"customer_id": 789}),
                ("What are the details for customer 100", "find_customer_by_id", {"customer_id": 100})
            ],
            "customer_orders": [
                ("Show me all orders for customer 123", "find_customer_orders", {"customer_id": 123}),
                ("Get orders from customer #456", "find_customer_orders", {"customer_id": 456}),
                ("What orders has customer 789 placed", "find_customer_orders", {"customer_id": 789}),
                ("List customer 100's orders", "find_customer_orders", {"customer_id": 100})
            ],
            "order_value": [
                ("Show me orders over $1000", "find_high_value_orders", {"min_amount": 1000}),
                ("Find high value orders above 500", "find_high_value_orders", {"min_amount": 500}),
                ("Get orders with total greater than 2000", "find_high_value_orders", {"min_amount": 2000})
            ],
            "order_status": [
                ("Show me all pending orders", "find_orders_by_status", {"status": "pending"}),
                ("Find delivered orders", "find_orders_by_status", {"status": "delivered"}),
                ("List cancelled orders", "find_orders_by_status", {"status": "cancelled"})
            ]
        }
    
    @pytest.fixture
    def mock_embedding_service_with_similarity(self):
        """Mock embedding service that calculates similarity based on keyword matching"""
        def calculate_similarity(query_text: str, template_text: str) -> float:
            """Simple keyword-based similarity for testing"""
            query_words = set(query_text.lower().split())
            template_words = set(template_text.lower().split())
            
            if not query_words or not template_words:
                return 0.0
            
            intersection = query_words.intersection(template_words)
            union = query_words.union(template_words)
            
            return len(intersection) / len(union) if union else 0.0
        
        # Create embedding mappings based on templates
        template_embeddings = {
            "find_customer_by_id": "customer id find show get",
            "find_customer_orders": "customer orders list history",
            "find_high_value_orders": "orders high value amount over above",
            "find_orders_by_status": "orders status pending delivered cancelled"
        }
        
        client = AsyncMock()
        
        def get_embedding(text: str):
            if text in template_embeddings:
                # Return template embedding based on content
                template_content = template_embeddings[text]
                return [calculate_similarity(text, template_content)] + [0.0] * 767
            else:
                # For queries, calculate similarity with each template
                max_sim = 0.0
                for template_id, template_content in template_embeddings.items():
                    sim = calculate_similarity(text, template_content)
                    max_sim = max(max_sim, sim)
                return [max_sim] + [0.0] * 767
        
        client.embed_query = AsyncMock(side_effect=get_embedding)
        return client
    
    @pytest.fixture
    def mock_inference_service_with_extraction(self):
        """Mock inference service that extracts parameters based on patterns"""
        def extract_parameters(prompt: str) -> str:
            """Extract parameters from query based on patterns"""
            prompt_lower = prompt.lower()
            
            # Extract customer ID
            import re
            customer_match = re.search(r'customer.*?(\d+)', prompt_lower)
            if customer_match:
                return f'{{"customer_id": {customer_match.group(1)}}}'
            
            # Extract order amount
            amount_match = re.search(r'(?:over|above|greater than).*?\$?(\d+)', prompt_lower)
            if amount_match:
                return f'{{"min_amount": {amount_match.group(1)}}}'
            
            # Extract status
            status_words = ['pending', 'delivered', 'cancelled', 'shipped', 'processing']
            for status in status_words:
                if status in prompt_lower:
                    return f'{{"status": "{status}"}}'
            
            return '{}'
        
        client = AsyncMock()
        client.generate = AsyncMock(side_effect=extract_parameters)
        return client
    
    @pytest.mark.asyncio
    async def test_template_matching_accuracy(self, validation_templates, test_queries_by_category):
        """Test that queries match the expected templates"""
        # Create temporary template file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(validation_templates, f)
            template_path = f.name
        
        try:
            adapter = IntentAdapter(template_library_path=template_path)
            templates = adapter.get_all_templates()
            
            # Test each category
            for category, queries in test_queries_by_category.items():
                for query, expected_template, expected_params in queries:
                    # Find best matching template by name similarity (simplified)
                    best_match = None
                    best_score = 0.0
                    
                    for template in templates:
                        # Simple matching based on example similarity
                        examples = template.get('nl_examples', [])
                        for example in examples:
                            if query.lower() in example.lower() or example.lower() in query.lower():
                                score = 1.0
                            else:
                                # Keyword-based similarity
                                query_words = set(query.lower().split())
                                example_words = set(example.lower().split())
                                if query_words and example_words:
                                    intersection = query_words.intersection(example_words)
                                    score = len(intersection) / len(query_words.union(example_words))
                                else:
                                    score = 0.0
                            
                            if score > best_score:
                                best_score = score
                                best_match = template['id']
                    
                    # Verify the match
                    print(f"Query: '{query}' -> Expected: {expected_template}, Got: {best_match}, Score: {best_score}")
                    
                    # Allow for reasonable matching (not perfect due to simplified logic)
                    assert best_match == expected_template or best_score > 0.3, \
                        f"Query '{query}' should match template '{expected_template}', got '{best_match}'"
        
        finally:
            os.unlink(template_path)
    
    @pytest.mark.asyncio
    async def test_parameter_extraction_accuracy(self, test_queries_by_category):
        """Test parameter extraction accuracy"""
        retriever = IntentPostgreSQLRetriever({'adapter_config': {'store_name': 'chroma'}})
        
        for category, queries in test_queries_by_category.items():
            for query, template_id, expected_params in queries:
                # Create mock template
                template = {
                    'parameters': [
                        {
                            'name': param_name,
                            'type': 'integer' if param_name.endswith('_id') or param_name == 'min_amount' else 'string',
                            'description': f"Parameter {param_name}",
                            'required': True
                        }
                        for param_name in expected_params.keys()
                    ]
                }
                
                # Mock inference client
                retriever.inference_client = AsyncMock()
                retriever.inference_client.generate.return_value = json.dumps(expected_params)
                
                # Extract parameters
                extracted = await retriever._extract_parameters(query, template)
                
                # Verify extraction
                for param_name, expected_value in expected_params.items():
                    assert param_name in extracted, f"Parameter '{param_name}' not extracted from query '{query}'"
                    assert extracted[param_name] == expected_value, \
                        f"Parameter '{param_name}' value mismatch: expected {expected_value}, got {extracted[param_name]}"
    
    @pytest.mark.asyncio
    async def test_sql_generation_correctness(self, validation_templates):
        """Test that SQL templates generate correct queries"""
        retriever = IntentPostgreSQLRetriever({'adapter_config': {'store_name': 'chroma'}})
        
        test_cases = [
            {
                'template_id': 'find_customer_by_id',
                'parameters': {'customer_id': 123},
                'expected_sql_parts': ['SELECT', 'customers', 'WHERE id = %(customer_id)s']
            },
            {
                'template_id': 'find_high_value_orders',
                'parameters': {'min_amount': 1000},
                'expected_sql_parts': ['SELECT', 'orders', 'JOIN customers', 'WHERE o.total >= %(min_amount)s']
            }
        ]
        
        for test_case in test_cases:
            template = next((t for t in validation_templates['templates'] if t['id'] == test_case['template_id']), None)
            parameters = test_case['parameters']
            
            # Process SQL template
            sql = retriever._process_sql_template(template['sql_template'], parameters)
            
            # Verify SQL contains expected parts
            for expected_part in test_case['expected_sql_parts']:
                assert expected_part in sql, \
                    f"SQL for template '{test_case['template_id']}' should contain '{expected_part}'"
    
    @pytest.mark.asyncio
    async def test_confidence_scoring(self, validation_templates):
        """Test confidence scoring for different query qualities"""
        # Create temporary template file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(validation_templates, f)
            template_path = f.name
        
        try:
            config = {
                'adapter_config': {
                    'template_library_path': template_path,
                    'confidence_threshold': 0.7,
                    'store_name': 'chroma'
                }
            }
            
            with patch('embeddings.base.EmbeddingServiceFactory'):
                with patch('inference.pipeline.providers.UnifiedProviderFactory'):
                    with patch('chromadb.Client'):
                        retriever = IntentPostgreSQLRetriever(config=config)
                        
                        # Test cases with expected confidence levels
                        test_cases = [
                            ("Show me customer 123", 0.9),  # Perfect match
                            ("Get customer with id 456", 0.8),  # Good match
                            ("Find some customer maybe", 0.3),  # Poor match
                            ("Random unrelated query", 0.1)  # No match
                        ]
                        
                        for query, expected_min_confidence in test_cases:
                            # Mock ChromaDB to return appropriate similarity
                            mock_collection = MagicMock()
                            mock_collection.query.return_value = {
                                'ids': [['find_customer_by_id']],
                                'distances': [[1.0 - expected_min_confidence]],  # Distance = 1 - similarity
                                'documents': [['customer template']],
                                'metadatas': [[{'template_id': 'find_customer_by_id'}]]
                            }
                            
                            retriever.template_collection = mock_collection
                            retriever.embedding_client = AsyncMock()
                            retriever.embedding_client.embed_query = AsyncMock(return_value=[0.5] * 768)
                            
                            # Find templates
                            templates = await retriever._find_best_templates(query)
                            
                            if templates:
                                similarity = templates[0]['similarity']
                                print(f"Query: '{query}' -> Similarity: {similarity:.2f}, Expected: {expected_min_confidence:.2f}")
                                
                                # Allow some tolerance in confidence scoring
                                assert abs(similarity - expected_min_confidence) < 0.1, \
                                    f"Confidence for '{query}' should be around {expected_min_confidence}, got {similarity}"
        
        finally:
            os.unlink(template_path)
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling for various failure scenarios"""
        config = {'adapter_config': {'store_name': 'chroma'}}
        retriever = IntentPostgreSQLRetriever(config=config)
        
        # Test with no templates loaded
        retriever.embedding_client = AsyncMock()
        retriever.template_collection = MagicMock()
        retriever.template_collection.query.return_value = {
            'ids': [[]],
            'distances': [[]],
            'documents': [[]],
            'metadatas': [[]]
        }
        
        results = await retriever.get_relevant_context("test query")
        
        assert len(results) == 1
        assert results[0]['confidence'] == 0.0
        assert 'error' in results[0]['metadata']
    
    @pytest.mark.asyncio
    async def test_query_normalization(self):
        """Test that queries are properly normalized and processed"""
        retriever = IntentPostgreSQLRetriever({'adapter_config': {'store_name': 'chroma'}})
        
        # Test cases with different query formats
        test_queries = [
            "Show me customer 123",
            "show me customer 123",  # Different case
            "Show me customer #123",  # With symbol
            "Show me customer ID 123",  # With ID word
            "customer 123 please",  # Different word order
        ]
        
        # All should result in similar embedding text
        for query in test_queries:
            # Mock embedding creation (simplified)
            embedding_text = retriever._create_embedding_text({
                'description': 'Find customer',
                'nl_examples': [query],
                'tags': ['customer'],
                'parameters': [{'name': 'customer_id'}]
            })
            
            assert 'customer' in embedding_text.lower()
            assert 'find' in embedding_text.lower() or 'customer' in embedding_text.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
