"""
Tests for domain-aware semantic components
"""

import pytest
import sys
import os
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock, AsyncMock

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.domain_aware_extractor import DomainAwareParameterExtractor
from retrievers.implementations.intent.domain_aware_response_generator import DomainAwareResponseGenerator
from retrievers.implementations.intent.template_reranker import TemplateReranker
from retrievers.implementations.intent.intent_plugin_system import (
    IntentPluginManager, QueryNormalizationPlugin, ResultEnrichmentPlugin, 
    ResponseEnhancementPlugin, IntentPluginContext
)


class TestDomainAwareParameterExtractor:
    """Test suite for DomainAwareParameterExtractor"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration for testing"""
        return {
            "domain_name": "E-Commerce",
            "entities": {
                "customer": {
                    "name": "customer",
                    "entity_type": "primary",
                    "table_name": "customers"
                }
            },
            "fields": {
                "customer": {
                    "id": {
                        "name": "id",
                        "data_type": "integer",
                        "db_column": "id",
                        "searchable": True,
                        "aliases": ["customer_id", "cust_id"]
                    },
                    "email": {
                        "name": "email",
                        "data_type": "string",
                        "db_column": "email",
                        "searchable": True
                    }
                }
            },
            "vocabulary": {
                "entity_synonyms": {
                    "customer": ["client", "buyer", "user"]
                },
                "action_verbs": {
                    "find": ["show", "get", "list", "display"]
                },
                "time_expressions": {
                    "last week": "7",
                    "last month": "30"
                }
            }
        }
    
    @pytest.fixture
    def mock_inference_client(self):
        """Mock inference client"""
        client = AsyncMock()
        client.generate = AsyncMock(return_value='{"customer_id": 123}')
        return client
    
    def test_extractor_initialization(self, mock_inference_client, sample_domain_config):
        """Test extractor initialization with domain config"""
        extractor = DomainAwareParameterExtractor(mock_inference_client, sample_domain_config)
        
        assert extractor.inference_client == mock_inference_client
        assert extractor.domain_config == sample_domain_config
        assert len(extractor.patterns) > 0  # Should have built patterns
    
    def test_pattern_building(self, mock_inference_client, sample_domain_config):
        """Test that extraction patterns are built correctly"""
        extractor = DomainAwareParameterExtractor(mock_inference_client, sample_domain_config)
        
        # Should have patterns for searchable fields
        assert "customer.id" in extractor.patterns
        assert "customer.email" in extractor.patterns
    
    @pytest.mark.asyncio
    async def test_extract_customer_id(self, mock_inference_client, sample_domain_config):
        """Test extracting customer ID from query"""
        extractor = DomainAwareParameterExtractor(mock_inference_client, sample_domain_config)
        
        template = {
            "parameters": [
                {
                    "name": "customer_id",
                    "type": "integer",
                    "required": True
                }
            ]
        }
        
        # Test various ID patterns
        test_cases = [
            "Show me customer 123",
            "Find customer id 456",
            "Get customer #789",
            "Client 999 details"
        ]
        
        for query in test_cases:
            params = await extractor.extract_parameters(query, template)
            if 'customer_id' in params:
                assert isinstance(params['customer_id'], int)
                assert params['customer_id'] > 0
    
    def test_extract_time_period(self, mock_inference_client, sample_domain_config):
        """Test time period extraction"""
        extractor = DomainAwareParameterExtractor(mock_inference_client, sample_domain_config)
        
        # Test vocabulary-based extraction
        assert extractor._extract_time_period("orders from last week") == 7
        assert extractor._extract_time_period("data from last month") == 30
        
        # Test pattern-based extraction
        assert extractor._extract_time_period("last 14 days") == 14
        assert extractor._extract_time_period("past 3 weeks") == 21
    
    def test_parameter_validation(self, mock_inference_client, sample_domain_config):
        """Test parameter validation"""
        extractor = DomainAwareParameterExtractor(mock_inference_client, sample_domain_config)
        
        template = {
            "parameters": [
                {
                    "name": "customer_id",
                    "type": "integer",
                    "required": True
                }
            ]
        }
        
        # Valid parameters
        params = {"customer_id": 123}
        is_valid, errors = extractor.validate_parameters(params, template)
        assert is_valid
        assert len(errors) == 0
        
        # Missing required parameter
        params = {}
        is_valid, errors = extractor.validate_parameters(params, template)
        assert not is_valid
        assert len(errors) > 0


