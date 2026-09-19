"""
POST /api/threads (`create_thread` in `_configure_thread_endpoints`) builds a
thread from a parent assistant message's stored metadata. Metadata can arrive
as a plain dict, a JSON string, or split across a separate `metadata_json`
column (SQLite) — the route normalizes all three before extracting
`retrieved_docs`/`query_context` and handing off to `ThreadService`.
"""

import json
import logging

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from routes.routes_configurator import RouteConfigurator

API_KEY = "api_tenantAAAAAAAAAAAAAAAAAAAAAAA"


class FakeDatabaseService:
    def __init__(self, parent_message):
        self._parent_message = parent_message

    async def find_one(self, collection_name, query):
        if self._parent_message is None:
            return None
        if (
            query.get('_id') == self._parent_message.get('_id')
            and query.get('session_id') == self._parent_message.get('session_id')
        ):
            return self._parent_message
        return None


class FakeChatHistoryService:
    def __init__(self, database_service, authorized=True, collection_name='chat_history'):
        self.database_service = database_service
        self.collection_name = collection_name
        self._authorized = authorized

    async def authorize_session(self, session_id, api_key):
        return self._authorized


class FakeThreadService:
    def __init__(self):
        self.calls = []

    async def create_thread(self, **kwargs):
        self.calls.append(kwargs)
        return {"thread_id": "new-thread", "parent_session_id": kwargs["parent_session_id"]}


def _build_app(parent_message, authorized=True):
    app = FastAPI()
    configurator = RouteConfigurator({}, logging.getLogger(__name__))
    thread_service = FakeThreadService()
    database_service = FakeDatabaseService(parent_message)
    chat_history_service = FakeChatHistoryService(database_service, authorized=authorized)

    async def get_thread_service(request: Request):
        return thread_service

    async def get_api_key(request: Request):
        return ("demo-adapter", None)

    async def validate_session_id(request: Request):
        return "sess-1"

    configurator.get_thread_service = get_thread_service
    configurator.get_api_key = get_api_key
    configurator.validate_session_id = validate_session_id
    configurator._configure_thread_endpoints(app)
    app.state.chat_history_service = chat_history_service
    return app, thread_service


def _base_message(**overrides):
    message = {
        '_id': 'msg-1',
        'session_id': 'sess-1',
        'role': 'assistant',
        'metadata': {
            'original_query': 'What is the total revenue?',
            'template_id': 'tmpl-1',
            'parameters_used': {'year': 2025},
            'retrieved_docs': [{'row': 1}],
        },
    }
    message.update(overrides)
    return message


def _post(app, message_id='msg-1', session_id='sess-1', headers=None):
    headers = {"X-API-Key": API_KEY, **(headers or {})}
    return TestClient(app).post(
        "/api/threads",
        json={"message_id": message_id, "session_id": session_id},
        headers=headers,
    )


class TestMetadataNormalization:
    def test_dict_metadata_is_used_directly(self):
        app, thread_service = _build_app(_base_message())
        r = _post(app)

        assert r.status_code == 200
        assert r.json()["thread_id"] == "new-thread"
        call = thread_service.calls[0]
        assert call["raw_results"] == [{'row': 1}]
        assert call["query_context"] == {
            'original_query': 'What is the total revenue?',
            'adapter_name': 'demo-adapter',
            'template_id': 'tmpl-1',
            'parameters': {'year': 2025},
        }

    def test_json_string_metadata_is_parsed(self):
        message = _base_message(metadata=json.dumps({
            'original_query': 'stringified',
            'retrieved_docs': [{'row': 2}],
        }))
        app, thread_service = _build_app(message)
        r = _post(app)

        assert r.status_code == 200
        assert thread_service.calls[0]["raw_results"] == [{'row': 2}]
        assert thread_service.calls[0]["query_context"]["original_query"] == "stringified"

    def test_malformed_json_string_metadata_falls_back_to_empty(self):
        message = _base_message(metadata="{not valid json")
        app, _ = _build_app(message)
        r = _post(app)

        # No retrieved_docs survive the fallback -> 400, not a 500 crash.
        assert r.status_code == 400

    def test_unsupported_metadata_type_falls_back_to_empty(self):
        message = _base_message(metadata=12345)
        app, _ = _build_app(message)
        r = _post(app)

        assert r.status_code == 400

    def test_metadata_json_column_merges_into_dict_metadata(self):
        message = _base_message(
            metadata={'original_query': 'base'},
            metadata_json=json.dumps({'retrieved_docs': [{'row': 3}], 'template_id': 'from-json-col'}),
        )
        app, thread_service = _build_app(message)
        r = _post(app)

        assert r.status_code == 200
        call = thread_service.calls[0]
        assert call["raw_results"] == [{'row': 3}]
        assert call["query_context"]["original_query"] == "base"
        assert call["query_context"]["template_id"] == "from-json-col"

    def test_malformed_metadata_json_column_is_ignored(self):
        message = _base_message(
            metadata={'original_query': 'base', 'retrieved_docs': [{'row': 1}]},
            metadata_json="{not valid json",
        )
        app, thread_service = _build_app(message)
        r = _post(app)

        assert r.status_code == 200
        # The dict metadata's own retrieved_docs survive; the broken column is dropped silently.
        assert thread_service.calls[0]["raw_results"] == [{'row': 1}]


class TestValidation:
    def test_missing_parent_message_is_404(self):
        app, _ = _build_app(None)
        r = _post(app)
        assert r.status_code == 404

    def test_non_assistant_message_is_400(self):
        app, _ = _build_app(_base_message(role='user'))
        r = _post(app)
        assert r.status_code == 400

    def test_no_retrieved_docs_is_400(self):
        app, _ = _build_app(_base_message(metadata={'original_query': 'x'}))
        r = _post(app)
        assert r.status_code == 400

    def test_unauthorized_session_is_403(self):
        app, thread_service = _build_app(_base_message(), authorized=False)
        r = _post(app)
        assert r.status_code == 403
        assert thread_service.calls == []

    def test_missing_chat_history_service_is_503(self):
        app, _ = _build_app(_base_message())
        del app.state.chat_history_service
        r = _post(app)
        assert r.status_code == 503

    def test_thread_service_failure_is_500(self):
        app, thread_service = _build_app(_base_message())

        async def raise_error(**kwargs):
            raise RuntimeError("dataset store unavailable")

        thread_service.create_thread = raise_error
        r = _post(app)
        assert r.status_code == 500
