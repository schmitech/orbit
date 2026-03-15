"""
Admin Panel Routes — Server-Rendered Admin UI

Serves a vanilla HTML/CSS/JS admin panel at /admin,
with integrated login, logout, and export endpoints.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pathlib import Path
from urllib.parse import quote

from routes.auth_helpers import get_admin_user, render_login_html

logger = logging.getLogger(__name__)

ADMIN_DIR = Path(__file__).parent.parent / "admin"

_admin_panel_html_cache: Optional[str] = None
_admin_panel_template_mtime: Optional[float] = None
_admin_panel_static_versions: Dict[str, str] = {}


def _load_admin_panel_template() -> str:
    """Load admin panel HTML template with mtime-based caching."""
    global _admin_panel_html_cache, _admin_panel_template_mtime, _admin_panel_static_versions

    template_path = ADMIN_DIR / "admin_panel.html"
    try:
        current_mtime = template_path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Admin panel template not found at %s", template_path)
        return "<h1>Admin panel template missing</h1>"

    static_files = {
        "{{ADMIN_PANEL_CSS_VERSION}}": ADMIN_DIR / "admin_panel.css",
        "{{ADMIN_PANEL_JS_VERSION}}": ADMIN_DIR / "admin_panel.js",
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


def _get_adapter_manager(request: Request):
    """Get adapter manager from app state."""
    manager = getattr(request.app.state, 'fault_tolerant_adapter_manager', None)
    if not manager:
        manager = getattr(request.app.state, 'adapter_manager', None)
    return manager


def create_admin_panel_router() -> APIRouter:
    """Create admin panel router."""
    router = APIRouter(tags=["admin-panel"])

    # ----- Login -----

    @router.get("/admin/login", response_class=HTMLResponse)
    async def get_admin_login(request: Request, next: str = "/admin"):
        """Render the admin login page."""
        next_path = next if next and next.startswith("/") else "/admin"
        user_info = await get_admin_user(request)
        if user_info:
            return RedirectResponse(url=next_path, status_code=303)
        return HTMLResponse(content=render_login_html(next_path=next_path))

    @router.post("/admin/login")
    async def post_admin_login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next: str = Form("/admin")
    ):
        """Authenticate an admin user."""
        auth_service = getattr(request.app.state, 'auth_service', None)
        if not auth_service:
            raise HTTPException(status_code=503, detail="Authentication service not available")

        if not getattr(auth_service, "_initialized", True):
            await auth_service.initialize()

        success, token, user_info = await auth_service.authenticate_user(username, password)
        if not success or not token or not user_info or user_info.get("role") != "admin":
            return HTMLResponse(
                content=render_login_html(
                    next_path=next if next and next.startswith("/") else "/admin",
                    error_message="Invalid admin username or password."
                ),
                status_code=401
            )

        destination = next if next and next.startswith("/") else "/admin"
        response = RedirectResponse(url=destination, status_code=303)
        secure_cookie = request.url.scheme == "https"
        response.set_cookie(
            "dashboard_token",
            token,
            httponly=True,
            secure=secure_cookie,
            samesite="lax",
            max_age=int(getattr(auth_service, "session_duration_hours", 12) * 3600)
        )
        return response

    # ----- Panel -----

    @router.get("/admin", response_class=HTMLResponse)
    async def get_admin_panel(request: Request):
        """Serve the admin panel."""
        user_info = await get_admin_user(request)
        if not user_info:
            return RedirectResponse(
                url=f"/admin/login?next={quote('/admin')}",
                status_code=303,
            )
        return HTMLResponse(content=_load_admin_panel_template())

    @router.get("/admin/api/token", response_class=JSONResponse)
    async def get_admin_panel_token(request: Request):
        """Relay the httponly cookie token to JS for API calls."""
        user_info = await get_admin_user(request)
        if not user_info:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required"},
            )
        token = request.cookies.get("dashboard_token")
        return JSONResponse(content={"token": token, "user": user_info})

    # ----- Logout -----

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

        response = RedirectResponse(url="/admin/login", status_code=303)
        response.delete_cookie("dashboard_token", path="/")
        return response

    # ----- Export -----

    @router.get("/admin/export")
    async def export_snapshot(request: Request):
        """Export a complete metrics snapshot as JSON for incident reports."""
        user_info = await get_admin_user(request)
        if not user_info:
            return RedirectResponse(
                url=f"/admin/login?next={quote(request.url.path)}",
                status_code=303
            )

        metrics_service = getattr(request.app.state, 'metrics_service', None)
        if not metrics_service or not metrics_service.is_enabled():
            raise HTTPException(status_code=503, detail="Metrics service not available")

        snapshot: Dict[str, Any] = {
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'metrics': metrics_service.get_dashboard_metrics(),
        }
        # Adapters
        adapter_manager = _get_adapter_manager(request)
        if adapter_manager:
            try:
                if hasattr(adapter_manager, 'get_health_status'):
                    health = adapter_manager.get_health_status()
                    snapshot['adapters'] = health.get('circuit_breakers', {})
                elif hasattr(adapter_manager, 'parallel_executor') and adapter_manager.parallel_executor:
                    if hasattr(adapter_manager.parallel_executor, 'get_circuit_breaker_status'):
                        snapshot['adapters'] = adapter_manager.parallel_executor.get_circuit_breaker_status()
            except Exception:
                pass
        # Thread pools
        tpm = getattr(request.app.state, 'thread_pool_manager', None)
        if tpm:
            try:
                snapshot['thread_pools'] = tpm.get_pool_stats()
            except Exception:
                pass
        # Pipeline
        pm = getattr(request.app.state, 'pipeline_monitor', None)
        if pm:
            try:
                snapshot['pipeline'] = json.loads(pm.export_metrics(format='json'))
            except Exception:
                pass

        return Response(
            content=json.dumps(snapshot, indent=2, default=str),
            media_type="application/json",
            headers={
                'Content-Disposition': f'attachment; filename="orbit-snapshot-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json"'
            }
        )

    return router