class TestDomainAwareResponseGenerator:
    """Test suite for DomainAwareResponseGenerator"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration"""
        return {
            "domain_name": "E-Commerce",
            "description": "Customer order management",
            "entities": {
                "customer": {
                    "description": "Customer information"
                }
            },
            "fields": {
                "customer": {
                    "id": {
                        "name": "id",
                        "data_type": "integer"
                    },
                    "total": {
                        "name": "total",
                        "data_type": "decimal",
                        "display_format": "currency"
                    }
                }
            }
        }
    
    @pytest.fixture
    def mock_inference_client(self):
        """Mock inference client"""
        client = AsyncMock()
        client.generate = AsyncMock(return_value="Generated response from LLM")
        return client
    
    @pytest.mark.asyncio
    async def test_generator_initialization(self, mock_inference_client, sample_domain_config):
        """Test generator initialization"""
        generator = DomainAwareResponseGenerator(mock_inference_client, sample_domain_config)
        
        assert generator.inference_client == mock_inference_client
        assert generator.domain_config == sample_domain_config
    
    def test_format_results_for_domain(self, mock_inference_client, sample_domain_config):
        """Test result formatting with domain configuration"""
        generator = DomainAwareResponseGenerator(mock_inference_client, sample_domain_config)
        
        results = [
            {"id": 123, "total": 150.75},
            {"id": 456, "total": 299.99}
        ]
        
        template = {"description": "Test template"}
        formatted = generator._format_results_for_domain(results, template)
        
        assert len(formatted) == 2
        assert formatted[0]["total"] == "$150.75"  # Currency formatting applied
        assert formatted[1]["total"] == "$299.99"
    
    @pytest.mark.asyncio
    async def test_generate_summary_response(self, mock_inference_client, sample_domain_config):
        """Test summary response generation"""
        generator = DomainAwareResponseGenerator(mock_inference_client, sample_domain_config)
        
        results = [{"id": 123, "name": "John Doe", "total": 100.50}]
        template = {"description": "Find customer", "result_format": "summary"}
        
        response = await generator.generate_response("Show customer 123", results, template)
        
        assert response == "Generated response from LLM"
        mock_inference_client.generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_error_response(self, mock_inference_client, sample_domain_config):
        """Test error response generation"""
        generator = DomainAwareResponseGenerator(mock_inference_client, sample_domain_config)
        
        response = await generator.generate_response("Test query", [], {}, error="Database error")
        
        assert response == "Generated response from LLM"
        mock_inference_client.generate.assert_called_once()


class TestTemplateReranker:
    """Test suite for TemplateReranker"""
    
    @pytest.fixture
    def sample_domain_config(self):
        """Sample domain configuration"""
        return {
            "domain_name": "E-Commerce",
            "vocabulary": {
                "entity_synonyms": {
                    "customer": ["client", "buyer", "user"]
                },
                "action_verbs": {
                    "find": ["show", "get", "list", "display"]
                }
            }
        }
    
    @pytest.fixture
    def sample_templates(self):
        """Sample templates for reranking"""
        return [
            {
                "template": {
                    "id": "find_customer",
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "customer"
                    },
                    "tags": ["customer", "lookup"],
                    "nl_examples": ["Show customer details", "Find customer info"]
                },
                "similarity": 0.6
            },
            {
                "template": {
                    "id": "find_orders",
                    "semantic_tags": {
                        "action": "find",
                        "primary_entity": "order"
                    },
                    "tags": ["order", "history"],
                    "nl_examples": ["Show order history", "Find order details"]
                },
                "similarity": 0.7
            }
        ]
    
    def test_reranker_initialization(self, sample_domain_config):
        """Test reranker initialization"""
        reranker = TemplateReranker(sample_domain_config)
        assert reranker.domain_config == sample_domain_config
        assert reranker.domain_name == "e-commerce"
        assert reranker.domain_strategy is not None  # Should load CustomerOrderStrategy
    
    def test_rerank_templates(self, sample_domain_config, sample_templates):
        """Test template reranking with boosts"""
        reranker = TemplateReranker(sample_domain_config)
        
        query = "show me customer details"
        reranked = reranker.rerank_templates(sample_templates, query)
        
        # Should have boost applied
        customer_template = next(t for t in reranked if t['template']['id'] == 'find_customer')
        assert customer_template['similarity'] > 0.6  # Should be boosted
        assert 'boost_applied' in customer_template
    
    def test_rerank_templates_customer_name_vs_city(self, sample_domain_config):
        """Test domain-specific customer name vs city disambiguation"""
        import copy
        
        # Create templates with deep copy to avoid mutation issues
        templates_original = [
            {
                "template": {
                    "id": "find_by_customer_name",
                    "semantic_tags": {"primary_entity": "customer"},
                    "tags": ["name"]
                },
                "similarity": 0.5
            },
            {
                "template": {
                    "id": "find_by_customer_city",
                    "semantic_tags": {"primary_entity": "customer"},
                    "tags": ["city"]
                },
                "similarity": 0.5
            }
        ]
        
        reranker = TemplateReranker(sample_domain_config)
        
        # Debug: Check if domain strategy was loaded
        assert reranker.domain_strategy is not None, "Domain strategy should be loaded for E-Commerce domain"
        
        # Test with person name pattern
        templates = copy.deepcopy(templates_original)
        reranked = reranker.rerank_templates(templates, "find orders from John Smith")
        name_template = next(t for t in reranked if 'customer_name' in t['template']['id'])
        city_template = next(t for t in reranked if 'customer_city' in t['template']['id'])
        assert name_template['similarity'] > city_template['similarity'], \
            f"Expected name template ({name_template['similarity']}) > city template ({city_template['similarity']})"
        
        # Test with city pattern
        templates = copy.deepcopy(templates_original)
        reranked = reranker.rerank_templates(templates, "find customers in New York")
        name_template = next(t for t in reranked if 'customer_name' in t['template']['id'])
        city_template = next(t for t in reranked if 'customer_city' in t['template']['id'])
        assert city_template['similarity'] > name_template['similarity'], \
            f"Expected city template ({city_template['similarity']}) > name template ({name_template['similarity']})"
    
    def test_entity_boost_calculation(self, sample_domain_config):
        """Test entity boost calculation"""
        reranker = TemplateReranker(sample_domain_config)
        
        # Direct entity match
        boost = reranker._calculate_entity_boost("find customer", "customer")
        assert boost > 0
        
        # Synonym match
        boost = reranker._calculate_entity_boost("find client", "customer")
        assert boost > 0
        
        # No match
        boost = reranker._calculate_entity_boost("find order", "customer")
        assert boost == 0
    
    def test_text_similarity(self, sample_domain_config):
        """Test text similarity calculation"""
        reranker = TemplateReranker(sample_domain_config)
        
        # Identical texts
        sim = reranker._calculate_text_similarity("hello world", "hello world")
        assert sim == 1.0
        
        # Partial overlap
        sim = reranker._calculate_text_similarity("hello world", "hello there")
        assert 0 < sim < 1
        
        # No overlap
        sim = reranker._calculate_text_similarity("hello", "goodbye")
        assert sim == 0
    
    def test_reranker_without_domain_strategy(self):
        """Test reranker with no domain-specific strategy"""
        config = {
            "domain_name": "unknown_domain",
            "vocabulary": {
                "entity_synonyms": {},
                "action_verbs": {}
            }
        }
        
        reranker = TemplateReranker(config)
        assert reranker.domain_strategy is None  # No strategy for unknown domain
        
        # Should still work with generic reranking
        templates = [{
            "template": {
                "id": "test",
                "semantic_tags": {"primary_entity": "test"},
                "tags": ["test"]
            },
            "similarity": 0.5
        }]
        
        reranked = reranker.rerank_templates(templates, "test query")
        assert len(reranked) == 1


