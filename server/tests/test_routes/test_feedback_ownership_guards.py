"""Feedback must be authorized before private comments are read or mutated."""

import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from routes.routes_configurator import RouteConfigurator


KEY_A = "tenant-a-key"
KEY_B = "tenant-b-key"
SESSION = "tenant-a-session"
FEEDBACK = {
    "message_id": "message-a",
    "feedback_type": "down",
    "comment": "Private pricing strategy",
}


@pytest.fixture
def feedback_app():
    app = FastAPI()
    feedback = AsyncMock()
    feedback.get_session_feedback.return_value = [FEEDBACK]
    feedback.submit_feedback.return_value = {**FEEDBACK, "action": "created"}
    history = AsyncMock()
    history.authorize_session.side_effect = lambda session, key: session == SESSION and key == KEY_A
    app.state.chat_history_service = history

    async def get_feedback_service():
        return feedback

    async def get_api_key(request: Request):
        # Both tenants authenticate successfully; ownership is a separate check.
        return ("adapter", None)

    async def get_user_id():
        return "user"

    RouteConfigurator({}, logging.getLogger(__name__))._configure_feedback_endpoints(app, {
        "get_feedback_service": get_feedback_service,
        "get_api_key": get_api_key,
        "get_user_id": get_user_id,
    })
    return TestClient(app), feedback, history


def send(client, method, key, *, bearer=False, comment="Private pricing strategy"):
    headers = {"Authorization": f"Bearer {key}"} if bearer else {"X-API-Key": key}
    if key is None:
        headers = {}
    if method == "GET":
        return client.get(f"/api/feedback/{SESSION}", headers=headers)
    return client.post("/api/feedback", headers=headers, json={
        **FEEDBACK, "session_id": SESSION, "comment": comment,
    })


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("bearer", [False, True])
def test_owner_allowed(feedback_app, method, bearer):
    client, feedback, history = feedback_app
    response = send(client, method, KEY_A, bearer=bearer)
    assert response.status_code == 200
    history.authorize_session.assert_awaited_once_with(SESSION, KEY_A)
    if method == "GET":
        assert response.json() == {"feedbacks": [FEEDBACK]}
        feedback.get_session_feedback.assert_awaited_once_with(SESSION)
    else:
        assert response.json() == {**FEEDBACK, "action": "created"}
        feedback.submit_feedback.assert_awaited_once_with(
            **FEEDBACK, session_id=SESSION, user_id="user", adapter_name="adapter",
        )


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("bearer", [False, True])
@pytest.mark.parametrize("comment", [None, "", "Changed private comment"])
def test_foreign_key_denied_before_feedback_access(feedback_app, method, bearer, comment):
    client, feedback, history = feedback_app
    response = send(client, method, KEY_B, bearer=bearer, comment=comment)
    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied"}
    history.authorize_session.assert_awaited_once_with(SESSION, KEY_B)
    feedback.get_session_feedback.assert_not_awaited()
    feedback.submit_feedback.assert_not_awaited()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("failure", ["missing", "none", "exception"])
def test_authorization_unavailable_fails_closed(feedback_app, method, failure):
    client, feedback, history = feedback_app
    if failure == "missing":
        del client.app.state.chat_history_service
    elif failure == "none":
        client.app.state.chat_history_service = None
    else:
        history.authorize_session.side_effect = RuntimeError("private database details")
    response = send(client, method, KEY_A)
    assert response.status_code == 503
    assert "private database details" not in response.text
    feedback.get_session_feedback.assert_not_awaited()
    feedback.submit_feedback.assert_not_awaited()


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("history_state", ["available", "missing", "none"])
def test_no_key_allows_standalone_feedback(feedback_app, method, history_state):
    client, feedback, history = feedback_app
    if history_state == "missing":
        del client.app.state.chat_history_service
    elif history_state == "none":
        client.app.state.chat_history_service = None
    response = send(client, method, None)
    assert response.status_code == 200
    history.authorize_session.assert_not_awaited()
    if method == "GET":
        assert response.json() == {"feedbacks": [FEEDBACK]}
        feedback.get_session_feedback.assert_awaited_once_with(SESSION)
    else:
        assert response.json() == {**FEEDBACK, "action": "created"}
        feedback.submit_feedback.assert_awaited_once_with(
            **FEEDBACK, session_id=SESSION, user_id="user", adapter_name="adapter",
        )


def test_empty_session_rejected(feedback_app):
    client, feedback, history = feedback_app
    response = client.post("/api/feedback", headers={"X-API-Key": KEY_A}, json={
        **FEEDBACK, "session_id": "",
    })
    assert response.status_code == 422
    history.authorize_session.assert_not_awaited()
    feedback.submit_feedback.assert_not_awaited()
