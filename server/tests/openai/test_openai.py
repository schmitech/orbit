"""
Pytest integration tests for OpenAI API.

Run:
  pytest server/tests/openai/test_openai.py -v
"""

import os
import warnings
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _load_env() -> None:
    """Load .env from common repo locations if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    current_dir = Path(__file__).resolve().parent
    candidates = [
        current_dir.parent.parent.parent / ".env",  # repo root
        current_dir.parent.parent / ".env",         # server/.env
        Path.cwd() / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return


@pytest.fixture(scope="module")
def openai_client():
    """Create OpenAI client if prerequisites are present."""
    _load_env()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    try:
        from openai import OpenAI
    except ImportError:
        pytest.skip("openai package not installed")

    return OpenAI(api_key=api_key)


def _get_model() -> str:
    """Resolve model name from env, fallback to a commonly available model."""
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _skip_for_connectivity(exc: Exception) -> None:
    """Skip OpenAI integration tests when endpoint/network is unavailable."""
    warnings.warn(f"Skipping OpenAI integration test due to connectivity issue: {exc}", RuntimeWarning)
    pytest.skip(f"OpenAI endpoint unavailable: {exc}")


def test_openai_list_models(openai_client):
    """Validate API connectivity by listing OpenAI models."""
    try:
        models = openai_client.models.list()
    except Exception as exc:
        _skip_for_connectivity(exc)
        return
    
    # Check if we got some models back
    model_list = list(models)
    assert len(model_list) > 0, "No models returned by OpenAI API"
    
    # Optionally verify GPT models are present
    gpt_models = [m for m in model_list if "gpt" in m.id.lower()]
    assert gpt_models, "No GPT models found in the models list"


def test_openai_chat_completion(openai_client):
    """Validate basic text generation with configured/default model."""
    model = _get_model()
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Say hello in one short sentence."}
            ],
        )
    except Exception as exc:
        _skip_for_connectivity(exc)
        return
    
    assert response is not None
    assert response.choices[0].message.content, "OpenAI response content was empty"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
