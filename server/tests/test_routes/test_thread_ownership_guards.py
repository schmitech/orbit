"""
Ownership guards on the thread-management endpoints.

A thread exposes its parent_session_id, query_context and dataset_key, and deleting
one destroys the parent conversation's cached dataset. Both operations therefore
require ownership of the thread, not merely a valid API key.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from routes.routes_configurator import RouteConfigurator
from utils.text_utils import hash_api_key

KEY_A = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"
KEY_B = "api_tenantBBBBBBBBBBBBBBBBBBBBBBB"


class FakeThreadService:
    def __init__(self, thread):
        self._thread = thread
        self.deleted = []

    async def get_thread(self, thread_id):
        return self._thread if self._thread and thread_id == self._thread['thread_id'] else None

    async def delete_thread(self, thread_id):
        self.deleted.append(thread_id)
        return True


class FakeChatHistoryService:
    """Legacy-thread fallback: only KEY_A owns 'parent-sess-1'."""
    def __init__(self, owner_key=KEY_A):
        self._owner_key = owner_key

    async def authorize_session(self, session_id, api_key):
        if not api_key:
            return True
        return api_key == self._owner_key


def _build_app(thread, chat_history_service=None):
    app = FastAPI()
    configurator = RouteConfigurator({}, logging.getLogger(__name__))
    thread_service = FakeThreadService(thread)

    async def get_thread_service(request: Request):
        return thread_service

    async def get_api_key(request: Request):
        return ("demo", None)

    async def validate_session_id(request: Request):
        # Only used by the POST route, which these tests don't exercise.
        return "sess"

    configurator._configure_thread_endpoints(app, {
        'get_thread_service': get_thread_service,
        'get_api_key': get_api_key,
        'validate_session_id': validate_session_id,
    })
    app.state.chat_history_service = chat_history_service or FakeChatHistoryService()
    return app, thread_service


def _bound_thread():
    return {
        'thread_id': 't1',
        'thread_session_id': 'thread-sess-1',
        'parent_message_id': 'msg-1',
        'parent_session_id': 'parent-sess-1',
        'adapter_name': 'intent-test',
        'query_context': {'original_query': 'A confidential question'},
        'dataset_key': 'thread_dataset_t1_secret',
        'created_at': '2026-07-31T00:00:00',
        'expires_at': '2026-08-01T00:00:00',
        'owner_api_key_hash': hash_api_key(KEY_A),
    }


class TestGetThread:
    def test_owner_can_read(self):
        app, _ = _build_app(_bound_thread())
        r = TestClient(app).get("/api/threads/t1", headers={"X-API-Key": KEY_A})
        assert r.status_code == 200
        assert r.json()['parent_session_id'] == 'parent-sess-1'

    def test_foreign_key_denied(self):
        app, _ = _build_app(_bound_thread())
        r = TestClient(app).get("/api/threads/t1", headers={"X-API-Key": KEY_B})
        assert r.status_code == 403
        # None of the thread's contents leak in the error body.
        body = r.text
        assert 'parent-sess-1' not in body
        assert 'thread_dataset_t1_secret' not in body
        assert 'A confidential question' not in body

    def test_owner_hash_not_exposed_to_client(self):
        """The fingerprint is an internal authorization value."""
        app, _ = _build_app(_bound_thread())
        r = TestClient(app).get("/api/threads/t1", headers={"X-API-Key": KEY_A})
        assert 'owner_api_key_hash' not in r.json()

    def test_legacy_thread_falls_back_to_parent_session(self):
        legacy = _bound_thread()
        legacy['owner_api_key_hash'] = None
        app, _ = _build_app(legacy)

        client = TestClient(app)
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_A}).status_code == 200
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403

    def test_missing_thread_is_404(self):
        app, _ = _build_app(None)
        r = TestClient(app).get("/api/threads/nope", headers={"X-API-Key": KEY_A})
        assert r.status_code == 404


class TestDeleteThread:
    def test_owner_can_delete(self):
        app, svc = _build_app(_bound_thread())
        r = TestClient(app).delete("/api/threads/t1", headers={"X-API-Key": KEY_A})
        assert r.status_code == 200
        assert svc.deleted == ['t1']

    def test_foreign_key_denied_and_nothing_deleted(self):
        app, svc = _build_app(_bound_thread())
        r = TestClient(app).delete("/api/threads/t1", headers={"X-API-Key": KEY_B})
        assert r.status_code == 403
        assert svc.deleted == []

    def test_legacy_thread_denied_via_parent_session(self):
        legacy = _bound_thread()
        legacy['owner_api_key_hash'] = None
        app, svc = _build_app(legacy)
        r = TestClient(app).delete("/api/threads/t1", headers={"X-API-Key": KEY_B})
        assert r.status_code == 403
        assert svc.deleted == []


class TestLegacyThreadFailsClosed:
    """
    A legacy thread carries no ownership proof of its own, so anything that stops the
    parent-session check from running must deny. Previously each of these fell through
    and returned the thread to any valid key.
    """

    def _legacy(self, **overrides):
        legacy = _bound_thread()
        legacy['owner_api_key_hash'] = None
        legacy.update(overrides)
        return legacy

    def test_missing_chat_history_service_denies(self):
        app, svc = _build_app(self._legacy())
        del app.state.chat_history_service

        client = TestClient(app)
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert client.delete("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert svc.deleted == []

    def test_none_chat_history_service_denies(self):
        app, svc = _build_app(self._legacy())
        app.state.chat_history_service = None

        client = TestClient(app)
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert client.delete("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert svc.deleted == []

    def test_missing_parent_session_id_denies(self):
        app, svc = _build_app(self._legacy(parent_session_id=None))

        client = TestClient(app)
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert client.delete("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert svc.deleted == []

    def test_empty_parent_session_id_denies(self):
        app, _ = _build_app(self._legacy(parent_session_id=""))
        r = TestClient(app).get("/api/threads/t1", headers={"X-API-Key": KEY_B})
        assert r.status_code == 403

    def test_authorization_lookup_raising_denies(self):
        class ExplodingChatHistoryService:
            async def authorize_session(self, session_id, api_key):
                raise RuntimeError("database unavailable")

        app, svc = _build_app(self._legacy(), chat_history_service=ExplodingChatHistoryService())

        client = TestClient(app)
        # Even the legitimate owner is denied — the check could not be established.
        assert client.get("/api/threads/t1", headers={"X-API-Key": KEY_A}).status_code == 403
        assert client.delete("/api/threads/t1", headers={"X-API-Key": KEY_B}).status_code == 403
        assert svc.deleted == []


class TestKeyEnforcementDisabled:
    """With no API key supplied, behaviour is unchanged."""
    def test_read_and_delete_allowed(self):
        app, svc = _build_app(_bound_thread())
        client = TestClient(app)
        assert client.get("/api/threads/t1").status_code == 200
        assert client.delete("/api/threads/t1").status_code == 200
        assert svc.deleted == ['t1']
