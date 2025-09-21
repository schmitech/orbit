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

    def test_response_formatter_with_generic_strategy(self):
        """Test that ResponseFormatter works with a generic domain strategy"""
        from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
        from retrievers.implementations.intent.domain import DomainConfig
        from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry

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

        # Get generic strategy (will be None for unknown domain)
        strategy = DomainStrategyRegistry.get_strategy("Generic")
        
        # Test with generic strategy (None)
        formatter = ResponseFormatter(domain_config, strategy)
        
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

    def test_semantic_types_in_domain_config(self):
        """Test that semantic types are properly parsed from domain configuration"""
        from retrievers.implementations.intent.domain import DomainConfig

        # Create domain config with semantic types
        config_with_semantics = {
            "domain_name": "E-Commerce",
            "domain_type": "ecommerce",
            "semantic_types": {
                "order_identifier": {
                    "description": "Unique identifier for an order",
                    "patterns": ["order", "id", "number"]
                },
                "monetary_amount": {
                    "description": "Currency amounts",
                    "patterns": ["amount", "total", "price", "cost"]
                },
                "person_name": {
                    "description": "Customer or person name",
                    "patterns": ["name", "customer", "client"]
                }
            },
            "entities": {
                "order": {
                    "name": "order"
                },
                "customer": {
                    "name": "customer"
                }
            },
            "fields": {
                "order": {
                    "id": {
                        "name": "id",
                        "data_type": "integer",
                        "semantic_type": "order_identifier",
                        "summary_priority": 10
                    },
                    "total": {
                        "name": "total",
                        "data_type": "decimal",
                        "semantic_type": "monetary_amount",
                        "summary_priority": 8
                    }
                },
                "customer": {
                    "name": {
                        "name": "name",
                        "data_type": "string",
                        "semantic_type": "person_name",
                        "summary_priority": 9,
                        "extraction_pattern": r"[A-Z][a-z]+ [A-Z][a-z]+",
                        "extraction_hints": {
                            "look_for_quotes": True,
                            "capitalization_required": True
                        }
                    }
                }
            }
        }

        domain_config = DomainConfig(config_with_semantics)

        # Test domain metadata
        assert domain_config.domain_type == "ecommerce"
        assert "order_identifier" in domain_config.semantic_types
        assert "monetary_amount" in domain_config.semantic_types
        assert "person_name" in domain_config.semantic_types

        # Test semantic type parsing
        semantic_type_config = domain_config.semantic_types["order_identifier"]
        assert semantic_type_config["description"] == "Unique identifier for an order"
        assert "order" in semantic_type_config["patterns"]

        # Test fields with semantic metadata
        order_id_field = domain_config.get_field("order", "id")
        assert order_id_field is not None
        assert order_id_field.semantic_type == "order_identifier"
        assert order_id_field.summary_priority == 10

        customer_name_field = domain_config.get_field("customer", "name")
        assert customer_name_field is not None
        assert customer_name_field.semantic_type == "person_name"
        assert customer_name_field.summary_priority == 9
        assert customer_name_field.extraction_pattern == r"[A-Z][a-z]+ [A-Z][a-z]+"
        assert customer_name_field.extraction_hints["look_for_quotes"] is True

    def test_get_fields_by_semantic_type(self):
        """Test the get_fields_by_semantic_type method"""
        from retrievers.implementations.intent.domain import DomainConfig

        config = {
            "domain_name": "E-Commerce",
            "entities": {
                "order": {
                    "name": "order"
                },
                "customer": {
                    "name": "customer"
                }
            },
            "fields": {
                "order": {
                    "id": {
                        "name": "id",
                        "data_type": "integer",
                        "semantic_type": "order_identifier"
                    },
                    "order_number": {
                        "name": "order_number",
                        "data_type": "string",
                        "semantic_type": "order_identifier"
                    },
                    "total": {
                        "name": "total",
                        "data_type": "decimal",
                        "semantic_type": "monetary_amount"
                    }
                },
                "customer": {
                    "name": {
                        "name": "name",
                        "data_type": "string",
                        "semantic_type": "person_name"
                    }
                }
            }
        }

        domain_config = DomainConfig(config)

        # Test getting fields by semantic type
        order_identifier_fields = domain_config.get_fields_by_semantic_type("order_identifier")
        assert len(order_identifier_fields) == 2
        assert any(f.name == "id" for f in order_identifier_fields)
        assert any(f.name == "order_number" for f in order_identifier_fields)

        monetary_amount_fields = domain_config.get_fields_by_semantic_type("monetary_amount")
        assert len(monetary_amount_fields) == 1
        assert monetary_amount_fields[0].name == "total"

        person_name_fields = domain_config.get_fields_by_semantic_type("person_name")
        assert len(person_name_fields) == 1
        assert person_name_fields[0].name == "name"

        # Test non-existent semantic type
        non_existent_fields = domain_config.get_fields_by_semantic_type("non_existent")
        assert len(non_existent_fields) == 0

    def test_response_formatter_with_semantic_priorities(self):
        """Test that ResponseFormatter uses semantic type priorities"""
        from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
        from retrievers.implementations.intent.domain import DomainConfig

        # Create domain config with semantic priorities
        config = {
            "domain_name": "E-Commerce",
            "entities": {
                "order": {
                    "name": "order"
                }
            },
            "fields": {
                "order": {
                    "id": {
                        "name": "id",
                        "data_type": "integer",
                        "semantic_type": "order_identifier",
                        "summary_priority": 10
                    },
                    "customer_name": {
                        "name": "customer_name",
                        "data_type": "string",
                        "semantic_type": "person_name",
                        "summary_priority": 9
                    },
                    "total": {
                        "name": "total",
                        "data_type": "decimal",
                        "semantic_type": "monetary_amount",
                        "summary_priority": 8
                    },
                    "status": {
                        "name": "status",
                        "data_type": "string",
                        "semantic_type": "order_status",
                        "summary_priority": 7
                    },
                    "description": {
                        "name": "description",
                        "data_type": "string"
                        # No semantic type or priority
                    }
                }
            }
        }

        domain_config = DomainConfig(config)
        formatter = ResponseFormatter(domain_config, None)  # No domain strategy

        # Sample result data
        sample_result = {
            "id": 12345,
            "customer_name": "John Doe",
            "total": 99.99,
            "status": "shipped",
            "description": "Large order with expedited shipping"
        }

        # Get summary fields - should use semantic priorities
        summary_fields = formatter._get_summary_fields(sample_result)

        # Verify fields are ordered by explicit summary priority (highest first)
        # Expected order: id=10, customer_name=9, total=8, status=7, description=generic fallback
        assert summary_fields[0] == "id"
        assert summary_fields[1] == "customer_name"
        assert summary_fields[2] == "total"
        assert summary_fields[3] == "status"
        assert summary_fields[4] == "description"