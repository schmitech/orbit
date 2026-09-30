"""
Tests that the shipped decision adapter configs are valid and wired to the decision_model type.
"""

import sys
from pathlib import Path

import yaml

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(SERVER_DIR))

from adapter_sdk.validator import validate_providers, validate_structure, validate_yaml_text  # noqa: E402
from inference.pipeline.steps.decision_model import validate_questions  # noqa: E402

ADAPTERS_FILE = SERVER_DIR.parent / "config" / "adapters" / "decision.yaml"


def _adapters():
    return yaml.safe_load(ADAPTERS_FILE.read_text())["adapters"]


def test_decision_yaml_passes_sdk_validation():
    assert validate_yaml_text(ADAPTERS_FILE.read_text()) == []


def test_each_example_adapter_is_valid():
    names = set()
    for adapter in _adapters():
        names.add(adapter["name"])
        assert adapter["type"] == "decision_model"
        assert adapter["decision_provider"] in {"ollama", "typesafe"}
        assert validate_structure(adapter) == []
        assert validate_questions(adapter["config"]["questions"]) is None
        assert adapter["capabilities"]["retrieval_behavior"] == "none"
    assert names == {"ticket-triage", "content-moderation", "skill-router"}


def test_decision_model_does_not_require_inference_provider():
    entry = {"type": "decision_model", "datasource": "none", "adapter": "multimodal",
             "implementation": "implementations.passthrough.multimodal.MultimodalImplementation",
             "inference_provider": "not-enabled"}
    assert validate_providers(entry, enabled_providers={"openai"}) == []
