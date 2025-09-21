"""Unit tests for the GenericDomainStrategy."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from retrievers.implementations.intent.domain import DomainConfig, FieldConfig
from retrievers.implementations.intent.domain_strategies.generic import GenericDomainStrategy


@pytest.fixture
def healthcare_domain_config():
    """DomainConfig resembling the healthcare example configuration."""
    config = {
        "domain_name": "Healthcare",
        "domain_type": "generic",
        "semantic_types": {
            "patient_identifier": {
                "patterns": ["patient", "mrn"],
                "regex_patterns": [r"MRN\s*[:#-]?\s*([A-Z]?\d{6,8})"],
            },
            "person_name": {
                "patterns": ["name", "patient"],
                "regex_patterns": [r'"([^"]+)"'],
            },
            "diagnosis_code": {
                "regex_patterns": [r"ICD(?:-\d{1,2})?[:\s]*([A-Z]\d{2}\.?\d*)"],
            },
            "encounter_date": {
                "regex_patterns": [r"\b\d{4}-\d{2}-\d{2}\b"],
            },
        },
        "entities": {
            "patient": {"name": "patient"},
        },
        "fields": {
            "patient": {
                "patient_id": {
                    "name": "patient_id",
                    "data_type": "string",
                    "semantic_type": "patient_identifier",
                    "summary_priority": 100,
                    "extraction_pattern": r"MRN\s*[:#-]?\s*([A-Z]?\d{6,8})",
                },
                "full_name": {
                    "name": "full_name",
                    "data_type": "string",
                    "semantic_type": "person_name",
                    "extraction_hints": {
                        "look_for_quotes": True,
                        "capitalization_required": True,
                    },
                },
            }
        },
    }
    return DomainConfig(config)


def test_semantic_extraction_uses_regex(healthcare_domain_config):
    strategy = GenericDomainStrategy(healthcare_domain_config)
    query = "Please pull records for patient MRN 123456"
    param = {
        "name": "patient_id",
        "entity": "patient",
        "field": "patient_id",
        "type": "string",
        "semantic_type": "patient_identifier",
    }

    value = strategy.extract_domain_parameters(query, param, healthcare_domain_config)
    assert value == "123456"


def test_extraction_hints_capture_names(healthcare_domain_config):
    strategy = GenericDomainStrategy(healthcare_domain_config)
    query = 'Patient name is "Jane Doe" and requires follow-up'
    param = {
        "name": "full_name",
        "entity": "patient",
        "field": "full_name",
        "type": "string",
    }

    value = strategy.extract_domain_parameters(query, param, healthcare_domain_config)
    assert value == "Jane Doe"


def test_summary_priority_prefers_explicit_value(healthcare_domain_config):
    strategy = GenericDomainStrategy(healthcare_domain_config)
    field_config = healthcare_domain_config.get_field("patient", "patient_id")
    assert field_config.summary_priority == 100
    priority = strategy.get_summary_field_priority("patient_id", field_config)
    assert priority == 100


def test_summary_priority_semantic_default():
    strategy = GenericDomainStrategy()
    field_config = FieldConfig(
        name="account_code",
        data_type="string",
        semantic_type="account_identifier",
    )
    priority = strategy.get_summary_field_priority("account_code", field_config)
    assert priority == 90  # identifier semantic fallback


def test_domain_names_include_type_and_generic(healthcare_domain_config):
    strategy = GenericDomainStrategy(healthcare_domain_config)
    names = strategy.get_domain_names()
    assert names[0] == "Healthcare"
    assert "generic" in names
