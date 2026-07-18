"""
Shared authentication helpers for admin routes.

Extracted from dashboard_routes.py to avoid circular imports
between dashboard/metrics routes and admin panel routes.
"""

import base64
import html
import logging
from http.cookies import SimpleCookie
from typing import Dict, Any, Optional
from urllib.parse import quote
from fastapi import Request, WebSocket, HTTPException
from pathlib import Path

from auth.rbac import has_any_permission, has_permission

logger = logging.getLogger(__name__)

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


def _render_sso_block(next_path: str, sso_providers: Optional[Dict[str, str]]) -> str:
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
    sso_providers: Optional[Dict[str, str]] = None,
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


async def get_admin_user(request: Request) -> Optional[Dict[str, Any]]:
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


async def require_admin(request: Request) -> Dict[str, Any]:
    """Require an authenticated admin via cookie token."""
    user_info = await get_admin_user(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_info


def check_service_availability(service, service_name: str) -> None:
    """Raise HTTP 503 if a required service is not initialized."""
    if service is None:
        raise HTTPException(status_code=503, detail=f"{service_name} is not available")


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
