"""The Vertex AI inference service must read the Vertex block that ships in inference.yaml.

The service is registered and configured as ``vertexai``. The shipped block was keyed
``vertex``, so the service read an empty config (no project, location or model).
Google retired gemini-1.5-pro-001 on 2025-05-24 and -002 on 2025-09-24 on Vertex AI:
https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions
"""

from pathlib import Path

import pytest
import yaml

from ai_services.implementations.inference.vertexai_inference_service import VertexAIInferenceService
from services.provider_metadata import get_provider_context_window_info

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_INFERENCE_CONFIGS = [
    REPO_ROOT / "config" / "inference.yaml",
    REPO_ROOT / "install" / "default-config" / "inference.yaml",
]
RETIRED_ON_VERTEX = {"gemini-1.5-pro", "gemini-1.5-pro-001", "gemini-1.5-pro-002", "gemini-1.5-flash"}


def _shipped_inference(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)["inference"]


@pytest.mark.parametrize("path", SHIPPED_INFERENCE_CONFIGS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_vertexai_service_reads_the_shipped_vertex_block(path):
    inference = _shipped_inference(path)
    service = VertexAIInferenceService({"inference": inference})

    assert service.project_id == inference["vertexai"]["project_id"]
    assert service.model == inference["vertexai"]["model"]
    assert service.model not in RETIRED_ON_VERTEX


def test_vertexai_has_its_own_context_window_default():
    assert get_provider_context_window_info("vertexai") == get_provider_context_window_info("gemini")
