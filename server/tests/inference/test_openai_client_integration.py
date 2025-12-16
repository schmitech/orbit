"""
Integration tests for the OpenAI Python SDK against ORBIT's /v1/chat/completions endpoint.
"""

import os
import uuid

import pytest

openai = pytest.importorskip("openai")


API_URL = os.getenv("ORBIT_TEST_SERVER_URL", "http://localhost:3000/v1")
API_KEY = os.getenv("ORBIT_TEST_API_KEY", "default-key")


def _skip_on_connection_error(exc: Exception) -> None:
    """Skip the test gracefully if the ORBIT server is unreachable."""
    from openai import APIConnectionError

    if isinstance(exc, APIConnectionError) or "Connection refused" in str(exc):
        pytest.skip("ORBIT server is not reachable at ORBIT_TEST_SERVER_URL")


@pytest.fixture(scope="module")
def openai_client():
    """Return an OpenAI client configured to talk to the local ORBIT server."""
    session_id = f"pytest-{uuid.uuid4()}"
    headers = {
        "X-Session-ID": session_id,
        "X-API-Key": API_KEY,
    }

    return openai.OpenAI(
        api_key=API_KEY,
        base_url=API_URL,
        default_headers=headers,
    )


def test_openai_chat_completions_sync(openai_client):
    """
    Validate a basic non-streaming completion using the OpenAI SDK.
    """
    try:
        response = openai_client.chat.completions.create(
            model="orbit-pytest",
            messages=[
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "Respond with a short hello from ORBIT."},
            ],
        )
    except Exception as exc:  # pragma: no cover - handled by skip helper
        _skip_on_connection_error(exc)
        raise

    assert response.id.startswith("chatcmpl-")
    assert response.choices, "Expected at least one completion choice"
    assert response.choices[0].message.content
    assert response.choices[0].finish_reason == "stop"
    assert response.orbit["metadata"]["pipeline_used"] is True


def test_openai_chat_completions_stream(openai_client):
    """
    Validate streaming completions using the OpenAI SDK to ensure SSE translation works.
    """
    try:
        stream = openai_client.chat.completions.create(
            model="orbit-pytest",
            messages=[
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "List two fun facts about ORBIT in one sentence."},
            ],
            stream=True,
        )
    except Exception as exc:  # pragma: no cover - handled by skip helper
        _skip_on_connection_error(exc)
        raise

    collected = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            collected.append(delta.content)

    full_response = "".join(collected).strip()
    assert full_response, "Streaming response should contain content"
