"""
Shared authentication helpers for admin routes.

Extracted from dashboard_routes.py to avoid circular imports
between dashboard/metrics routes and admin panel routes.
"""

import base64
import html
import logging
from http.cookies import SimpleCookie
from typing import Any, Optional
from urllib.parse import quote
from fastapi import Request, WebSocket, HTTPException
from pathlib import Path

from auth.rbac import has_any_permission, has_permission
from utils import is_true_value

logger = logging.getLogger(__name__)

# Sentinel distinguishing "not yet resolved" from a cached negative (anonymous/invalid) result.
_UNRESOLVED = object()

# Sentinel returned by require_authenticated_user_ws when it has already closed the
# socket, distinguishing that from "anonymous but allowed" (which returns None).
WS_AUTH_CLOSED = object()

ADMIN_DIR = Path(__file__).parent.parent / "admin"

_login_template_cache = None
_login_template_mtime: Optional[float] = None


def load_login_template() -> str:
    """Load the login template with simple change detection."""
    global _login_template_cache, _login_template_mtime
    template_path = ADMIN_DIR / "admin_login.html"
    try:
        current_mtime = template_path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Login template not found at %s", template_path)
        return "<h1>Login template missing</h1>"

    if _login_template_cache is None or _login_template_mtime != current_mtime:
        _login_template_cache = template_path.read_text()
        _login_template_mtime = current_mtime

    return _login_template_cache


def _render_sso_block(next_path: str, sso_providers: Optional[dict[str, str]]) -> str:
    """Build the 'or continue with' block of provider sign-in buttons."""
    if not sso_providers:
        return ""
    next_q = quote(next_path, safe="")
    buttons = []
    for name, label in sso_providers.items():
        href = f"/admin/auth/{html.escape(name, quote=True)}/login?next={next_q}"
        buttons.append(
            f'<a class="sso-button" href="{href}">Sign in with {html.escape(label)}</a>'
        )
    return (
        '<div class="sso-divider"><span>or continue with</span></div>'
        f'<div class="sso-buttons">{"".join(buttons)}</div>'
    )


def render_login_html(
    next_path: str = "/admin",
    error_message: Optional[str] = None,
    sso_providers: Optional[dict[str, str]] = None,
) -> str:
    """Render the login template.

    sso_providers maps enabled provider name -> display label; when provided,
    a set of SSO sign-in buttons is rendered below the password form.
    """
    template = load_login_template()
    error_block = ""
    if error_message:
        error_block = (
            f'<div class="login-alert" role="alert">{html.escape(error_message)}</div>'
        )

    return (
        template
        .replace("{{NEXT_PATH}}", html.escape(next_path, quote=True))
        .replace("{{ERROR_BLOCK}}", error_block)
        .replace("{{SSO_BLOCK}}", _render_sso_block(next_path, sso_providers))
    )


def get_sso_service(request: Request):
    """Lazily build and cache the admin SSO service on app.state (None if disabled)."""
    app = request.app
    if hasattr(app.state, "admin_sso_service"):
        return app.state.admin_sso_service

    svc = None
    try:
        config = getattr(app.state, "config", {}) or {}
        providers = config.get("auth", {}).get("providers", {})
        if providers.get("admin_sso", {}).get("enabled"):
            from services.admin_sso_service import AdminSSOService
            built = AdminSSOService(providers)
            svc = built if built.enabled else None
    except Exception as e:
        logger.error("Failed to initialize admin SSO service: %s", e)
        svc = None

    app.state.admin_sso_service = svc
    return svc


async def get_admin_user(request: Request) -> Optional[dict[str, Any]]:
    """Validate the auth cookie and return the admin user."""
    auth_service = getattr(request.app.state, 'auth_service', None)
    if not auth_service:
        raise HTTPException(status_code=503, detail="Authentication service not available")

    if not getattr(auth_service, "_initialized", True):
        await auth_service.initialize()

    token = request.cookies.get("dashboard_token")
    if not token:
        return None

    valid, user_info = await auth_service.validate_token(token)
    if not valid or not user_info or not has_any_permission(user_info):
        return None

    return user_info


