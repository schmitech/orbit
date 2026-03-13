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
from fastapi import Request, WebSocket, HTTPException
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_login_template_cache = None
_login_template_mtime: Optional[float] = None


def load_login_template() -> str:
    """Load the login template with simple change detection."""
    global _login_template_cache, _login_template_mtime
    template_path = TEMPLATE_DIR / "admin_login.html"
    try:
        current_mtime = template_path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Login template not found at %s", template_path)
        return "<h1>Login template missing</h1>"

    if _login_template_cache is None or _login_template_mtime != current_mtime:
        _login_template_cache = template_path.read_text()
        _login_template_mtime = current_mtime

    return _login_template_cache


def render_login_html(next_path: str = "/admin", error_message: Optional[str] = None) -> str:
    """Render the login template."""
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
    )


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
    if not valid or not user_info or user_info.get("role") != "admin":
        return None

    return user_info


async def require_admin(request: Request) -> Dict[str, Any]:
    """Require an authenticated admin via cookie token."""
    user_info = await get_admin_user(request)
    if not user_info:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_info


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
                if valid and user_info and user_info.get("role") == "admin":
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
    if not success or not user_info or user_info.get("role") != "admin":
        await websocket.close(code=4403, reason="Admin credentials required")
        return False

    return True