class TestIntentPluginSystem:
    """Test suite for Intent plugin system"""
    
    def test_plugin_manager_initialization(self):
        """Test plugin manager initialization"""
        manager = IntentPluginManager()
        assert len(manager.plugins) == 0
    
    def test_plugin_registration(self):
        """Test plugin registration and prioritization"""
        manager = IntentPluginManager()
        
        plugin1 = QueryNormalizationPlugin()
        plugin2 = ResultEnrichmentPlugin()
        
        manager.register_plugin(plugin1)
        manager.register_plugin(plugin2)
        
        assert len(manager.plugins) == 2
        # Should be sorted by priority
        assert manager.plugins[0].get_priority().value >= manager.plugins[1].get_priority().value
    
    def test_query_normalization_plugin(self):
        """Test query normalization plugin"""
        plugin = QueryNormalizationPlugin()
        context = IntentPluginContext(user_query="show me customer 123")
        
        normalized = plugin.pre_process_query("show me customer details", context)
        assert "find" in normalized
        assert "show me" not in normalized
    
    def test_result_enrichment_plugin(self):
        """Test result enrichment plugin"""
        plugin = ResultEnrichmentPlugin()
        context = IntentPluginContext(
            user_query="test",
            similarity_score=0.85,
            execution_time_ms=150.5
        )
        
        results = [{"id": 1, "name": "Test"}]
        enriched = plugin.post_process_results(results, context)
        
        assert len(enriched) == 1
        assert "metadata" in enriched[0]
        assert enriched[0]["metadata"]["processed_by"] == plugin.get_name()
        assert enriched[0]["metadata"]["query_similarity"] == 0.85
    
    def test_response_enhancement_plugin(self):
        """Test response enhancement plugin"""
        plugin = ResponseEnhancementPlugin()
        context = IntentPluginContext(
            user_query="test",
            template_id="find_customer",
            similarity_score=0.9
        )
        
        response = "Found customer details"
        enhanced = plugin.enhance_response(response, context)
        
        assert "find_customer" in enhanced
        assert "90.0%" in enhanced  # Confidence percentage
    
    def test_plugin_manager_execution(self):
        """Test plugin manager execution flow"""
        manager = IntentPluginManager()
        
        # Register plugins
        manager.register_plugin(QueryNormalizationPlugin())
        manager.register_plugin(ResultEnrichmentPlugin())
        manager.register_plugin(ResponseEnhancementPlugin())
        
        context = IntentPluginContext(
            user_query="show me customer",
            template_id="test_template",
            similarity_score=0.8
        )
        
        # Test pre-processing
        normalized_query = manager.execute_pre_processing("show me customer details", context)
        assert "find" in normalized_query
        
        # Test post-processing
        results = [{"id": 123}]
        processed_results = manager.execute_post_processing(results, context)
        assert "metadata" in processed_results[0]
        
        # Test response enhancement
        response = "Test response"
        enhanced_response = manager.execute_response_enhancement(response, context)
        assert "test_template" in enhanced_response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])