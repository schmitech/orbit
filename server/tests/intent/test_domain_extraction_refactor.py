#!/usr/bin/env python
"""
Test script to verify domain-specific parameter extraction is working
after the refactoring to use DomainStrategy pattern.
"""

import pytest
import asyncio
from retrievers.implementations.intent.domain.extraction.extractor import DomainParameterExtractor

# Mock inference client for testing
class MockInferenceClient:
    async def generate(self, *args, **kwargs):
        return {"extracted_value": None}

class TestDomainExtractionRefactor:
    """Test domain extraction after refactoring to use DomainStrategy"""

    @pytest.mark.asyncio
    async def test_customer_order_extraction(self):
        """Test that customer order domain extraction still works after refactoring"""

        # Create a simple domain config for e-commerce
        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {
                "order": {
                    "name": "order",
                    "fields": {
                        "id": {
                            "name": "id",
                            "data_type": "integer",
                            "searchable": True,
                            "filterable": True
                        }
                    }
                }
            }
        }

        # Initialize extractor
        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        # Test cases for customer order domain
        test_cases = [
            ("Show me order #12345", {"name": "order_id", "type": "integer"}, 12345),
            ("Orders from the last 30 days", {"name": "days_back", "type": "integer"}, 30),
            ("Orders over $500", {"name": "min_amount", "type": "decimal"}, 500.0),
            ("Show order 9876", {"name": "order_id", "type": "integer"}, 9876),
            ("Orders from last week", {"name": "days_back", "type": "integer"}, 7),
            ("Total exceeds $1,000.50", {"name": "amount", "type": "decimal"}, 1000.50),
        ]

        for query, param, expected in test_cases:
            # Extract using the refactored system
            result = await extractor.extract_parameters(
                query,
                {"parameters": [param]}
            )

            actual = result.get(param["name"])
            assert actual == expected, f"Failed for query '{query}': expected {expected}, got {actual}"

    @pytest.mark.asyncio
    async def test_extraction_with_multiple_order_ids(self):
        """Test extraction of multiple order IDs"""

        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {}
        }

        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        # Test multiple order IDs
        result = await extractor.extract_parameters(
            "Show me orders 123, 456, 789",
            {"parameters": [{"name": "order_ids", "type": "string"}]}
        )

        assert result.get("order_ids") == "123,456,789"

    @pytest.mark.asyncio
    async def test_extraction_with_order_range(self):
        """Test extraction of order ID ranges"""

        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {}
        }

        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        # Test order range
        result = await extractor.extract_parameters(
            "Orders between 100 and 105",
            {"parameters": [{"name": "order_ids", "type": "string"}]}
        )

        # Should generate comma-separated list for small ranges
        assert result.get("order_ids") == "100,101,102,103,104,105"

    @pytest.mark.asyncio
    async def test_time_period_extraction(self):
        """Test extraction of time periods"""

        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {}
        }

        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        time_period_tests = [
            ("last month", 30),
            ("past quarter", 90),
            ("this year", 365),
            ("yesterday", 1),
        ]

        for query, expected_days in time_period_tests:
            result = await extractor.extract_parameters(
                f"Orders from {query}",
                {"parameters": [{"name": "days_back", "type": "integer"}]}
            )
            assert result.get("days_back") == expected_days, f"Failed for '{query}'"

    @pytest.mark.asyncio
    async def test_generic_extraction_fallback(self):
        """Test that generic extraction still works for non-domain-specific params"""

        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {}
        }

        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        # Test email extraction (generic)
        result = await extractor.extract_parameters(
            "Customer email is john.doe@example.com",
            {"parameters": [{"name": "customer_email", "type": "string"}]}
        )
        assert result.get("customer_email") == "john.doe@example.com"

        # Test date extraction (generic)
        result = await extractor.extract_parameters(
            "Orders from 2024-01-15",
            {"parameters": [{"name": "start_date", "type": "date"}]}
        )
        assert result.get("start_date") == "2024-01-15"

    @pytest.mark.asyncio
    async def test_domain_strategy_is_used(self):
        """Verify that CustomerOrderStrategy is actually being used"""

        domain_config = {
            "domain_name": "E-Commerce",
            "entities": {}
        }

        extractor = DomainParameterExtractor(
            MockInferenceClient(),
            domain_config
        )

        # Check that the strategy was loaded
        assert extractor.domain_strategy is not None
        assert extractor.domain_strategy.__class__.__name__ == "CustomerOrderStrategy"

        # Verify the strategy is passed to ValueExtractor
        assert extractor.value_extractor.domain_strategy is not None
        assert extractor.value_extractor.domain_strategy == extractor.domain_strategy

    def test_response_formatter_with_domain_strategy(self):
        """Test that ResponseFormatter uses domain strategy for field prioritization"""
        from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
        from retrievers.implementations.intent.domain_strategies.customer_order import CustomerOrderStrategy
        from retrievers.implementations.intent.domain import DomainConfig

        # Create domain config
        domain_config = DomainConfig({
            "domain_name": "E-Commerce",
            "entities": {
                "order": {
                    "name": "order",
                    "fields": {
                        "order_id": {"name": "order_id", "data_type": "integer"},
                        "customer_name": {"name": "customer_name", "data_type": "string"},
                        "total": {"name": "total", "data_type": "decimal"},
                        "status": {"name": "status", "data_type": "string"},
                        "order_date": {"name": "order_date", "data_type": "date"},
                        "shipping_address": {"name": "shipping_address", "data_type": "string"},
                    }
                }
            }
        })

        # Create domain strategy
        strategy = CustomerOrderStrategy()

        # Test with domain strategy
        formatter_with_strategy = ResponseFormatter(domain_config, strategy)
        
        # Sample result data
        sample_result = {
            "order_id": 12345,
            "customer_name": "John Doe",
            "total": 99.99,
            "status": "shipped",
            "order_date": "2024-01-15",
            "shipping_address": "123 Main St"
        }

        # Get summary fields using strategy
        summary_fields = formatter_with_strategy._get_summary_fields(sample_result)
        
        # Verify that high-priority fields are selected first
        # Based on CustomerOrderStrategy priorities: order_id=100, customer_name=90, total=85, status=80
        assert "order_id" in summary_fields
        assert "customer_name" in summary_fields
        assert "total" in summary_fields
        assert "status" in summary_fields
        
        # Verify order_id comes first (highest priority)
        assert summary_fields[0] == "order_id"

    def test_response_formatter_without_domain_strategy(self):
        """Test that ResponseFormatter falls back to generic prioritization without strategy"""
        from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
        from retrievers.implementations.intent.domain import DomainConfig

        # Create domain config
        domain_config = DomainConfig({
            "domain_name": "Generic",
            "entities": {
                "record": {
                    "name": "record",
                    "fields": {
                        "id": {"name": "id", "data_type": "integer"},
                        "name": {"name": "name", "data_type": "string"},
                        "description": {"name": "description", "data_type": "string"},
                        "created_at": {"name": "created_at", "data_type": "date"},
                    }
                }
            }
        })

        # Test without domain strategy
        formatter = ResponseFormatter(domain_config, None)
        
        # Sample result data
        sample_result = {
            "id": 1,
            "name": "Test Record",
            "description": "A test record",
            "created_at": "2024-01-15"
        }

        # Get summary fields using generic fallback
        summary_fields = formatter._get_summary_fields(sample_result)
        
        # Verify that generic patterns are used
        # Generic priorities: id=50, name=45, date=35
        assert "id" in summary_fields
        assert "name" in summary_fields
        assert "created_at" in summary_fields
        
        # Verify id comes first (highest generic priority)
        assert summary_fields[0] == "id"

    def test_response_formatter_field_priority_hierarchy(self):
        """Test that field priority hierarchy works correctly"""
        from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
        from retrievers.implementations.intent.domain_strategies.customer_order import CustomerOrderStrategy
        from retrievers.implementations.intent.domain import DomainConfig

        # Create domain config
        domain_config = DomainConfig({
            "domain_name": "E-Commerce",
            "entities": {
                "order": {
                    "name": "order",
                    "fields": {
                        "order_id": {"name": "order_id", "data_type": "integer"},
                        "customer_name": {"name": "customer_name", "data_type": "string"},
                        "total": {"name": "total", "data_type": "decimal"},
                        "status": {"name": "status", "data_type": "string"},
                        "order_date": {"name": "order_date", "data_type": "date"},
                        "shipping_address": {"name": "shipping_address", "data_type": "string"},
                        "payment_method": {"name": "payment_method", "data_type": "string"},
                        "email": {"name": "email", "data_type": "string"},
                        "city": {"name": "city", "data_type": "string"},
                    }
                }
            }
        })

        strategy = CustomerOrderStrategy()
        formatter = ResponseFormatter(domain_config, strategy)
        
        # Sample result with many fields
        sample_result = {
            "order_id": 12345,
            "customer_name": "John Doe",
            "total": 99.99,
            "status": "shipped",
            "order_date": "2024-01-15",
            "shipping_address": "123 Main St",
            "payment_method": "credit_card",
            "email": "john@example.com",
            "city": "New York"
        }

        summary_fields = formatter._get_summary_fields(sample_result)
        
        # Verify fields are ordered by priority (highest first)
        # Expected order based on CustomerOrderStrategy priorities:
        # order_id=100, customer_name=90, total=85, status=80, order_date=75, payment_method=70, email=65, shipping_address=60, city=50
        expected_order = ["order_id", "customer_name", "total", "status", "order_date"]
        
        # Check that the first 5 fields match expected order
        assert summary_fields[:5] == expected_order