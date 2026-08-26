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
- A handler may publish canonical values via `request.state.audit_context`
  when the raw request differs from what was persisted. Handler-supplied data
  is always scoped by the route's own declaration — summary fields through the
  per-route allowlist, and the resource id only on routes declaring the
  "context" source. The redaction contract belongs to the route, so a handler
  can neither write a field its route excludes nor displace a resource id the
  route derives from the request.
- Path templates are matched via precompiled regexes; the actor is pulled
  from `request.state.current_user` (set by auth dependencies) or from the
  `X-API-Key` header if API-key auth succeeded.
- All audit errors are swallowed — a failing audit write must never break
  the underlying admin action.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from utils.ip_utils import extract_ip as _extract_ip
from utils.ip_utils import parse_trusted_networks as _parse_trusted_networks
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
#   - "context" — the handler supplies it via request.state.audit_context, for
#       ids that only exist after the write (e.g. a freshly inserted row). This
#       is opt-in per route precisely because it trusts handler-supplied data
#       into long-lived audit storage: a route with a request-derived source
#       above keeps it, and context is ignored there.
#   - None — no resource id
#
# allowed_body_fields: iterable of top-level keys to copy from the JSON body
#   into request_summary. Set to an empty list to record nothing; set to
#   sentinel `_CHANGED_KEYS` to record just the list of top-level keys.

_CHANGED_KEYS = object()

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

    # ---- User blacklist ----
    # The pattern is the whole point of the event — an auditor needs to know
    # *who* was blocked, not just that a rule changed. It's operator-authored
    # matching syntax (an email/username/id glob), not a credential, so it is
    # safe to record.
    #
    # Create can't derive a resource id from the request: the rule id doesn't
    # exist until the insert, and the submitted pattern is not canonical (the
    # service trims and lowercases it before storing). So it opts into the
    # "context" source, and the handler publishes the real rule id once written
    # — keying a successful create the same way as update and delete. A *failed*
    # create publishes nothing, so it has no resource id (nothing was created)
    # while its request_summary still shows what was attempted.
    ("POST",   "/auth/blacklist",                     "auth.blacklist.create",   "CREATE", "blacklist_rule", "context",       ("pattern", "entry_type", "reason")),
    ("PUT",    "/auth/blacklist/{rule_id}",           "auth.blacklist.update",   "UPDATE", "blacklist_rule", "path:rule_id",  ("pattern", "entry_type", "reason")),
    ("DELETE", "/auth/blacklist/{rule_id}",           "auth.blacklist.delete",   "DELETE", "blacklist_rule", "path:rule_id",  ()),

    # ---- Identity allowlist (pre-clearing external logins) ----
    # Same reasoning as the blacklist: the pattern *is* the event, since it says
    # who was granted access rather than merely that a rule moved. Recording it
    # is what lets an auditor answer "who approved this identity, and when".
    #
    # A deletion here is the security-relevant direction (it withdraws access),
    # which is the reverse of the blacklist, so it is audited identically.
    ("POST",   "/auth/allowlist",                     "auth.allowlist.create",   "CREATE", "allowlist_rule", "context",       ("pattern", "entry_type", "reason")),
    ("PUT",    "/auth/allowlist/{rule_id}",           "auth.allowlist.update",   "UPDATE", "allowlist_rule", "path:rule_id",  ("pattern", "entry_type", "reason")),
    ("DELETE", "/auth/allowlist/{rule_id}",           "auth.allowlist.delete",   "DELETE", "allowlist_rule", "path:rule_id",  ()),

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
    ("POST",   "/admin/adapters",                                   "admin.adapter.create",             "CREATE",  "adapter", None,                ("spec",)),
    # `force` is a query param, so the body allowlist cannot capture it — the event
    # records which adapter was deleted, not whether the referrer check was waived.
    ("DELETE", "/admin/adapters/{adapter_name}",                    "admin.adapter.delete",             "DELETE",  "adapter", "path:adapter_name", ()),

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
# Body handling
# ---------------------------------------------------------------------------

async def _read_and_replay_body(request: Request) -> bytes:
    """
    Read the request body for audit capture.  Starlette caches the body in
    request._body after the first read, so the downstream handler can still
    consume it via request.body() / request.json().

    Skips reading entirely when Content-Length signals an oversized payload,
    avoiding unnecessary memory allocation.
    """
    content_length = int(request.headers.get("content-length", 0) or 0)
    if content_length > _MAX_BODY_BYTES:
        return b""

    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return b""

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


def _apply_summary_overrides(
    summary: Optional[Dict[str, Any]],
    overrides: Any,
    allowed: Any,
) -> Optional[Dict[str, Any]]:
    """Merge handler-published values into the summary, allowlist-bound.

    Overrides go through the SAME per-route allowlist as the request body. The
    redaction contract is a property of the route, not of who supplies the
    value: a handler must not be able to publish a field the route deliberately
    excludes, or the hook becomes a way to write secrets into the ledger.

    Routes recording nothing (empty allowlist) or only changed-key names
    (`_CHANGED_KEYS`) accept no overrides at all. An override of None removes
    the field, letting a handler correct the ledger when the stored value ended
    up empty.
    """
    if not isinstance(overrides, dict) or not overrides:
        return summary
    # `_CHANGED_KEYS` summaries are derived key names, not field values, and an
    # empty allowlist means "record nothing" - neither takes overrides.
    if allowed is _CHANGED_KEYS or not allowed:
        return summary

    merged = dict(summary or {})
    for field in allowed:
        if field not in overrides:
            continue
        value = overrides[field]
        if value is None:
            merged.pop(field, None)
        else:
            merged[field] = value
    return merged or None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AdminAuditMiddleware(BaseHTTPMiddleware):
    """Captures admin/auth mutations and routes them to AuditService."""

    def __init__(self, app, config: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        security_cfg = (config or {}).get("security", {}) or {}
        rate_cfg = security_cfg.get("rate_limiting", {}) or {}
        self._trust_proxy = rate_cfg.get("trust_proxy_headers", False)
        self._trusted_networks = _parse_trusted_networks(
            rate_cfg.get("trusted_proxies", [])
        )

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

        # A handler may publish canonical audit values on request.state (shared
        # via the ASGI scope, same as request.state.current_user above) when the
        # raw request differs from what was persisted. Everything taken from
        # here is scoped by the route's own declaration: the summary through the
        # field allowlist, the resource id only where the route opted in with
        # the "context" source. Handler-supplied data must never be able to
        # displace a request-derived id or widen what the ledger stores.
        audit_context = getattr(request.state, "audit_context", None)
        if not isinstance(audit_context, dict):
            audit_context = {}

        # Resolve resource id
        resource_id: Optional[str] = None
        if resource_id_source:
            if resource_id_source.startswith("path:"):
                resource_id = path_params.get(resource_id_source.split(":", 1)[1])
            elif resource_id_source.startswith("body:") and body_json:
                resource_id = body_json.get(resource_id_source.split(":", 1)[1])
            elif resource_id_source == "actor":
                resource_id = actor_id
            elif resource_id_source == "context":
                resource_id = audit_context.get("resource_id")

        request_summary = _apply_summary_overrides(
            _build_request_summary(body_json, allowed),
            audit_context.get("summary"),
            allowed,
        )

        # IP + metadata
        ip, ip_metadata = _extract_ip(
            request,
            trust_proxy=self._trust_proxy,
            trusted_networks=self._trusted_networks,
        )

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
            request_summary=request_summary,
        )

        await audit_service.log_admin_event(record)
