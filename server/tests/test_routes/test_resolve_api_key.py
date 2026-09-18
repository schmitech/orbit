"""
`resolve_api_key` (routes/auth_helpers.py) is the shared X-API-Key /
Authorization: Bearer resolver behind `RouteConfigurator._resolve_api_key`
and `get_api_key`. `allow_bearer_fallback=False` call sites must never treat
a bearer token as an API key — that gate is what keeps this helper from
expanding behavior on the header-only call sites (file_routes,
discovery_routes, auth_dependencies.permission_or_api_key) it was not
migrated into.
"""

from unittest.mock import Mock

from routes.auth_helpers import resolve_api_key


def _request(headers: dict[str, str]):
    request = Mock()
    request.headers = headers
    return request


def test_x_api_key_header_is_used_when_present():
    request = _request({"X-API-Key": "key-from-header"})
    assert resolve_api_key(request, {}) == "key-from-header"


def test_bearer_fallback_used_when_enabled_and_header_absent():
    request = _request({"Authorization": "Bearer token-123"})
    assert resolve_api_key(request, {}, allow_bearer_fallback=True) == "token-123"


def test_bearer_fallback_not_used_when_disabled():
    request = _request({"Authorization": "Bearer token-123"})
    assert resolve_api_key(request, {}, allow_bearer_fallback=False) is None


def test_neither_header_present_returns_none():
    request = _request({})
    assert resolve_api_key(request, {}) is None


def test_x_api_key_takes_precedence_over_bearer():
    request = _request({"X-API-Key": "from-header", "Authorization": "Bearer from-bearer"})
    assert resolve_api_key(request, {}, allow_bearer_fallback=True) == "from-header"


def test_custom_header_name_from_config_is_respected():
    request = _request({"X-Custom-Key": "custom-value"})
    config = {"api_keys": {"header_name": "X-Custom-Key"}}
    assert resolve_api_key(request, config) == "custom-value"


def test_non_bearer_authorization_header_is_ignored():
    request = _request({"Authorization": "Basic dXNlcjpwYXNz"})
    assert resolve_api_key(request, {}, allow_bearer_fallback=True) is None
