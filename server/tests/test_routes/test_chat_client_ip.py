"""Chat routes pass a usable client IP to conversation logging."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.routes_configurator import RouteConfigurator


def _build_app(config):
    app = FastAPI()
    configurator = RouteConfigurator(config, logging.getLogger(__name__))
    configurator._create_dependencies()
    configurator._configure_chat_endpoint(app)

    chat_service = MagicMock()
    chat_service.authorize_session_access = AsyncMock()
    chat_service.process_chat = AsyncMock(return_value={"response": "hello"})

    app.dependency_overrides[configurator.check_not_paused] = lambda: None
    app.dependency_overrides[configurator.get_chat_service] = lambda: chat_service
    app.dependency_overrides[configurator.get_api_key] = lambda: ("test-adapter", None)
    app.dependency_overrides[configurator.validate_session_id] = lambda: "sess1"
    app.dependency_overrides[configurator.get_user_id] = lambda: None
    return app, chat_service


@pytest.mark.parametrize("path", ["/v1/chat", "/v1/chat/completions"])
@pytest.mark.parametrize("client_ip", ["127.0.0.1", "::1"])
def test_chat_uses_numeric_loopback_ip(path, client_ip):
    app, chat_service = _build_app({})
    response = TestClient(app, client=(client_ip, 12345)).post(
        path, json={"messages": [{"role": "user", "content": "hi"}]}
    )

    assert response.status_code == 200
    assert chat_service.process_chat.await_args.kwargs["client_ip"] == client_ip


@pytest.mark.parametrize("path", ["/v1/chat", "/v1/chat/completions"])
def test_chat_uses_first_forwarded_private_ip(path):
    config = {"security": {"rate_limiting": {
        "trust_proxy_headers": True, "trusted_proxies": ["127.0.0.1"]
    }}}
    app, chat_service = _build_app(config)
    response = TestClient(app, client=("127.0.0.1", 12345)).post(
        path,
        headers={"X-Forwarded-For": "10.0.0.1, 198.51.100.2"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert chat_service.process_chat.await_args.kwargs["client_ip"] == "10.0.0.1"


@pytest.mark.parametrize("path", ["/v1/chat", "/v1/chat/completions"])
def test_chat_ignores_untrusted_forwarded_ip(path):
    app, chat_service = _build_app({})
    response = TestClient(app, client=("127.0.0.1", 12345)).post(
        path,
        headers={"X-Forwarded-For": "198.51.100.2"},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert chat_service.process_chat.await_args.kwargs["client_ip"] == "127.0.0.1"
