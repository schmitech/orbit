import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from utils.ollama_utils import OllamaConfig


def test_ollama_inference_resolves_use_preset_without_default_model():
    config = {
        "inference": {
            "ollama": {
                "enabled": True,
                "use_preset": "smollm2-1.7b-cpu",
            }
        },
        "ollama_presets": {
            "smollm2-1.7b-cpu": {
                "base_url": "http://localhost:11434",
                "model": "SmolLM2:latest",
                "temperature": 0.6,
            }
        },
    }

    ollama_config = OllamaConfig(config, "inference")

    assert ollama_config.model == "SmolLM2:latest"
    assert ollama_config.temperature == 0.6


def test_ollama_inference_requires_model_or_valid_preset():
    config = {
        "inference": {
            "ollama": {
                "enabled": True,
            }
        }
    }

    with pytest.raises(ValueError, match="Ollama inference model is not configured"):
        OllamaConfig(config, "inference")


def test_ollama_inference_rejects_unknown_preset():
    config = {
        "inference": {
            "ollama": {
                "enabled": True,
                "use_preset": "missing-preset",
            }
        },
        "ollama_presets": {},
    }

    with pytest.raises(ValueError, match="missing-preset"):
        OllamaConfig(config, "inference")
