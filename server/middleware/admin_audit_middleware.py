"""
Admin & Auth Audit Middleware
=============================

Captures mutations to `/admin/*` and `/auth/*` endpoints and routes them to
the AuditService's admin-event storage. Read-only GETs are ignored.

Design:
- Only POST/PUT/PATCH/DELETE to `/admin/*` and `/auth/*` are audited.
- The request body is read once, JSON-parsed, and (a) replayed so the
  downstream handler can still read it, (b) scrubbed against a per-route
  allowlist so secrets (passwords, raw API keys, prompt bodies, config
  values) are never stored.
- Path templates are matched via precompiled regexes; the actor is pulled
  from `request.state.current_user` (set by auth dependencies) or from the
  `X-API-Key` header if API-key auth succeeded.
- All audit errors are swallowed — a failing audit write must never break
  the underlying admin action.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from utils.text_utils import mask_api_key

logger = logging.getLogger(__name__)


_MAX_BODY_BYTES = 64 * 1024  # cap to protect memory
_AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUDITED_PREFIXES = ("/admin/", "/auth/")

# Routes under the audited prefixes that are NOT mutations — pure utilities
# with no state change and no audit value. Skip them entirely rather than
# record them as `admin.unknown`.
_SKIP_PATHS = frozenset({
    "/admin/render-markdown",  # markdown preview; no state, no secrets
})


# ---------------------------------------------------------------------------
# Route map
# ---------------------------------------------------------------------------

# Each entry: (method, path_template, event_type, action, resource_type,
#              resource_id_source, allowed_body_fields)
#
# resource_id_source:
#   - "path:<name>" — pull from path_params[<name>]
#   - "body:<field>" — pull from parsed request body
#   - "actor" — use the actor's id
#   - None — no resource id
#
# allowed_body_fields: iterable of top-level keys to copy from the JSON body
#   into request_summary. Set to an empty list to record nothing; set to
#   sentinel `_CHANGED_KEYS` to record just the list of top-level keys.

_CHANGED_KEYS = "__changed_keys__"

_ROUTE_MAP: List[Tuple[str, str, str, str, str, Optional[str], Any]] = [
    # ---- Auth ----
    ("POST",   "/auth/login",                         "auth.login",              "LOGIN",  "session", None,               ("username",)),
    ("POST",   "/auth/logout",                        "auth.logout",             "LOGOUT", "session", None,               ()),

    # Dashboard cookie-based login/logout (from admin_panel_routes.py) — distinct
    # from the bearer-token /auth/login above. Both paths matter for an audit trail.
    ("POST",   "/admin/login",                        "auth.dashboard.login",    "LOGIN",  "session", None,               ("username",)),
    ("POST",   "/admin/logout",                       "auth.dashboard.logout",   "LOGOUT", "session", None,               ()),
    ("POST",   "/auth/register",                      "auth.user.create",        "CREATE", "user",    "body:username",    ("username", "role")),
    ("DELETE", "/auth/users/{user_id}",               "auth.user.delete",        "DELETE", "user",    "path:user_id",     ()),
    ("POST",   "/auth/users/{user_id}/deactivate",    "auth.user.deactivate",    "UPDATE", "user",    "path:user_id",     ()),
    ("POST",   "/auth/users/{user_id}/activate",      "auth.user.activate",      "UPDATE", "user",    "path:user_id",     ()),
    ("POST",   "/auth/change-password",               "auth.password.change",    "UPDATE", "user",    "actor",            ()),
    ("POST",   "/auth/reset-password",                "auth.password.reset",     "UPDATE", "user",    "body:user_id",     ("user_id",)),

    # ---- API keys ----
    ("POST",   "/admin/api-keys",                                   "admin.api_key.create",     "CREATE", "api_key", None,                  ("client_name", "adapter_name", "system_prompt_id", "notes")),
    ("PUT",    "/admin/api-keys/{api_key_id}",                      "admin.api_key.update",     "UPDATE", "api_key", "path:api_key_id",     ("client_name", "adapter_name", "notes")),
    ("PATCH",  "/admin/api-keys/{api_key_id}/rename",               "admin.api_key.rename",     "UPDATE", "api_key", "path:api_key_id",     ("new_name",)),
    ("POST",   "/admin/api-keys/{api_key_id}/deactivate",           "admin.api_key.deactivate", "UPDATE", "api_key", "path:api_key_id",     ()),
    ("DELETE", "/admin/api-keys/{api_key_id}",                      "admin.api_key.delete",     "DELETE", "api_key", "path:api_key_id",     ()),
    ("POST",   "/admin/api-keys/{api_key_id}/prompt",               "admin.api_key.attach_prompt", "UPDATE", "api_key", "path:api_key_id",  ("prompt_id",)),

    # ---- Quotas ----
    ("PUT",    "/admin/api-keys/{api_key_id}/quota",                "admin.quota.update",       "UPDATE", "api_key", "path:api_key_id",     ("daily_limit", "monthly_limit", "throttle_enabled")),
    ("POST",   "/admin/api-keys/{api_key_id}/quota/reset",          "admin.quota.reset",        "UPDATE", "api_key", "path:api_key_id",     ()),

    # ---- Prompts ----
    ("POST",   "/admin/prompts",                                    "admin.prompt.create",      "CREATE", "prompt",  None,                  ("name", "version")),
    ("PUT",    "/admin/prompts/{prompt_id}",                        "admin.prompt.update",      "UPDATE", "prompt",  "path:prompt_id",      ("name", "version")),
    ("DELETE", "/admin/prompts/{prompt_id}",                        "admin.prompt.delete",      "DELETE", "prompt",  "path:prompt_id",      ()),

    # ---- Adapter config ----
    ("PUT",    "/admin/adapters/config/entry/{adapter_name}",       "admin.adapter.config_update",      "UPDATE",  "adapter", "path:adapter_name", _CHANGED_KEYS),
    ("PATCH",  "/admin/adapters/config/entry/{adapter_name}/toggle","admin.adapter.toggle",             "UPDATE",  "adapter", "path:adapter_name", ("enabled",)),
    ("PUT",    "/admin/adapters/config/{filename}",                 "admin.adapter.config_file_update", "UPDATE",  "config",  "path:filename",     _CHANGED_KEYS),

    # ---- Control operations ----
    ("POST",   "/admin/reload-adapters",                            "admin.adapter.reload",     "CONTROL", "adapter",  None,                  ()),
    ("POST",   "/admin/reload-adapters/async",                      "admin.adapter.reload",     "CONTROL", "adapter",  None,                  ()),
    ("POST",   "/admin/reload-templates",                           "admin.template.reload",    "CONTROL", "template", None,                  ()),
    ("POST",   "/admin/reload-templates/async",                     "admin.template.reload",    "CONTROL", "template", None,                  ()),
    ("POST",   "/admin/adapters/{adapter_name}/test-query",         "admin.adapter.test_query", "CONTROL", "adapter",  "path:adapter_name",   ()),

    # ---- Chat history / conversations ----
    ("DELETE", "/admin/chat-history/{session_id}",                  "admin.chat_history.clear",    "DELETE", "session", "path:session_id",  ()),
    ("DELETE", "/admin/conversations/{session_id}",                 "admin.conversation.delete",   "DELETE", "session", "path:session_id",  ()),

    # ---- System ----
    ("PUT",    "/admin/config",                                     "admin.config.update",      "UPDATE",  "config", None, _CHANGED_KEYS),
    ("POST",   "/admin/shutdown",                                   "admin.server.shutdown",    "CONTROL", "server", None, ()),
    ("POST",   "/admin/restart",                                    "admin.server.restart",     "CONTROL", "server", None, ()),
]


def _template_to_regex(template: str) -> re.Pattern:
    """Convert `/admin/foo/{bar}/baz` to `^/admin/foo/(?P<bar>[^/]+)/baz$`."""
    pattern = re.sub(r"\{([^/}]+)\}", r"(?P<\1>[^/]+)", template)
    return re.compile(f"^{pattern}$")


_COMPILED_ROUTES: List[Tuple[str, re.Pattern, str, str, str, Optional[str], Any, str]] = [
    (method, _template_to_regex(template), event_type, action, resource_type, resource_id_source, allowed, template)
    for (method, template, event_type, action, resource_type, resource_id_source, allowed) in _ROUTE_MAP
]


def _match_route(method: str, path: str):
    """Return the route tuple matching method+path, or None."""
    for entry in _COMPILED_ROUTES:
        ent_method, regex, *_rest = entry
        if ent_method != method:
            continue
        match = regex.match(path)
        if match:
            return entry, match.groupdict()
    return None


# ---------------------------------------------------------------------------
# IP parsing (mirror of LoggerService / AuditService logic)
# ---------------------------------------------------------------------------

def _is_local_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def _extract_ip(request: Request) -> Tuple[str, Dict[str, Any]]:
    """Return (ip_address, ip_metadata) for the request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        raw = forwarded
        clean = forwarded.split(",")[0].strip()
        source = "proxy"
    else:
        clean = request.client.host if request.client else "unknown"
        raw = clean
        source = "direct"

    if not clean or clean == "unknown":
        return "unknown", {
            "address": "unknown",
            "type": "unknown",
            "isLocal": False,
            "source": "unknown",
            "originalValue": raw,
        }

    if clean in ("::1", "::ffff:127.0.0.1", "127.0.0.1") or clean.startswith("::ffff:127."):
        return "localhost", {
            "address": "localhost",
            "type": "local",
            "isLocal": True,
            "source": "direct",
            "originalValue": clean,
        }

    if clean.startswith("::ffff:"):
        clean = clean[7:]
        ip_type = "ipv4"
    elif ":" in clean:
        ip_type = "ipv6"
    else:
        ip_type = "ipv4"

    return clean, {
        "address": clean,
        "type": ip_type,
        "isLocal": _is_local_ip(clean),
        "source": source,
        "originalValue": raw,
    }


