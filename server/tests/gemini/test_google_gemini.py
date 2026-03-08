"""
Pytest integration tests for Google Gemini API.

Run:
  pytest server/tests/gemini/test_google_gemini.py -v
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
def gemini_client():
    """Create Google GenAI client if prerequisites are present."""
    _load_env()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        pytest.skip("GOOGLE_API_KEY not set")

    try:
        from google import genai
    except ImportError:
        pytest.skip("google-genai package not installed")

    return genai.Client(api_key=api_key)


def _get_model() -> str:
    """Resolve model name from env, fallback to a commonly available model."""
    return os.getenv("GOOGLE_GENAI_MODEL", "gemini-1.5-pro-latest")


def _skip_for_connectivity(exc: Exception) -> None:
    """Skip Gemini integration tests when endpoint/network is unavailable."""
    warnings.warn(f"Skipping Gemini integration test due to connectivity issue: {exc}", RuntimeWarning)
    pytest.skip(f"Gemini endpoint unavailable: {exc}")


def test_gemini_list_models(gemini_client):
    """Validate API connectivity by listing Gemini models."""
    try:
        models = gemini_client.models.list()
    except Exception as exc:
        _skip_for_connectivity(exc)
        return
    gemini_models = [m for m in models if "gemini" in m.name.lower()]
    assert gemini_models, "No Gemini models returned by API"


def test_gemini_generate_content(gemini_client):
    """Validate basic text generation with configured/default model."""
    model = _get_model()
    try:
        response = gemini_client.models.generate_content(
            model=model,
            contents="Say hello in one short sentence.",
        )
    except Exception as exc:
        _skip_for_connectivity(exc)
        return
    assert response is not None
    assert getattr(response, "text", None), "Gemini response text was empty"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
