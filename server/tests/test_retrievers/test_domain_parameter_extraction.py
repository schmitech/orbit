"""Regression tests for intent-domain parameter extraction."""

import os
import sys
from unittest.mock import AsyncMock

import pytest

# Ensure the server directory is in the path for imports
_server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from retrievers.implementations.intent.domain import DomainConfig
from retrievers.implementations.intent.domain.extraction import DomainParameterExtractor, ValueExtractor
from retrievers.implementations.intent.domain.extraction.pattern_builder import PatternBuilder
from retrievers.implementations.intent.domain.extraction.validator import Validator
from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
from retrievers.implementations.intent.domain_strategies.generic import GenericDomainStrategy


def test_value_extractor_picks_explicit_year_for_integer_param():
    domain_config = DomainConfig({})
    strategy = GenericDomainStrategy(domain_config)
    extractor = ValueExtractor(domain_config, patterns={}, domain_strategy=strategy)

    value = extractor.extract_template_parameter(
        "Are weekends more dangerous in Edmonton in 2024?",
        {
            "name": "year",
            "type": "integer",
            "description": "Year to analyze",
            "default": 2025,
        },
    )

    assert value == 2024


@pytest.mark.asyncio
async def test_domain_parameter_extractor_prefers_explicit_year_over_default():
    domain_config = DomainConfig({})
    inference_client = AsyncMock()
    strategy = GenericDomainStrategy(domain_config)
    extractor = DomainParameterExtractor(inference_client, domain_config, strategy)

    template = {
        "description": "Compare weekend vs weekday occurrence rates by category",
        "parameters": [
            {
                "name": "year",
                "type": "integer",
                "description": "Year to analyze",
                "required": False,
                "default": 2025,
            }
        ],
    }

    parameters = await extractor.extract_parameters(
        "Are weekends more dangerous in Edmonton in 2024?",
        template,
    )

    assert parameters == {"year": 2024}


def test_email_patterns_reject_pipe_in_tld():
    domain_config = DomainConfig({
        "entities": {
            "user": {"display_name": "User"},
        },
        "fields": {
            "user": {
                "email": {
                    "data_type": "string",
                    "filterable": True,
                },
            },
        },
    })

    validator = Validator(domain_config)
    assert validator._is_valid_email("person@example.com")
    assert not validator._is_valid_email("person@example.g|")

    patterns = PatternBuilder(domain_config).build_patterns()
    assert patterns["user.email"].search("email person@example.com")
    assert not patterns["user.email"].search("email person@example.g|")

    strategy = GenericDomainStrategy(domain_config)
    assert strategy._extract_email("contact person@example.com", {}) == "person@example.com"
    assert strategy._extract_email("contact person@example.g|", {}) is None


def test_validator_accepts_negative_integer_strings():
    validator = Validator(DomainConfig({}))

    assert validator._validate_type("-5", "integer")
    assert validator._validate_type("5", "integer")
    assert not validator._validate_type("-", "integer")


def test_validator_skips_invalid_configured_pattern(caplog):
    domain_config = DomainConfig({
        "entities": {
            "ticket": {"display_name": "Ticket"},
        },
        "fields": {
            "ticket": {
                "code": {
                    "data_type": "string",
                    "validation_rules": {"pattern": "["},
                },
            },
        },
    })
    validator = Validator(domain_config)

    is_valid, error = validator.validate("ABC-123", "ticket", "code")

    assert is_valid is True
    assert error is None
    assert "Invalid validation pattern for code skipped" in caplog.text


def test_response_formatter_percentage_ratio():
    domain_config = DomainConfig({
        "entities": {
            "metric": {"display_name": "Metric"},
        },
        "fields": {
            "metric": {
                "conversion_rate": {
                    "data_type": "decimal",
                    "display_format": "percentage_ratio",
                },
            },
        },
    })
    formatter = ResponseFormatter(domain_config, GenericDomainStrategy(domain_config))

    assert formatter.format_results([{"conversion_rate": 0.425}], {}) == [
        {"conversion_rate": "42.5%"}
    ]


def test_generic_date_range_requires_date_like_values():
    strategy = GenericDomainStrategy(DomainConfig({}))

    assert strategy._extract_date_range("orders from the East Side to the West Side", {}) is None
