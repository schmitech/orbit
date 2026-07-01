"""Unit tests for A2A (Agent-to-Agent) protocol routes."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.a2a_routes import create_a2a_router, _tasks, _extract_text, _build_skills


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_app(chat_service=None, api_key_service=None, adapter_manager=None, config=None):
    app = FastAPI()
    app.state.config = config or {}
    app.state.chat_service = chat_service or MagicMock()
    if api_key_service is not None:
        app.state.api_key_service = api_key_service
    if adapter_manager is not None:
        app.state.adapter_manager = adapter_manager
    app.include_router(create_a2a_router())
    return app


@pytest.fixture(autouse=True)
def clear_tasks():
    """Isolate in-memory task store between tests."""
    _tasks.clear()
    yield
    _tasks.clear()


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------

class TestAgentCard:
    def test_returns_agent_card(self):
        client = TestClient(make_app())
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["name"] == "ORBIT"
        assert card["capabilities"]["streaming"] is True
        assert isinstance(card["skills"], list)

    def test_skills_from_adapter_manager(self):
        adapter_manager = MagicMock()
        adapter_manager.get_all_skills.return_value = [
            {"name": "HR", "adapter_name": "hr", "description": "HR queries"}
        ]
        client = TestClient(make_app(adapter_manager=adapter_manager))
        card = client.get("/.well-known/agent.json").json()
        assert any(s["id"] == "hr" for s in card["skills"])

    def test_fallback_skill_when_no_adapter_manager(self):
        client = TestClient(make_app())
        card = client.get("/.well-known/agent.json").json()
        assert card["skills"][0]["id"] == "chat"


# ---------------------------------------------------------------------------
# Invalid JSON-RPC
# ---------------------------------------------------------------------------

class TestInvalidRequests:
    def test_bad_json(self):
        client = TestClient(make_app())
        resp = client.post("/a2a", content=b"not-json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == -32700

    def test_wrong_jsonrpc_version(self):
        client = TestClient(make_app())
        resp = client.post("/a2a", json={"jsonrpc": "1.0", "method": "tasks/send", "id": 1})
        assert resp.json()["error"]["code"] == -32600

    def test_unknown_method(self):
        client = TestClient(make_app())
        body = {"jsonrpc": "2.0", "id": 1, "method": "tasks/unknown", "params": {}}
        resp = client.post("/a2a", json=body)
        assert resp.json()["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# tasks/send
# ---------------------------------------------------------------------------

class TestTasksSend:
    def _chat_service(self, response="Hello!"):
        svc = MagicMock()
        svc.process_chat = AsyncMock(return_value={"response": response})
        return svc

    def _body(self, text, task_id=None):
        msg = {"role": "user", "parts": [{"type": "text", "text": text}]}
        params = {"message": msg}
        if task_id:
            params["id"] = task_id
        return {"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": params}

    def test_successful_task(self):
        client = TestClient(make_app(chat_service=self._chat_service("Hi there!")))
        resp = client.post("/a2a", json=self._body("Hello"))
        data = resp.json()
        assert "error" not in data
        result = data["result"]
        assert result["status"]["state"] == "completed"
        assert result["artifacts"][0]["parts"][0]["text"] == "Hi there!"

    def test_preserves_provided_task_id(self):
        client = TestClient(make_app(chat_service=self._chat_service()))
        resp = client.post("/a2a", json=self._body("Hello", task_id="my-task-123"))
        assert resp.json()["result"]["id"] == "my-task-123"

    def test_missing_text_returns_error(self):
        client = TestClient(make_app())
        body = {
            "jsonrpc": "2.0", "id": 1, "method": "tasks/send",
            "params": {"message": {"role": "user", "parts": [{"type": "image", "url": "x"}]}}
        }
        resp = client.post("/a2a", json=body)
        assert resp.json()["error"]["code"] == -32602

    def test_chat_service_error_returns_failed_task(self):
        svc = MagicMock()
        svc.process_chat = AsyncMock(return_value={"error": "LLM unavailable"})
        client = TestClient(make_app(chat_service=svc))
        resp = client.post("/a2a", json=self._body("Hello"))
        assert resp.json()["error"]["code"] == -32000

    def test_metadata_adapter_override(self):
        svc = MagicMock()
        svc.process_chat = AsyncMock(return_value={"response": "ok"})
        client = TestClient(make_app(chat_service=svc))
        body = self._body("query")
        body["params"]["metadata"] = {"adapter": "hr"}
        client.post("/a2a", json=body)
        call_kwargs = svc.process_chat.call_args
        assert call_kwargs.kwargs.get("adapter_name") == "hr"


# ---------------------------------------------------------------------------
# tasks/get and tasks/cancel
# ---------------------------------------------------------------------------

class TestTasksGetCancel:
    def _post(self, client, method, params):
        return client.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})

    def test_get_nonexistent_task(self):
        client = TestClient(make_app())
        resp = self._post(client, "tasks/get", {"id": "no-such-task"})
        assert resp.json()["error"]["code"] == -32001

    def test_get_existing_task(self):
        _tasks["t1"] = {"id": "t1", "status": {"state": "completed"}, "history": [], "artifacts": []}
        client = TestClient(make_app())
        resp = self._post(client, "tasks/get", {"id": "t1"})
        assert resp.json()["result"]["id"] == "t1"

    def test_cancel_task(self):
        _tasks["t2"] = {"id": "t2", "status": {"state": "working"}, "history": [], "artifacts": []}
        client = TestClient(make_app())
        resp = self._post(client, "tasks/cancel", {"id": "t2"})
        assert resp.json()["result"]["status"]["state"] == "canceled"
        assert _tasks["t2"]["status"]["state"] == "canceled"

    def test_cancel_nonexistent_task(self):
        client = TestClient(make_app())
        resp = self._post(client, "tasks/cancel", {"id": "ghost"})
        assert resp.json()["error"]["code"] == -32001


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_extract_text_from_parts(self):
        msg = {"parts": [{"type": "text", "text": "hello"}, {"type": "image", "url": "x"}]}
        assert _extract_text(msg) == "hello"

    def test_extract_text_multiple_text_parts(self):
        msg = {"parts": [{"type": "text", "text": "foo"}, {"type": "text", "text": "bar"}]}
        assert _extract_text(msg) == "foo bar"

    def test_extract_text_empty(self):
        assert _extract_text({}) == ""


# ---------------------------------------------------------------------------
# P1: API key enforcement
# ---------------------------------------------------------------------------

class TestApiKeyEnforcement:
    def _body(self, text="Hello"):
        msg = {"role": "user", "parts": [{"type": "text", "text": text}]}
        return {"jsonrpc": "2.0", "id": 1, "method": "tasks/send", "params": {"message": msg}}

    def test_missing_bearer_when_key_service_present_returns_401(self):
        key_svc = MagicMock()
        client = TestClient(make_app(api_key_service=key_svc), raise_server_exceptions=False)
        resp = client.post("/a2a", json=self._body())
        assert resp.status_code == 401

    def test_invalid_bearer_propagates_auth_error(self):
        from fastapi import HTTPException as FastAPIHTTPException
        key_svc = MagicMock()
        key_svc.get_adapter_for_api_key = AsyncMock(
            side_effect=FastAPIHTTPException(status_code=403, detail="Invalid API key")
        )
        client = TestClient(make_app(api_key_service=key_svc), raise_server_exceptions=False)
        resp = client.post("/a2a", json=self._body(), headers={"Authorization": "Bearer bad-key"})
        assert resp.status_code == 403

    def test_no_key_service_allows_default_without_bearer(self):
        svc = MagicMock()
        svc.process_chat = AsyncMock(return_value={"response": "ok"})
        # No api_key_service set — auth disabled
        client = TestClient(make_app(chat_service=svc))
        resp = client.post("/a2a", json=self._body())
        assert resp.status_code == 200

    def test_valid_bearer_resolves_adapter(self):
        key_svc = MagicMock()
        key_svc.get_adapter_for_api_key = AsyncMock(return_value=("hr", None))
        chat_svc = MagicMock()
        chat_svc.process_chat = AsyncMock(return_value={"response": "ok"})
        client = TestClient(make_app(chat_service=chat_svc, api_key_service=key_svc))
        resp = client.post("/a2a", json=self._body(), headers={"Authorization": "Bearer valid-key"})
        assert resp.status_code == 200
        call_kwargs = chat_svc.process_chat.call_args.kwargs
        assert call_kwargs["adapter_name"] == "hr"


# ---------------------------------------------------------------------------
# P2: Streaming error propagation
# ---------------------------------------------------------------------------

class TestStreamingErrorPropagation:
    def _body(self, text="Hello"):
        msg = {"role": "user", "parts": [{"type": "text", "text": text}]}
        return {"jsonrpc": "2.0", "id": 1, "method": "tasks/sendSubscribe", "params": {"message": msg}}

    async def _stream_chunks(self, *chunks):
        for c in chunks:
            yield f"data: {json.dumps(c)}\n\n"

    def _collect_sse_events(self, client, body):
        """Collect all SSE data lines from a streaming response."""
        events = []
        with client.stream("POST", "/a2a", json=body) as resp:
            for line in resp.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[6:].strip()))
        return events

    def test_error_in_done_chunk_marks_task_failed(self):
        async def bad_stream(**kwargs):
            yield "data: " + json.dumps({"response": "partial"}) + "\n\n"
            yield "data: " + json.dumps({"done": True, "error": "Pipeline failed"}) + "\n\n"

        chat_svc = MagicMock()
        chat_svc.process_chat_stream = bad_stream
        # No api_key_service — auth disabled
        client = TestClient(make_app(chat_service=chat_svc))

        events = self._collect_sse_events(client, self._body())

        completed = any(
            e.get("result", {}).get("status", {}).get("state") == "completed"
            for e in events
        )
        assert not completed, "Task must not be marked completed when stream reports an error"

    def test_clean_stream_marks_task_completed(self):
        async def good_stream(**kwargs):
            yield "data: " + json.dumps({"response": "Hello!"}) + "\n\n"
            yield "data: " + json.dumps({"done": True}) + "\n\n"

        chat_svc = MagicMock()
        chat_svc.process_chat_stream = good_stream
        client = TestClient(make_app(chat_service=chat_svc))

        events = self._collect_sse_events(client, self._body())

        completed = any(
            e.get("result", {}).get("status", {}).get("state") == "completed"
            for e in events
        )
        assert completed
