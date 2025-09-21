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
    
    def test_person_name_pattern_detection(self, strategy):
        """Test person name pattern detection"""
        matchers = strategy.get_pattern_matchers()
        person_matcher = matchers['person_name']
        
        # Should match person patterns
        assert person_matcher("orders from Angela Smith")  # "from Name Name" pattern
        assert person_matcher("show me mr. wilson's orders")  # Title pattern
        assert person_matcher("angela's purchases")  # Possessive pattern
        assert person_matcher("find orders from John Doe")  # "from Name Name" pattern
        
        # Should not match non-person patterns  
        assert not person_matcher("find customer John Doe")  # Just "customer" is not enough
        assert not person_matcher("orders from last week")
        assert not person_matcher("find all orders")
        assert not person_matcher("customers in New York")  # City pattern should override
    
    def test_city_pattern_detection(self, strategy):
        """Test city pattern detection"""
        matchers = strategy.get_pattern_matchers()
        city_matcher = matchers['city']
        
        # Should match city patterns
        assert city_matcher("customers in New York")
        assert city_matcher("orders from the city of Boston")
        assert city_matcher("customers from downtown area")
        assert city_matcher("located in San Francisco")
        
        # Should not match non-city patterns
        assert not city_matcher("customer John Doe")
        assert not city_matcher("orders from yesterday")
    
    def test_order_pattern_detection(self, strategy, domain_config):
        """Test order pattern detection"""
        matchers = strategy.get_pattern_matchers()
        order_matcher = matchers['order']
        
        # Should match order patterns
        assert order_matcher("show me orders", domain_config)
        assert order_matcher("find purchases", domain_config)
        assert order_matcher("pending transactions", domain_config)
        assert order_matcher("shipped items", domain_config)
        
        # Should not match non-order patterns
        assert not order_matcher("find customers", domain_config)
    
    def test_payment_pattern_detection(self, strategy, domain_config):
        """Test payment pattern detection"""
        matchers = strategy.get_pattern_matchers()
        payment_matcher = matchers['payment']
        
        # Should match payment patterns
        assert payment_matcher("paid by credit card", domain_config)
        assert payment_matcher("paypal payments", domain_config)
        assert payment_matcher("cash transactions", domain_config)
        
        # Should not match non-payment patterns
        assert not payment_matcher("find orders", domain_config)

    def test_extracts_customer_id(self, strategy):
        """Customer ID values should be extracted for numeric queries"""
        query = "What's the lifetime value of customer 59665834?"
        param = {"name": "customer_id", "type": "integer"}
        value = strategy.extract_domain_parameters(query, param, {})
        assert value == 59665834
    
    def test_calculate_domain_boost(self, strategy, domain_config):
        """Test domain-specific boost calculation"""
        # Test customer name boosting
        template_info = {
            "template": {"id": "find_by_customer_name"}
        }
        boost = strategy.calculate_domain_boost(template_info, "orders from John Smith", domain_config)
        assert boost > 0
        
        # Test city boosting
        template_info = {
            "template": {"id": "find_by_customer_city"}
        }
        boost = strategy.calculate_domain_boost(template_info, "customers in Boston", domain_config)
        assert boost > 0
        
        # Test city penalty when person name detected
        boost_with_person = strategy.calculate_domain_boost(
            template_info, "from Angela Smith", domain_config
        )
        assert boost_with_person < 0  # Should be negative due to penalty
        
        # Test order pattern boosting
        template_info = {
            "template": {"id": "find_orders"}
        }
        boost = strategy.calculate_domain_boost(template_info, "show pending orders", domain_config)
        assert boost > 0
        
        # Test payment pattern boosting
        template_info = {
            "template": {"id": "payment_summary"}
        }
        boost = strategy.calculate_domain_boost(template_info, "credit card payments", domain_config)
        assert boost > 0


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
