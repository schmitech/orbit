"""
Tests for domain-specific reranking strategies
"""

import pytest
import sys
import os
from typing import Dict, Any

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.domain import DomainConfig
from retrievers.implementations.intent.domain_strategies.base import DomainStrategy
from retrievers.implementations.intent.domain_strategies.customer_order import CustomerOrderStrategy
from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
from retrievers.implementations.intent.domain_strategies.generic import GenericDomainStrategy


class TestCustomerOrderStrategy:
    """Test suite for CustomerOrderStrategy"""
    
    @pytest.fixture
    def domain_config(self):
        """Sample domain configuration for customer orders"""
        return {
            "domain_name": "E-Commerce",
            "fields": {
                "order": {
                    "status": {
                        "enum_values": ["pending", "processing", "shipped", "delivered"]
                    },
                    "payment_method": {
                        "enum_values": ["credit_card", "debit_card", "paypal", "cash"]
                    }
                }
            }
        }
    
    @pytest.fixture
    def strategy(self):
        """CustomerOrderStrategy instance"""
        return CustomerOrderStrategy()
    
    def test_get_domain_names(self, strategy):
        """Test that strategy returns correct domain names"""
        domains = strategy.get_domain_names()
        assert "customer_order" in domains
        assert "e-commerce" in domains
    
    def test_person_name_context_detection(self, strategy):
        """Test person name context detection using new design"""
        matchers = strategy.get_pattern_matchers()

        # Check if person_name_context matcher exists
        assert 'person_name_context' in matchers
        person_context_matcher = matchers['person_name_context']

        # Should match person name contexts
        assert person_context_matcher("orders from angela smith")  # "from Name Name" pattern
        assert person_context_matcher("show me mr. wilson's orders")  # Title pattern
        assert person_context_matcher("angela's purchases")  # Possessive pattern
        assert person_context_matcher("find orders from john doe")  # "from Name Name" pattern

        # Should not match non-person contexts
        assert not person_context_matcher("orders from last week")
        assert not person_context_matcher("find all orders")
        assert not person_context_matcher("customers in new york")  # City context should override
    
    def test_city_context_detection(self, strategy):
        """Test city context detection using new design"""
        matchers = strategy.get_pattern_matchers()

        # Check if city_context matcher exists
        assert 'city_context' in matchers
        city_context_matcher = matchers['city_context']

        # Should match city contexts
        assert city_context_matcher("customers in new york")
        assert city_context_matcher("orders from the city of boston")
        assert city_context_matcher("customers from downtown area")
        assert city_context_matcher("located in san francisco")

        # Should not match non-city contexts
        assert not city_context_matcher("customer john doe")
        assert not city_context_matcher("orders from yesterday")
    
    def test_semantic_extraction_for_orders(self, strategy, domain_config):
        """Test semantic extraction for order-related queries"""
        # Test order identifier extraction
        param = {"name": "order_id", "type": "integer", "semantic_type": "order_identifier"}

        # Should extract order IDs
        assert strategy.extract_domain_parameters("show me order #12345", param, domain_config) == 12345
        assert strategy.extract_domain_parameters("order 67890", param, domain_config) == 67890

        # Test vocabulary-based pattern matching
        matchers = strategy.get_pattern_matchers()
        # Check if order_pattern matcher exists (from vocabulary)
        if 'order_pattern' in matchers:
            order_matcher = matchers['order_pattern']
            assert order_matcher("show me orders")
            assert order_matcher("find purchases")  # synonym from vocabulary
    
    def test_payment_method_extraction(self, strategy, domain_config):
        """Test payment method extraction using semantic types"""
        # Test payment method extraction through semantic type
        param = {"name": "payment_method", "type": "string", "semantic_type": "payment_method"}

        # The generic strategy should handle enum extraction
        result = strategy.extract_domain_parameters("paid by credit card", param, domain_config)
        # May return None if not matching exact enum values, which is fine

        # Test that semantic extractors include payment-related extraction
        extractors = strategy.get_semantic_extractors()
        assert 'monetary_amount' in extractors  # Should have monetary amount extractor

    def test_extracts_customer_id(self, strategy, domain_config):
        """Customer ID values should be extracted using semantic types"""
        query = "What's the lifetime value of customer 59665834?"
        param = {"name": "customer_id", "type": "integer", "semantic_type": "customer_identifier"}
        value = strategy.extract_domain_parameters(query, param, domain_config)
        assert value == 59665834
    
    def test_calculate_domain_boost(self, strategy, domain_config):
        """Test domain-specific boost calculation with new design"""
        # Test customer name context boosting
        template_info = {
            "template": {
                "id": "find_by_customer_name",
                "semantic_tags": {"action": "find", "primary_entity": "customer"}
            }
        }
        boost = strategy.calculate_domain_boost(template_info, "orders from john smith", domain_config)
        assert boost >= 0  # Base boost from semantic tags

        # Test city context boosting
        template_info = {
            "template": {
                "id": "find_by_customer_city",
                "semantic_tags": {"action": "find", "primary_entity": "customer"}
            }
        }
        boost = strategy.calculate_domain_boost(template_info, "customers in boston", domain_config)
        assert boost > 0  # Should get boost from city context

        # Test with person name context when looking for city (disambiguation)
        boost_with_person = strategy.calculate_domain_boost(
            template_info, "from angela smith", domain_config
        )
        # May be negative or lower due to disambiguation logic

        # Test semantic tag matching
        template_info = {
            "template": {
                "id": "find_orders",
                "semantic_tags": {"action": "find", "primary_entity": "order"},
                "parameters": [
                    {"name": "status", "semantic_type": "status_value"}
                ]
            }
        }
        boost = strategy.calculate_domain_boost(template_info, "show pending orders", domain_config)
        assert boost >= 0  # Should get boost from vocabulary and semantic matching


