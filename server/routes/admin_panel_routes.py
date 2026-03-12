"""
Admin Panel Routes — Server-Rendered Admin UI

Serves a vanilla HTML/CSS/JS admin panel at /admin,
reusing dashboard authentication (cookie-based).
"""

import html
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pathlib import Path
from urllib.parse import quote

from routes.dashboard_routes import _get_dashboard_admin_user, _dashboard_login_html

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_admin_panel_html_cache: Optional[str] = None
_admin_panel_template_mtime: Optional[float] = None
_admin_panel_static_versions: Dict[str, str] = {}


def _load_admin_panel_template() -> str:
    """Load admin panel HTML template with mtime-based caching."""
    global _admin_panel_html_cache, _admin_panel_template_mtime, _admin_panel_static_versions

    template_path = TEMPLATE_DIR / "admin_panel.html"
    try:
        current_mtime = template_path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Admin panel template not found at %s", template_path)
        return "<h1>Admin panel template missing</h1>"

    static_files = {
        "{{ADMIN_PANEL_CSS_VERSION}}": TEMPLATE_DIR / "admin_panel.css",
        "{{ADMIN_PANEL_JS_VERSION}}": TEMPLATE_DIR / "admin_panel.js",
    }

    reload_required = (
        _admin_panel_html_cache is None
        or _admin_panel_template_mtime != current_mtime
    )
    new_versions: Dict[str, str] = {}
    for placeholder, path in static_files.items():
        try:
            version = str(path.stat().st_mtime)
        except FileNotFoundError:
            version = "0"
        new_versions[placeholder] = version
        if not reload_required and _admin_panel_static_versions.get(placeholder) != version:
            reload_required = True

    if reload_required:
        content = template_path.read_text()
        for placeholder, version in new_versions.items():
            content = content.replace(placeholder, version)
        _admin_panel_html_cache = content
        _admin_panel_template_mtime = current_mtime
        _admin_panel_static_versions = new_versions

    return _admin_panel_html_cache


def create_admin_panel_router() -> APIRouter:
    """Create admin panel router."""
    router = APIRouter(tags=["admin-panel"])

    @router.get("/admin", response_class=HTMLResponse)
    async def get_admin_panel(request: Request):
        """Serve the admin panel."""
        user_info = await _get_dashboard_admin_user(request)
        if not user_info:
            return RedirectResponse(
                url=f"/dashboard/login?next={quote('/admin')}",
                status_code=303,
            )
        return HTMLResponse(content=_load_admin_panel_template())

    @router.get("/admin/api/token", response_class=JSONResponse)
    async def get_admin_panel_token(request: Request):
        """Relay the httponly cookie token to JS for API calls."""
        user_info = await _get_dashboard_admin_user(request)
        if not user_info:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required"},
            )
        token = request.cookies.get("dashboard_token")
        return JSONResponse(content={"token": token, "user": user_info})

    @router.post("/admin/logout")
    async def post_admin_panel_logout(request: Request):
        """Logout and redirect to login."""
        auth_service = getattr(request.app.state, "auth_service", None)
        if auth_service:
            token = request.cookies.get("dashboard_token")
            if token:
                try:
                    await auth_service.logout(token)
                except Exception:
                    logger.debug("Failed to revoke token during admin panel logout", exc_info=True)

        response = RedirectResponse(url="/dashboard/login", status_code=303)
        response.delete_cookie("dashboard_token", path="/")
        return response

    return router
