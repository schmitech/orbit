"""
Tests for the IntentAdapter class
"""

import pytest
import sys
import os
import yaml
import tempfile
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.adapters.intent.intent_adapter import IntentAdapter


class TestIntentAdapter:
    """Test suite for IntentAdapter"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration for testing"""
        return {
            "domain_name": "Test E-Commerce",
            "description": "Test customer order system",
            "entities": {
                "customer": {
                    "name": "customer",
                    "entity_type": "primary",
                    "table_name": "customers",
                    "description": "Customer information",
                    "primary_key": "id"
                },
                "order": {
                    "name": "order",
                    "entity_type": "transaction",
                    "table_name": "orders",
                    "description": "Customer orders",
                    "primary_key": "id"
                }
            },
            "fields": {
                "customer": {
                    "id": {
                        "name": "id",
                        "data_type": "integer",
                        "db_column": "id",
                        "description": "Customer ID"
                    },
                    "name": {
                        "name": "name",
                        "data_type": "string",
                        "db_column": "name",
                        "description": "Customer name"
                    }
                }
            }
        }
    
    @pytest.fixture
    def sample_template_library(self):
        """Sample template library for testing"""
        return {
            "templates": [
                {
                    "id": "find_customer_by_id",
                    "description": "Find a customer by their ID",
                    "nl_examples": ["Show me customer 123", "Get customer with id 456"],
                    "tags": ["customer", "find", "id"],
                    "parameters": [
                        {
                            "name": "customer_id",
                            "type": "integer",
                            "description": "The customer ID",
                            "required": True
                        }
                    ],
                    "sql_template": "SELECT * FROM customers WHERE id = %(customer_id)s"
                },
                {
                    "id": "find_recent_orders",
                    "description": "Find recent orders",
                    "nl_examples": ["Show recent orders", "Get orders from last week"],
                    "tags": ["orders", "recent"],
                    "parameters": [
                        {
                            "name": "days",
                            "type": "integer",
                            "description": "Number of days",
                            "default": 7
                        }
                    ],
                    "sql_template": "SELECT * FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '%(days)s days'"
                }
            ]
        }
    
    @pytest.fixture
    def temp_config_files(self, sample_domain_config, sample_template_library):
        """Create temporary YAML config files"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as domain_file:
            yaml.dump(sample_domain_config, domain_file)
            domain_path = domain_file.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as template_file:
            yaml.dump(sample_template_library, template_file)
            template_path = template_file.name
            
        yield domain_path, template_path
        
        # Cleanup
        os.unlink(domain_path)
        os.unlink(template_path)
    
    def test_adapter_initialization(self):
        """Test basic adapter initialization"""
        adapter = IntentAdapter(
            confidence_threshold=0.8,
            verbose=True
        )
        
        assert adapter.confidence_threshold == 0.8
        assert adapter.verbose == True
        assert adapter.domain_config is None
        assert adapter.template_library is None
    
    def test_adapter_with_config_files(self, temp_config_files):
        """Test adapter initialization with config files"""
        domain_path, template_path = temp_config_files
        
        adapter = IntentAdapter(
            domain_config_path=domain_path,
            template_library_path=template_path,
            confidence_threshold=0.75
        )
        
        assert adapter.domain_config is not None
        assert adapter.domain_config['domain_name'] == "Test E-Commerce"
        assert adapter.template_library is not None
        assert any(t['id'] == 'find_customer_by_id' for t in adapter.template_library['templates'])
    
    def test_get_template_by_id(self, temp_config_files):
        """Test retrieving a template by ID"""
        domain_path, template_path = temp_config_files
        
        adapter = IntentAdapter(
            template_library_path=template_path
        )
        
        template = adapter.get_template_by_id('find_customer_by_id')
        assert template is not None
        assert template['description'] == "Find a customer by their ID"
        assert len(template['parameters']) == 1
        
        # Test non-existent template
        assert adapter.get_template_by_id('non_existent') is None
    
    def test_get_all_templates(self, temp_config_files):
        """Test retrieving all templates"""
        domain_path, template_path = temp_config_files
        
        adapter = IntentAdapter(
            template_library_path=template_path
        )
        
        templates = adapter.get_all_templates()
        assert len(templates) == 2
        
        # Check that IDs are included
        template_ids = [t['id'] for t in templates]
        assert 'find_customer_by_id' in template_ids
        assert 'find_recent_orders' in template_ids
    
    def test_format_document_single_result(self):
        """Test formatting a single result document"""
        adapter = IntentAdapter()
        
        metadata = {
            'template_id': 'test_template',
            'query_intent': 'Find customer',
            'results': [
                {
                    'customer_id': 123,
                    'customer_name': 'John Doe',
                    'email': 'john@example.com'
                }
            ]
        }
        
        formatted = adapter.format_document("Raw SQL result", metadata)
        
        assert formatted['template_id'] == 'test_template'
        assert formatted['query_intent'] == 'Find customer'
        assert formatted['result_count'] == 1
        assert 'Customer Id: 123' in formatted['content']
        assert 'Customer Name: John Doe' in formatted['content']
    
    def test_format_document_multiple_results(self):
        """Test formatting multiple result documents"""
        adapter = IntentAdapter()
        
        metadata = {
            'results': [
                {'id': 1, 'name': 'Item 1'},
                {'id': 2, 'name': 'Item 2'},
                {'id': 3, 'name': 'Item 3'}
            ]
        }
        
        formatted = adapter.format_document("Raw results", metadata)
        
        assert formatted['result_count'] == 3
        assert 'Found 3 results:' in formatted['content']
        assert 'Result 1:' in formatted['content']
        assert 'Result 2:' in formatted['content']
        assert 'Result 3:' in formatted['content']
    
    def test_format_document_no_results(self):
        """Test formatting when no results found"""
        adapter = IntentAdapter()
        
        metadata = {
            'results': []
        }
        
        formatted = adapter.format_document("", metadata)
        
        assert formatted['result_count'] == 0
        assert formatted['content'] == "No results found for the query."
    
    def test_extract_direct_answer(self):
        """Test extracting direct answer from context"""
        adapter = IntentAdapter(confidence_threshold=0.7)
        
        # High confidence result
        context = [{
            'content': 'Customer found: John Doe',
            'confidence': 0.9
        }]
        
        answer = adapter.extract_direct_answer(context)
        assert answer == 'Customer found: John Doe'
        
        # Low confidence result
        context = [{
            'content': 'Maybe John Doe',
            'confidence': 0.5
        }]
        
        answer = adapter.extract_direct_answer(context)
        assert answer is None
        
        # Empty context
        assert adapter.extract_direct_answer([]) is None
    
    def test_apply_domain_filtering(self):
        """Test domain-specific filtering"""
        adapter = IntentAdapter(confidence_threshold=0.6)
        
        context_items = [
            {'content': 'Result 1', 'confidence': 0.9},
            {'content': 'Result 2', 'confidence': 0.7},
            {'content': 'Result 3', 'confidence': 0.5},  # Below threshold
            {'content': 'Result 4', 'confidence': 0.8}
        ]
        
        filtered = adapter.apply_domain_filtering(context_items, "test query")
        
        assert len(filtered) == 3  # One item filtered out
        assert all(item['confidence'] >= 0.6 for item in filtered)
        assert filtered[0]['confidence'] == 0.9  # Highest first
        assert filtered[1]['confidence'] == 0.8
        assert filtered[2]['confidence'] == 0.7
    
    def test_invalid_config_path(self):
        """Test adapter with invalid config paths"""
        adapter = IntentAdapter(
            domain_config_path="/non/existent/path.yaml",
            template_library_path="/another/invalid/path.yaml"
        )
        
        # Should not raise error, just log warning
        assert adapter.domain_config is None
        assert adapter.template_library is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])