async def require_admin(request: Request) -> dict[str, Any]:
    """Require an authenticated admin via cookie token."""
    user_info = await get_admin_user(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_info


def check_service_availability(service, service_name: str) -> None:
    """Raise HTTP 503 if a required service is not initialized."""
    if service is None:
        raise HTTPException(status_code=503, detail=f"{service_name} is not available")


async def resolve_authenticated_user(request: Request, header_name: str = "authorization") -> Optional[dict[str, Any]]:
    """
    Resolve the authenticated ORBIT user context from a bearer token, if present.

    Validates via `auth_service.validate_token`, which handles both opaque
    session tokens and external-provider JWTs (Entra/Auth0), JIT-provisioning
    the latter into the `users` table. Returns None for anonymous/invalid
    requests rather than raising, so callers can treat identity as optional
    (e.g. for API-key allowlist checks that only apply to restricted keys).

    The result (including a negative one) is cached on `request.state` per
    `header_name`, since a single request commonly resolves the same header
    twice (e.g. the API-key and user-id dependencies both call this). Cache
    presence, not the cached value, is the "already resolved" signal, so a
    cached None (anonymous/invalid) is never mistaken for "not yet checked".

    Args:
        header_name: Header to read the "Bearer <token>" credential from.
            Defaults to the standard `Authorization` header. Pass an
            alternate header when the transport's `Authorization` slot is
            already occupied by something else (e.g. A2A uses it for the
            raw API key, so a distinct user credential needs its own header).
    """
    cache = getattr(request.state, "orbit_auth_cache", None)
    if cache is None:
        cache = {}
        request.state.orbit_auth_cache = cache

    cached = cache.get(header_name, _UNRESOLVED)
    if cached is not _UNRESOLVED:
        return cached

    user_info: Optional[dict[str, Any]] = None
    auth_header = request.headers.get(header_name)
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        auth_service = getattr(request.app.state, "auth_service", None)
        if token and auth_service:
            is_valid, resolved = await auth_service.validate_token(token)
            if is_valid and resolved:
                user_info = resolved
                request.state.current_user = user_info

    cache[header_name] = user_info
    return user_info


def normalize_adapter_auth_override(value: Any) -> Optional[bool]:
    """
    Normalize an adapter's `capabilities.requires_authenticated_user` value to a
    tri-state bool: `None` means unset (defer to the global flag), anything else
    is parsed with the same truthy/falsy rules as every other config boolean.

    YAML config substitution (`${SOME_ENV_VAR}`) always produces a string, so
    `requires_authenticated_user: ${REQUIRE_USER}` with `REQUIRE_USER=true`
    arrives here as the string `"true"` — and, just as importantly,
    `REQUIRE_USER=false` arrives as `"false"`. Plain `bool(...)` gets the first
    case right by accident (any non-empty string is truthy) and the second case
    wrong (`bool("false")` is `True`), so this must go through `is_true_value`
    rather than a bare `bool()` cast.
    """
    if value is None:
        return None
    return is_true_value(value)


def is_authenticated_user_required(config: dict[str, Any], adapter_config: Optional[dict[str, Any]] = None) -> bool:
    """
    Decide whether an authenticated user (not just an API key) must be present.

    Precedence: an adapter's `capabilities.requires_authenticated_user` wins
    when explicitly set (true or false); otherwise the global
    `auth.require_authenticated_user` flag decides. This lets a global "on"
    posture carve out an exception for a genuinely public adapter, and lets a
    global "off" posture still lock down one sensitive adapter.
    """
    adapter_override = None
    if adapter_config:
        adapter_override = adapter_config.get("capabilities", {}).get("requires_authenticated_user")
    adapter_override = normalize_adapter_auth_override(adapter_override)

    if adapter_override is not None:
        return adapter_override

    return is_true_value(config.get("auth", {}).get("require_authenticated_user", False))


async def require_authenticated_user(
    request: Request,
    *,
    adapter_config: Optional[dict[str, Any]] = None,
    header_name: str = "authorization",
) -> Optional[dict[str, Any]]:
    """
    Resolve the caller's identity and, if required, enforce that it is present.

    Always resolves identity first (so callers get it back even when not
    strictly required). Raises 401 with a `WWW-Authenticate` header when
    identity is required and absent/invalid. The same generic message is used
    for "no token" and "invalid/blacklisted token" so a caller cannot use the
    response to distinguish a blacklisted account from a bad token.
    """
    user_info = await resolve_authenticated_user(request, header_name)
    if user_info or not is_authenticated_user_required(request.app.state.config, adapter_config):
        return user_info

    auth_header = request.headers.get(header_name)
    if auth_header:
        detail = "Invalid or expired authentication token."
    else:
        detail = (
            "Authentication required. This deployment requires an authenticated user: "
            "send Authorization: Bearer <user-token> and put the API key in the X-API-Key header."
        )
    raise HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": 'Bearer realm="orbit"'},
    )


