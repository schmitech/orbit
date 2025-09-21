"""Integration tests for the healthcare domain using the generic strategy."""

import os
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.domain import DomainConfig
from retrievers.implementations.intent.domain.extraction.extractor import DomainParameterExtractor
from retrievers.implementations.intent.domain.response.formatters import ResponseFormatter
from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry


HEALTHCARE_CONFIG_PATH = Path(__file__).resolve().parents[3] / 'config' / 'sql_intent_templates' / 'examples' / 'healthcare' / 'healthcare_domain.yaml'


class MockInferenceClient:
    async def generate(self, *args, **kwargs):
        return {"extracted_value": None}


@pytest.fixture(scope="module")
def healthcare_domain_config() -> DomainConfig:
    with open(HEALTHCARE_CONFIG_PATH, 'r', encoding='utf-8') as config_file:
        config_dict = yaml.safe_load(config_file)
    return DomainConfig(config_dict)


@pytest.mark.asyncio
async def test_generic_strategy_extracts_healthcare_fields(healthcare_domain_config):
    extractor = DomainParameterExtractor(MockInferenceClient(), healthcare_domain_config)

    query = (
        "Pull encounter details for patient MRN 123456 who was seen on 2024-01-15 "
        "with diagnosis ICD-10: A10.5 and medication \"Metformin\""
    )

    template = {
        "parameters": [
            {
                "name": "patient_id",
                "entity": "patient",
                "field": "patient_id",
                "type": "string",
                "required": True,
            },
            {
                "name": "diagnosis_code",
                "entity": "patient",
                "field": "diagnosis_code",
                "type": "string",
            },
            {
                "name": "encounter_date",
                "entity": "patient",
                "field": "encounter_date",
                "type": "date",
            },
            {
                "name": "medication",
                "entity": "patient",
                "field": "medication",
                "type": "string",
            },
        ]
    }

    parameters = await extractor.extract_parameters(query, template)

    assert parameters["patient_id"] == "123456"
    assert parameters["diagnosis_code"] == "A10.5"
    assert parameters["encounter_date"] == "2024-01-15"
    assert parameters["medication"] == "Metformin"


def test_generic_strategy_prioritises_healthcare_summary(healthcare_domain_config):
    strategy = DomainStrategyRegistry.get_strategy(
        healthcare_domain_config.domain_name,
        healthcare_domain_config,
    )
    assert strategy is not None
    formatter = ResponseFormatter(healthcare_domain_config, strategy)

    summary_fields = formatter._get_summary_fields(
        {
            "patient_id": "123456",
            "full_name": "Jane Doe",
            "diagnosis_code": "A10.5",
            "medication": "Metformin",
            "encounter_date": "2024-01-15",
        }
    )

    assert summary_fields[0] == "patient_id"
    assert "full_name" in summary_fields[:3]
    assert "diagnosis_code" in summary_fields
