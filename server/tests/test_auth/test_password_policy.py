"""Unit tests for configurable local-password complexity validation."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from services.auth_service import AuthService  # noqa: E402
from routes.auth_dependencies import get_current_user  # noqa: E402
from routes.auth_routes import auth_router  # noqa: E402


STRICT_POLICY = {
    "min_length": 12,
    "max_length": 128,
    "require_uppercase": True,
    "require_lowercase": True,
    "require_digit": True,
    "require_symbol": True,
    "reject_common_passwords": True,
}


def validate(password, policy=STRICT_POLICY):
    return AuthService.validate_password(password, policy)


def test_policy_rejects_each_complexity_rule():
    assert "at least 12" in validate("Aa1!")
    assert "uppercase" in validate("lowercase1!x")
    assert "lowercase" in validate("UPPERCASE1!X")
    assert "digit" in validate("NoDigitsHere!")
    assert "symbol" in validate("NoSymbols123")
    assert "too common" in validate(
        "password123", {"reject_common_passwords": True}
    )


def test_policy_aggregates_all_unmet_rules():
    error = validate("short")

    assert error is not None
    assert "at least 12" in error
    assert "uppercase" in error
    assert "digit" in error
    assert "symbol" in error
    assert "; " in error


def test_policy_enforces_maximum_length_and_allows_valid_password():
    assert "at most 16" in validate("A1!" + "a" * 20, {
        **STRICT_POLICY, "max_length": 16,
    })
    assert validate("LongEnough1!a") is None


def test_absent_policy_preserves_legacy_length_only_behavior():
    assert AuthService.validate_password("password123") is None
    assert AuthService.validate_password("short") == "Password must be at least 8 characters"


def test_password_policy_endpoint_returns_normalized_active_policy():
    app = FastAPI()
    app.state.auth_service = SimpleNamespace(password_policy={
        "min_length": "14",
        "require_digit": "true",
    })
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin"}
    app.include_router(auth_router)

    response = TestClient(app).get("/auth/password-policy")

    assert response.status_code == 200
    assert response.json() == {
        "min_length": 14,
        "max_length": 128,
        "require_uppercase": False,
        "require_lowercase": False,
        "require_digit": True,
        "require_symbol": False,
        "reject_common_passwords": False,
    }


def test_normalized_policy_never_exceeds_transport_password_limit():
    policy = AuthService.normalize_password_policy({
        "min_length": 20,
        "max_length": 1000,
    })

    assert policy["min_length"] == 20
    assert policy["max_length"] == AuthService.PASSWORD_MAX_LENGTH


@pytest.mark.asyncio
async def test_default_admin_must_satisfy_configured_password_policy():
    database = SimpleNamespace(
        find_one=AsyncMock(return_value=None),
        insert_one=AsyncMock(),
    )
    auth_service = AuthService({
        "auth": {
            "default_admin_username": "admin",
            "default_admin_password": "admin123",
            "password_policy": STRICT_POLICY,
        }
    }, database)

    with pytest.raises(ValueError, match="Default admin password does not satisfy"):
        await auth_service._create_default_admin()

    database.insert_one.assert_not_awaited()
