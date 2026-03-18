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