async def resolve_authenticated_user_ws(
    websocket: WebSocket,
    header_name: str = "authorization",
    query_param: str = "access_token",
) -> Optional[dict[str, Any]]:
    """
    WebSocket counterpart to `resolve_authenticated_user`.

    Browsers cannot set arbitrary headers on the WS handshake, so the token
    may also arrive as a query parameter (default `access_token`), checked
    only when the header is absent. Cached on `websocket.state` the same way
    `resolve_authenticated_user` caches on `request.state`, so resolving
    identity early (e.g. to pass to an API-key allowlist check) and again
    later (e.g. to enforce auth.require_authenticated_user) does not
    re-validate the token twice.
    """
    cache = getattr(websocket.state, "orbit_auth_cache", None)
    if cache is None:
        cache = {}
        websocket.state.orbit_auth_cache = cache

    cached = cache.get(header_name, _UNRESOLVED)
    if cached is not _UNRESOLVED:
        return cached

    user_info: Optional[dict[str, Any]] = None
    auth_header = websocket.headers.get(header_name)
    if not auth_header:
        token = websocket.query_params.get(query_param)
        if token:
            auth_header = f"Bearer {token}"

    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        auth_service = getattr(websocket.app.state, "auth_service", None)
        if token and auth_service:
            is_valid, resolved = await auth_service.validate_token(token)
            if is_valid and resolved:
                user_info = resolved

    cache[header_name] = user_info
    return user_info


async def require_authenticated_user_ws(
    websocket: WebSocket,
    *,
    adapter_config: Optional[dict[str, Any]] = None,
    header_name: str = "authorization",
    query_param: str = "access_token",
) -> Optional[dict[str, Any]]:
    """
    WebSocket counterpart to `require_authenticated_user`.

    Closes the socket (code 4401) before `accept()` rather than raising,
    since raising inside a WS handler produces no HTTP response. Returns
    `WS_AUTH_CLOSED` after closing — callers must check for that sentinel
    (not falsiness) and return immediately, since a plain `None` here means
    "resolved to anonymous, and that's allowed" rather than "rejected".
    """
    config = websocket.app.state.config
    user_info = await resolve_authenticated_user_ws(websocket, header_name, query_param)

    if user_info or not is_authenticated_user_required(config, adapter_config):
        return user_info

    await websocket.close(code=4401, reason="Authentication required")
    return WS_AUTH_CLOSED


async def resolve_authenticated_user_id(request: Request, header_name: str = "authorization") -> Optional[str]:
    """Compatibility wrapper returning just the authenticated ORBIT user id."""
    user_info = await resolve_authenticated_user(request, header_name)
    if not user_info:
        return None
    auth_user_id = user_info.get("id") or user_info.get("user_id") or user_info.get("username")
    return str(auth_user_id).strip() if auth_user_id else None


async def authenticate_websocket_admin(websocket: WebSocket) -> bool:
    """Validate admin auth for WebSocket connections."""
    auth_service = getattr(websocket.app.state, 'auth_service', None)
    if not auth_service:
        await websocket.close(code=1011, reason="Authentication service unavailable")
        return False

    if not getattr(auth_service, "_initialized", True):
        await auth_service.initialize()

    # Try cookie-based session first
    cookie_header = websocket.headers.get('cookie')
    if cookie_header:
        try:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            if "dashboard_token" in cookie:
                token = cookie["dashboard_token"].value
                valid, user_info = await auth_service.validate_token(token)
                if valid and user_info and has_permission(user_info, "metrics.read"):
                    return True
        except Exception:
            pass

    # Fall back to HTTP Basic credentials supplied with the websocket request
    auth_header = websocket.headers.get('authorization')
    if not auth_header or not auth_header.lower().startswith('basic '):
        await websocket.close(code=4401, reason="Authentication required")
        return False

    try:
        decoded = base64.b64decode(auth_header.split(' ', 1)[1]).decode('utf-8')
        username, password = decoded.split(':', 1)
    except Exception:
        await websocket.close(code=4401, reason="Invalid basic auth header")
        return False

    success, user_info = await auth_service.verify_credentials(username, password)
    if not success or not user_info or not has_permission(user_info, "metrics.read"):
        await websocket.close(code=4403, reason="Admin credentials required")
        return False

    return True