# ---------------------------------------------------------------------------
# Body handling
# ---------------------------------------------------------------------------

async def _read_and_replay_body(request: Request) -> bytes:
    """
    Read the request body into memory and patch `_receive` so the downstream
    handler can still consume it. Capped at `_MAX_BODY_BYTES` — oversized
    bodies are passed through without capture.
    """
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        body = b""  # don't buffer huge bodies; handler still has original stream

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive
    return body


def _parse_json_body(body_bytes: bytes, content_type: Optional[str]) -> Optional[Dict[str, Any]]:
    if not body_bytes:
        return None
    if not content_type or "application/json" not in content_type.lower():
        return None
    try:
        parsed = json.loads(body_bytes)
        return parsed if isinstance(parsed, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _build_request_summary(body: Optional[Dict[str, Any]], allowed: Any) -> Optional[Dict[str, Any]]:
    """Apply the per-route allowlist; secrets (passwords, raw keys) never pass through."""
    if not body:
        return None
    if allowed is _CHANGED_KEYS:
        return {"changed_keys": list(body.keys())}
    if not allowed:
        return None
    summary: Dict[str, Any] = {}
    for field in allowed:
        if field in body and body[field] is not None:
            summary[field] = body[field]
    return summary or None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AdminAuditMiddleware(BaseHTTPMiddleware):
    """Captures admin/auth mutations and routes them to AuditService."""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        method = request.method

        # Fast-path: skip everything non-auditable.
        if method not in _AUDITED_METHODS or not path.startswith(_AUDITED_PREFIXES):
            return await call_next(request)
        if path in _SKIP_PATHS:
            return await call_next(request)

        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service is None or not getattr(audit_service, "admin_events_enabled", False):
            return await call_next(request)

        # Read body (once) so we can both scrub it for the audit summary AND
        # let the downstream handler read it.
        try:
            body_bytes = await _read_and_replay_body(request)
        except Exception as e:
            logger.debug(f"AdminAuditMiddleware: failed to read body: {e}")
            body_bytes = b""

        body_json = _parse_json_body(body_bytes, request.headers.get("content-type"))

        # Let the handler run.
        response = await call_next(request)

        # Emit audit event (never raise from here).
        try:
            await self._emit_event(request, response, path, method, body_json, audit_service)
        except Exception as e:
            logger.error(f"AdminAuditMiddleware: error emitting event: {e}")

        return response

    async def _emit_event(
        self,
        request: Request,
        response,
        path: str,
        method: str,
        body_json: Optional[Dict[str, Any]],
        audit_service,
    ) -> None:
        from services.audit import AdminAuditRecord  # local import avoids cycles

        match = _match_route(method, path)
        if match is None:
            route_entry = None
            event_type = "admin.unknown"
            action = method
            resource_type = "unknown"
            resource_id_source: Optional[str] = None
            allowed: Any = ()
            path_params: Dict[str, str] = {}
        else:
            entry, path_params = match
            _method, _regex, event_type, action, resource_type, resource_id_source, allowed, _template = entry

        # Resolve actor
        actor_type = "anonymous"
        actor_id: Optional[str] = None
        actor_username: Optional[str] = None

        current_user = getattr(request.state, "current_user", None)
        if current_user:
            actor_type = "user"
            actor_id = str(current_user.get("id") or current_user.get("_id") or "") or None
            actor_username = current_user.get("username")
        else:
            raw_api_key = getattr(request.state, "api_key", None) or request.headers.get("x-api-key")
            if raw_api_key:
                actor_type = "api_key"
                actor_id = mask_api_key(raw_api_key, show_last=True, num_chars=6)

        # Resolve resource id
        resource_id: Optional[str] = None
        if resource_id_source:
            if resource_id_source.startswith("path:"):
                resource_id = path_params.get(resource_id_source.split(":", 1)[1])
            elif resource_id_source.startswith("body:") and body_json:
                resource_id = body_json.get(resource_id_source.split(":", 1)[1])
            elif resource_id_source == "actor":
                resource_id = actor_id

        # IP + metadata
        ip, ip_metadata = _extract_ip(request)

        status_code = response.status_code
        success = status_code < 400
        error_message = None
        if not success:
            # For failed requests, leave a short marker. Response bodies are
            # not captured (they may contain sensitive info).
            error_message = f"HTTP {status_code}"

        record = AdminAuditRecord(
            timestamp=datetime.now(),
            event_type=event_type,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_username=actor_username,
            method=method,
            path=path,
            status_code=status_code,
            success=success,
            ip=ip,
            ip_metadata=ip_metadata,
            user_agent=request.headers.get("user-agent"),
            error_message=error_message,
            request_summary=_build_request_summary(body_json, allowed),
        )

        await audit_service.log_admin_event(record)