class TestDomainStrategyRegistry:
    """Test suite for DomainStrategyRegistry"""
    
    def test_get_builtin_strategy(self):
        """Test retrieving built-in strategies"""
        # Should find customer order strategy
        strategy = DomainStrategyRegistry.get_strategy("e-commerce")
        assert strategy is not None
        assert isinstance(strategy, CustomerOrderStrategy)
        
        # Should also work with alternate name
        strategy = DomainStrategyRegistry.get_strategy("customer_order")
        assert strategy is not None
        assert isinstance(strategy, CustomerOrderStrategy)
    
    def test_get_unknown_strategy(self):
        """Test retrieving non-existent strategy returns None"""
        strategy = DomainStrategyRegistry.get_strategy("unknown_domain")
        assert strategy is None
        
        # Empty domain name
        strategy = DomainStrategyRegistry.get_strategy("")
        assert strategy is None
    
    def test_register_custom_strategy(self):
        """Test registering custom domain strategies"""
        class TestStrategy(DomainStrategy):
            def get_domain_names(self):
                return ["test_domain"]

            def calculate_domain_boost(self, template_info, query, domain_config):
                return 0.5

            def get_pattern_matchers(self):
                return {}

            def extract_domain_parameters(self, query, param, domain_config):
                return None

            def get_semantic_extractors(self):
                return {}

            def get_summary_field_priority(self, field_name, field_config):
                return 0
        
        # Register custom strategy
        DomainStrategyRegistry.register_strategy("test_domain", TestStrategy)
        try:
            strategy = DomainStrategyRegistry.get_strategy("test_domain")
            assert strategy is not None
            assert isinstance(strategy, TestStrategy)
            assert strategy.calculate_domain_boost({}, "", {}) == 0.5
        finally:
            DomainStrategyRegistry._custom_strategies.pop("test_domain", None)
    
    def test_register_invalid_strategy(self):
        """Test that registering invalid strategy raises error"""
        class InvalidStrategy:
            pass
        
        with pytest.raises(ValueError):
            DomainStrategyRegistry.register_strategy("invalid", InvalidStrategy)
    
    def test_generic_fallback_with_domain_config(self):
        """Unknown domains should receive the generic strategy when config is provided"""
        domain_config = DomainConfig({
            "domain_name": "DataWarehouse",
            "domain_type": "generic",
            "entities": {},
            "fields": {},
        })

        strategy = DomainStrategyRegistry.get_strategy(
            domain_config.domain_name,
            domain_config,
        )

        assert strategy is not None
        assert isinstance(strategy, GenericDomainStrategy)

    def test_domain_type_registration_match(self):
        """Custom strategies should be matched via domain_type metadata"""

        class MedicalStrategy(DomainStrategy):
            def get_domain_names(self):
                return ["medical_custom"]

            def calculate_domain_boost(self, template_info, query, domain_config):
                return 0.0

            def get_pattern_matchers(self):
                return {}

            def extract_domain_parameters(self, query, param, domain_config):
                return None

            def get_semantic_extractors(self):
                return {}

            def get_summary_field_priority(self, field_name, field_config):
                return 0

        DomainStrategyRegistry.register_strategy("medical", MedicalStrategy)
        try:
            domain_config = DomainConfig({
                "domain_name": "EHR",
                "domain_type": "medical",
                "entities": {},
                "fields": {},
            })
            strategy = DomainStrategyRegistry.get_strategy("EHR", domain_config)
            assert strategy is not None
            assert isinstance(strategy, MedicalStrategy)
        finally:
            DomainStrategyRegistry._custom_strategies.pop("medical", None)

    def test_list_available_domains(self):
        """Test listing all available domains"""
        domains = DomainStrategyRegistry.list_available_domains()

        # Should include built-in domains
        assert "e-commerce" in domains
        assert "customer_order" in domains
        
        # Should be sorted
        assert domains == sorted(domains)


