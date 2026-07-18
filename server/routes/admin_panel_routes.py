"""
Admin Panel Routes — Server-Rendered Admin UI

Serves a vanilla HTML/CSS/JS admin panel at /admin,
with integrated login, logout, and export endpoints.
"""

import base64
import json
import logging
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pathlib import Path
from urllib.parse import quote

from routes.auth_helpers import get_admin_user, get_sso_service, render_login_html

# User-facing messages for /admin/login?error=<code>
_SSO_ERROR_MESSAGES = {
    "sso_unavailable": "SSO sign-in is not available.",
    "sso_failed": "SSO sign-in failed. Please try again.",
    "not_authorized": "Your account is not authorized for admin access.",
}

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


def _feedback_datetime(value: Any) -> Optional[datetime]:
    """Normalize database date values to timezone-aware UTC datetimes."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _feedback_excerpt(value: Any, limit: int) -> Optional[str]:
    """Return a compact single-line excerpt suitable for the analytics payload."""
    if not isinstance(value, str):
        return None
    compact = " ".join(value.split())
    if not compact:
        return None
    return compact if len(compact) <= limit else compact[:limit - 1].rstrip() + "…"


def _feedback_rate(positive: int, total: int) -> Optional[float]:
    return round((positive / total) * 100, 1) if total else None


async def _feedback_records(database_service, query: Dict[str, Any], limit: int = 10000) -> List[Dict[str, Any]]:
    """Read feedback in bounded pages so analytics works across all DB backends."""
    records: List[Dict[str, Any]] = []
    page_size = 1000
    while len(records) < limit:
        batch = await database_service.find_many(
            "feedback",
            query,
            limit=min(page_size, limit - len(records)),
            sort=[("created_at", -1)],
            skip=len(records),
        )
        records.extend(batch)
        if len(batch) < page_size:
            break
    return records


def create_admin_panel_router() -> APIRouter:
    """Create admin panel router."""
    router = APIRouter(tags=["admin-panel"])

    # ----- Login -----

    def _sso_providers(request: Request) -> Optional[Dict[str, str]]:
        """Enabled SSO provider -> label, for rendering login buttons."""
        sso = get_sso_service(request)
        return sso.provider_labels() if sso else None

    @router.get("/admin/login", response_class=HTMLResponse)
    async def get_admin_login(request: Request, next: str = "/admin", error: Optional[str] = None):
        """Render the admin login page."""
        next_path = next if next and next.startswith("/") else "/admin"
        user_info = await get_admin_user(request)
        if user_info:
            return RedirectResponse(url=next_path, status_code=303)
        return HTMLResponse(content=render_login_html(
            next_path=next_path,
            error_message=_SSO_ERROR_MESSAGES.get(error),
            sso_providers=_sso_providers(request),
        ))

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
                    error_message="Invalid admin username or password.",
                    sso_providers=_sso_providers(request),
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

    # ----- SSO (external identity providers) -----

    def _login_redirect(error: Optional[str] = None):
        """Redirect back to the login page, optionally with an error code."""
        url = "/admin/login" + (f"?error={error}" if error else "")
        resp = RedirectResponse(url=url, status_code=303)
        resp.delete_cookie("admin_sso_flow", path="/admin")
        return resp

    @router.get("/admin/auth/{provider}/login")
    async def admin_sso_login(request: Request, provider: str, next: str = "/admin"):
        """Begin an SSO login: redirect to the provider's authorize endpoint."""
        sso = get_sso_service(request)
        if not sso or not sso.provider_enabled(provider):
            return _login_redirect("sso_unavailable")

        next_path = next if next and next.startswith("/") else "/admin"
        redirect_uri = sso.redirect_uri(provider, str(request.base_url))
        auth_url, state, code_verifier, nonce = sso.build_authorize_url(provider, redirect_uri)

        flow = json.dumps({
            "provider": provider, "state": state,
            "verifier": code_verifier, "nonce": nonce, "next": next_path,
        })
        response = RedirectResponse(url=auth_url, status_code=303)
        response.set_cookie(
            "admin_sso_flow",
            base64.urlsafe_b64encode(flow.encode("utf-8")).decode("ascii"),
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=300,
            path="/admin",
        )
        return response

    @router.get("/admin/auth/{provider}/callback")
    async def admin_sso_callback(
        request: Request,
        provider: str,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Complete an SSO login: validate the id_token and mint a session cookie."""
        sso = get_sso_service(request)
        if not sso or not sso.provider_enabled(provider):
            return _login_redirect("sso_unavailable")

        raw = request.cookies.get("admin_sso_flow")
        if error or not code or not state or not raw:
            return _login_redirect("sso_failed")

        try:
            flow = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8"))
        except Exception:
            return _login_redirect("sso_failed")

        if flow.get("provider") != provider or not secrets.compare_digest(str(flow.get("state", "")), state):
            return _login_redirect("sso_failed")

        redirect_uri = sso.redirect_uri(provider, str(request.base_url))
        tokens = await sso.exchange_code(provider, code, flow.get("verifier", ""), redirect_uri)
        if not tokens or not tokens.get("id_token"):
            return _login_redirect("sso_failed")

        claims = await sso.validate_id_token(provider, tokens["id_token"], flow.get("nonce", ""))
        if not claims:
            return _login_redirect("sso_failed")

        subject = claims["sub"]
        email = claims.get("email") or claims.get("preferred_username")
        if not sso.is_admin(email, provider, subject):
            logger.warning(
                "Admin SSO denied for %s: email=%r subject=%r not on admin_users allowlist",
                provider, email, subject,
            )
            return _login_redirect("not_authorized")

        auth_service = getattr(request.app.state, "auth_service", None)
        if not auth_service:
            raise HTTPException(status_code=503, detail="Authentication service not available")

        user = await auth_service.provision_sso_user(provider, subject, email, is_admin=True)
        if not user or not user.get("active", True) or user.get("role") != "admin":
            return _login_redirect("not_authorized")

        token = await auth_service.create_session(user)

        destination = flow.get("next") or "/admin"
        if not destination.startswith("/"):
            destination = "/admin"
        response = RedirectResponse(url=destination, status_code=303)
        response.set_cookie(
            "dashboard_token",
            token,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
            max_age=int(getattr(auth_service, "session_duration_hours", 12) * 3600),
        )
        response.delete_cookie("admin_sso_flow", path="/admin")
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

    @router.get("/admin/api/feedback-analytics", response_class=JSONResponse)
    async def get_feedback_analytics(request: Request, days: int = 30):
        """Return current feedback health, trends, adapter breakdowns, and examples."""
        user_info = await get_admin_user(request)
        if not user_info:
            raise HTTPException(status_code=401, detail="Authentication required")
        if days not in (7, 30, 90, 365):
            raise HTTPException(status_code=400, detail="days must be one of 7, 30, 90, or 365")

        feedback_service = getattr(request.app.state, "feedback_service", None)
        if feedback_service is None:
            from services.feedback_service import FeedbackService
            feedback_service = FeedbackService(
                request.app.state.config,
                database_service=getattr(request.app.state, "database_service", None),
            )
            await feedback_service.initialize()
            request.app.state.feedback_service = feedback_service

        database_service = feedback_service.database_service
        now = datetime.now(timezone.utc)
        first_day = now.date() - timedelta(days=days - 1)
        window_start = datetime.combine(first_day, datetime.min.time(), tzinfo=timezone.utc)
        feedback_query = {"created_at": {"$gte": window_start.isoformat()}}

        records = await _feedback_records(database_service, feedback_query)
        source_count = await database_service.count("feedback", feedback_query)
        source_count = max(source_count, len(records))

        positive = sum(1 for item in records if item.get("feedback_type") == "up")
        negative = sum(1 for item in records if item.get("feedback_type") == "down")
        rated_total = positive + negative
        negative_comments = sum(
            1 for item in records
            if item.get("feedback_type") == "down" and str(item.get("comment") or "").strip()
        )
        unique_sessions = {str(item.get("session_id")) for item in records if item.get("session_id")}
        unique_users = {str(item.get("user_id")) for item in records if item.get("user_id")}

        trend_map: Dict[str, Dict[str, int]] = defaultdict(lambda: {"positive": 0, "negative": 0})
        adapter_map: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"positive": 0, "negative": 0, "comments": 0}
        )
        for item in records:
            feedback_type = item.get("feedback_type")
            created_at = _feedback_datetime(item.get("created_at"))
            if created_at and feedback_type in ("up", "down"):
                trend_key = created_at.date().isoformat()
                trend_map[trend_key]["positive" if feedback_type == "up" else "negative"] += 1

            adapter_name = str(item.get("adapter_name") or "Unknown")
            if feedback_type == "up":
                adapter_map[adapter_name]["positive"] += 1
            elif feedback_type == "down":
                adapter_map[adapter_name]["negative"] += 1
            if str(item.get("comment") or "").strip():
                adapter_map[adapter_name]["comments"] += 1

        trend = []
        for offset in range(days):
            day = first_day + timedelta(days=offset)
            counts = trend_map[day.isoformat()]
            total = counts["positive"] + counts["negative"]
            trend.append({
                "date": day.isoformat(),
                "positive": counts["positive"],
                "negative": counts["negative"],
                "total": total,
                "satisfaction_rate": _feedback_rate(counts["positive"], total),
            })

        adapters = []
        for name, counts in adapter_map.items():
            total = counts["positive"] + counts["negative"]
            adapters.append({
                "adapter": name,
                "positive": counts["positive"],
                "negative": counts["negative"],
                "total": total,
                "comments": counts["comments"],
                "satisfaction_rate": _feedback_rate(counts["positive"], total),
            })
        adapters.sort(key=lambda item: (-item["total"], item["adapter"].lower()))

        # Feedback and chat history share message/session identifiers. Enrich only the
        # most recent negative examples to keep the endpoint useful and inexpensive.
        chat_history_service = getattr(request.app.state, "chat_history_service", None)
        chat_collection = getattr(chat_history_service, "collection_name", "chat_history")
        recent_negative = []
        user_cache: Dict[str, Optional[str]] = {}
        negative_records = [item for item in records if item.get("feedback_type") == "down"][:25]
        auth_service = getattr(request.app.state, "auth_service", None)
        users_collection = getattr(auth_service, "users_collection_name", "users")

        for item in negative_records:
            session_id = item.get("session_id")
            message_id = item.get("message_id")
            assistant_message = None
            user_prompt = None
            if session_id and message_id and chat_history_service is not None:
                # Resolve the exact rated response by its primary key. This avoids a
                # global history fan-out cap starving a busy session's example.
                assistant_message = await database_service.find_one(
                    chat_collection,
                    {"_id": str(message_id), "session_id": session_id, "role": "assistant"},
                )
                if assistant_message and assistant_message.get("timestamp"):
                    nearby_history = await database_service.find_many(
                        chat_collection,
                        {
                            "session_id": session_id,
                            "timestamp": {"$lte": assistant_message["timestamp"]},
                        },
                        limit=8,
                        sort=[("timestamp", -1)],
                    )
                    preceding = next(
                        (
                            candidate for candidate in nearby_history
                            if candidate.get("role") == "user"
                        ),
                        None,
                    )
                    if preceding:
                        user_prompt = _feedback_excerpt(preceding.get("content"), 500)

            user_id = str(item.get("user_id")) if item.get("user_id") else None
            user_label = None
            if user_id:
                if user_id not in user_cache:
                    user_doc = await database_service.find_one(users_collection, {"_id": user_id})
                    user_cache[user_id] = (
                        _feedback_excerpt(user_doc.get("email") or user_doc.get("username"), 120)
                        if user_doc else None
                    )
                user_label = user_cache[user_id]

            feedback_created_at = _feedback_datetime(item.get("created_at"))
            recent_negative.append({
                "created_at": feedback_created_at.isoformat() if feedback_created_at else None,
                "adapter": item.get("adapter_name") or "Unknown",
                "session_id": session_id,
                "user": user_label or ("Authenticated user" if user_id else "Anonymous"),
                "comment": _feedback_excerpt(item.get("comment"), 2000),
                "user_prompt": user_prompt,
                "assistant_response": _feedback_excerpt(
                    assistant_message.get("content") if assistant_message else None,
                    800,
                ),
            })

        eligible_messages = None
        if chat_history_service is not None:
            eligible_messages = await database_service.count(
                chat_collection,
                {"role": "assistant", "timestamp": {"$gte": window_start.isoformat()}},
            )

        return JSONResponse(content={
            "window": {
                "days": days,
                "start": window_start.isoformat(),
                "end": now.isoformat(),
                "basis": "Current ratings grouped by their creation date",
            },
            "summary": {
                "total": rated_total,
                "positive": positive,
                "negative": negative,
                "satisfaction_rate": _feedback_rate(positive, rated_total),
                "comments": negative_comments,
                "negative_comment_rate": _feedback_rate(negative_comments, negative),
                "sessions": len(unique_sessions),
                "users": len(unique_users),
                "eligible_messages": eligible_messages,
                "response_rate": (
                    _feedback_rate(rated_total, eligible_messages)
                    if (
                        eligible_messages is not None
                        and eligible_messages >= rated_total
                        and source_count == len(records)
                    ) else None
                ),
            },
            "trend": trend,
            "adapters": adapters,
            "recent_negative": recent_negative,
            "meta": {
                "generated_at": now.isoformat(),
                "source_records": source_count,
                "record_limit": 10000,
                "truncated": source_count > len(records),
            },
        })

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
