"""
Admin IP Allowlist Middleware
=============================

Defense-in-depth gate on top of authentication and RBAC: restricts `/admin/*`
(the admin panel and its API surface) and the admin-scoped `/auth/*` routes
(user management, blacklist/allowlist, session revocation, this control's own
rules) to a configurable set of IP addresses/CIDR ranges. Regular `/v1/chat`
traffic and other non-admin surfaces are never touched.

Enforcement is delegated to `AuthService.admin_ip_allowlist`
(`services/admin_ip_allowlist_service.py`), read off `app.state.auth_service`
since middleware runs outside FastAPI's dependency-injection system. When
that service isn't ready yet (auth disabled, or still starting up) requests
pass through unaffected — this is a defense-in-depth layer, not the primary
access control.

Loopback requests are always exempt, regardless of configured ranges. This is
what keeps `orbit` CLI commands (which talk to the server over `localhost` by
default) working no matter how narrow an operator configures the allowed
ranges — the single mitigation against the "misconfigure this and lock out
every admin, including yourself" failure mode described in the roadmap plan.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from utils.ip_utils import extract_ip, parse_trusted_networks

logger = logging.getLogger(__name__)

# Every admin-scoped /auth/* route template, mirroring the require_permission
# gates in routes/auth_routes.py. Kept as an explicit list rather than a blanket
# "/auth/*" match so ordinary sign-in (/auth/login, /auth/me, /auth/sessions,
# /auth/change-password, ...) is never affected by this control.
_ADMIN_AUTH_PATH_TEMPLATES = (
    "/auth/roles",
    "/auth/register",
    "/auth/reset-password",
    "/auth/users",
    "/auth/users/by-username",
    "/auth/users/{user_id}",
    "/auth/users/{user_id}/roles",
    "/auth/users/{user_id}/deactivate",
    "/auth/users/{user_id}/activate",
    "/auth/users/{user_id}/sessions",
    "/auth/users/{user_id}/sessions/{session_id}",
    "/auth/blacklist",
    "/auth/blacklist/{rule_id}",
    "/auth/allowlist",
    "/auth/allowlist/{rule_id}",
    "/auth/admin-ip-rules",
    "/auth/admin-ip-rules/{rule_id}",
)


def _template_to_regex(template: str) -> re.Pattern:
    pattern = re.sub(r"\{([^/}]+)\}", r"[^/]+", template)
    return re.compile(f"^{pattern}$")


_ADMIN_AUTH_PATH_REGEXES = [_template_to_regex(t) for t in _ADMIN_AUTH_PATH_TEMPLATES]


def _is_gated_path(path: str) -> bool:
    if path.startswith("/admin"):
        return True
    return any(regex.match(path) for regex in _ADMIN_AUTH_PATH_REGEXES)


class AdminIpAllowlistMiddleware(BaseHTTPMiddleware):
    """Denies gated admin requests from IPs outside the configured allowlist."""

    def __init__(self, app, config: Optional[dict[str, Any]] = None):
        super().__init__(app)
        security_cfg = (config or {}).get("security", {}) or {}
        rate_cfg = security_cfg.get("rate_limiting", {}) or {}
        # Reuse the rate limiter's proxy-trust configuration exactly, so a
        # reverse-proxy misconfiguration can't make this check and the rate
        # limiter disagree about who a request is actually from.
        self._trust_proxy = rate_cfg.get("trust_proxy_headers", False)
        self._trusted_networks = parse_trusted_networks(rate_cfg.get("trusted_proxies", []))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not _is_gated_path(path):
            return await call_next(request)

        auth_service = getattr(request.app.state, "auth_service", None)
        service = getattr(auth_service, "admin_ip_allowlist", None) if auth_service else None
        if service is None or not service.enforcing:
            return await call_next(request)

        ip, ip_metadata = extract_ip(
            request, trust_proxy=self._trust_proxy, trusted_networks=self._trusted_networks
        )
        if ip == "localhost":
            return await call_next(request)

        if await service.is_allowed(ip):
            return await call_next(request)

        logger.warning(f"Admin IP allowlist denied {request.method} {path} from {ip}")
        await self._log_denial(request, path, ip, ip_metadata)
        return JSONResponse(
            status_code=403,
            content={"detail": "Access to the admin interface is not permitted from this network"},
        )

    async def _log_denial(
        self, request: Request, path: str, ip: str, ip_metadata: dict[str, Any]
    ) -> None:
        """Best-effort audit record; never allowed to affect the response."""
        try:
            audit_service = getattr(request.app.state, "audit_service", None)
            if audit_service is None or not getattr(audit_service, "admin_events_enabled", False):
                return
            from services.audit import AdminAuditRecord

            await audit_service.log_admin_event(AdminAuditRecord(
                timestamp=datetime.now(),
                event_type="auth.admin_ip.denied",
                action="DENY",
                resource_type="admin_ip_rule",
                resource_id=None,
                actor_type="anonymous",
                actor_id=None,
                actor_username=None,
                method=request.method,
                path=path,
                status_code=403,
                success=False,
                ip=ip,
                ip_metadata=ip_metadata,
                user_agent=request.headers.get("user-agent"),
                error_message="IP not in admin allowlist",
                request_summary=None,
            ))
        except Exception as e:
            logger.error(f"AdminIpAllowlistMiddleware: failed to log denial: {e}")