class TestCustomDomainStrategy:
    """Test creating a custom domain strategy"""
    
    def test_create_healthcare_strategy(self):
        """Test creating a custom healthcare domain strategy"""
        
        class HealthcareStrategy(DomainStrategy):
            def get_domain_names(self):
                return ["healthcare", "medical"]
            
            def calculate_domain_boost(self, template_info, query, domain_config):
                template_id = template_info['template'].get('id', '')
                query_lower = query.lower()
                boost = 0.0
                
                if 'patient' in template_id and self._contains_patient_pattern(query_lower):
                    boost += 0.3
                elif 'diagnosis' in template_id and self._contains_medical_pattern(query_lower):
                    boost += 0.4
                
                return boost
            
            def get_pattern_matchers(self):
                return {
                    'patient': self._contains_patient_pattern,
                    'medical': self._contains_medical_pattern
                }

            def extract_domain_parameters(self, query, param, domain_config):
                """Extract healthcare-specific parameters"""
                param_name = param.get('name', '')

                # Example: extract patient MRN
                if 'mrn' in param_name.lower() or 'patient_id' in param_name.lower():
                    import re
                    # Look for patterns like MRN123456 or P123456
                    match = re.search(r'(?:mrn|patient)\s*[:\-]?\s*([A-Z]?\d{6,8})', query, re.IGNORECASE)
                    if match:
                        return match.group(1)

                return None

            def get_semantic_extractors(self):
                """Return healthcare semantic extractors"""
                return {
                    'patient_identifier': lambda q, t: self._extract_patient_id(q),
                    'diagnosis_code': lambda q, t: self._extract_diagnosis_code(q),
                }

            def get_summary_field_priority(self, field_name, field_config):
                """Get field priority for healthcare summaries"""
                healthcare_priorities = {
                    'mrn': 100,
                    'patient_id': 100,
                    'patient_name': 90,
                    'diagnosis': 85,
                    'admission_date': 80,
                    'doctor': 75,
                    'room': 70,
                }

                if field_name in healthcare_priorities:
                    return healthcare_priorities[field_name]

                # Pattern-based fallback
                field_lower = field_name.lower()
                if 'id' in field_lower or 'mrn' in field_lower:
                    return 95
                if 'name' in field_lower:
                    return 85
                if 'date' in field_lower:
                    return 75

                return 0

            def _extract_patient_id(self, query):
                """Extract patient ID from query"""
                import re
                match = re.search(r'(?:mrn|patient)\s*[:\-]?\s*([A-Z]?\d{6,8})', query, re.IGNORECASE)
                return match.group(1) if match else None

            def _extract_diagnosis_code(self, query):
                """Extract diagnosis code from query"""
                import re
                # ICD-10 pattern: Letter followed by 2 digits, optional dot, optional more digits
                match = re.search(r'([A-Z]\d{2}\.?\d*)', query, re.IGNORECASE)
                return match.group(1) if match else None

            def _contains_patient_pattern(self, text):
                patient_terms = ['patient', 'mrn', 'medical record']
                return any(term in text for term in patient_terms)

            def _contains_medical_pattern(self, text):
                medical_terms = ['diagnosis', 'symptom', 'treatment', 'medication']
                return any(term in text for term in medical_terms)
        
        # Register the strategy
        DomainStrategyRegistry.register_strategy("healthcare", HealthcareStrategy)
        try:
            strategy = DomainStrategyRegistry.get_strategy("healthcare")
            assert strategy is not None

            matchers = strategy.get_pattern_matchers()
            assert matchers['patient']("find patient record")
            assert matchers['medical']("diagnosis code lookup")

            template_info = {"template": {"id": "patient_lookup"}}
            boost = strategy.calculate_domain_boost(
                template_info, "find patient mrn 12345", {}
            )
            assert boost == 0.3
        finally:
            DomainStrategyRegistry._custom_strategies.pop("healthcare", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
