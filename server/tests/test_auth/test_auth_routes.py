"""Authentication-route response contracts."""

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from routes.auth_routes import auth_router  # noqa: E402


def test_auth_me_without_bearer_token_is_401_not_500():
    """/auth/me requires identity even though the shared dependency is optional."""
    app = FastAPI()
    app.state.auth_service = object()
    app.include_router(auth_router)

    response = TestClient(app, raise_server_exceptions=False).get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Authentication required"
