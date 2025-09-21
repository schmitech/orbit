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