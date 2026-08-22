"""
Admin and auth audit event query endpoint.
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    audit_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# -------------------------------------------------------------------------
# Admin / Auth Audit Events
# -------------------------------------------------------------------------

@router.get("/audit/events", dependencies=[audit_auth])
async def list_admin_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    source: str = Query("all", pattern="^(all|admin|chat)$"),
    event_type: Optional[str] = Query(None),
    event_prefix: Optional[str] = Query(None, description="Match event_type that starts with this prefix (e.g. 'auth.', 'admin.api_key.')"),
    actor_id: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    resource_type: Optional[str] = Query(None),
    call_type: Optional[str] = Query(None, description="Filter chat rows by AI call kind: chat, embedding, reranking, image, video, audio, document"),
    q: Optional[str] = Query(None, description="Free-text search across actor_username, path, resource_id, ip"),
    since: Optional[str] = Query(None, description="ISO timestamp (inclusive lower bound)"),
    until: Optional[str] = Query(None, description="ISO timestamp (exclusive upper bound)"),
):
    """
    List audit ledger entries, most recent first.

    The ledger can merge two sources:
      - admin/auth audit events
      - chat request audit records

    We oversample each requested source, normalize the row shape, sort by
    timestamp descending, apply the remaining filters, then slice the page.
    """
    def _normalize_admin(row: dict) -> dict:
        return {
            **row,
            "audit_source": "admin",
            "audit_kind": "admin_event",
            "title": row.get("event_type") or "admin.event",
            "subtitle": row.get("action") or "",
            "search_text": " ".join(
                str(row.get(field, "") or "")
                for field in (
                    "event_type",
                    "action",
                    "actor_username",
                    "actor_id",
                    "path",
                    "resource_id",
                    "resource_type",
                    "ip",
                )
            ).lower(),
        }

    def _normalize_chat(row: dict) -> dict:
        api_key = row.get("api_key") or {}
        masked_key = api_key.get("key") if isinstance(api_key, dict) else None

        actor_type = "anonymous"
        actor_id_value = None
        if row.get("user_id"):
            actor_type = "user"
            actor_id_value = row.get("user_id")
        elif masked_key:
            actor_type = "api_key"
            actor_id_value = masked_key

        provider = row.get("provider") or "chat"
        model = row.get("model")
        adapter_name = row.get("adapter_name")
        session_id = row.get("session_id")
        query_text = str(row.get("query") or "")
        response_text = str(row.get("response") or "")

        return {
            **row,
            "audit_source": "chat",
            "audit_kind": "chat_request",
            "call_type": row.get("call_type") or "chat",
            "event_type": "chat.request",
            "action": "BLOCK" if row.get("blocked") else "CHAT",
            "resource_type": "chat",
            "resource_id": adapter_name or provider,
            "actor_type": actor_type,
            "actor_id": actor_id_value,
            "actor_username": None,
            "method": row.get("method") or "CHAT",
            "path": row.get("path") or provider,
            "status_code": None,
            "success": not bool(row.get("blocked")),
            "request_summary": {
                "provider": provider,
                "model": model,
                "adapter_name": adapter_name,
                "session_id": session_id,
                "user_id": row.get("user_id"),
                "api_key": masked_key,
                "blocked": bool(row.get("blocked")),
                "response_compressed": bool(row.get("response_compressed")),
                "prompt_tokens": row.get("prompt_tokens"),
                "completion_tokens": row.get("completion_tokens"),
                "total_tokens": row.get("total_tokens"),
                "reasoning_tokens": row.get("reasoning_tokens"),
                "cost_usd": row.get("cost_usd"),
                "input_rate_per_1m": row.get("input_rate_per_1m"),
                "output_rate_per_1m": row.get("output_rate_per_1m"),
                "pricing_source": row.get("pricing_source"),
                "usage_unit": row.get("usage_unit"),
                "usage_quantity": row.get("usage_quantity"),
                "call_type": row.get("call_type") or "chat",
            },
            "title": model or provider,
            "subtitle": adapter_name or "chat request",
            "search_text": " ".join(
                value
                for value in (
                    provider,
                    model,
                    adapter_name,
                    session_id,
                    row.get("user_id"),
                    masked_key,
                    row.get("ip"),
                    query_text,
                    response_text,
                )
                if value
            ).lower(),
        }

    audit_service = getattr(request.app.state, "audit_service", None)
    admin_enabled = bool(audit_service and audit_service.admin_events_enabled)
    chat_enabled = bool(audit_service and audit_service.chat_events_enabled)

    if audit_service is None or (not admin_enabled and not chat_enabled):
        raise HTTPException(
            status_code=503,
            detail=(
                "Audit ledger is not enabled. Enable either "
                "internal_services.audit.enabled for chat requests or "
                "internal_services.audit.admin_events.enabled for admin events."
            ),
        )
    if source == "admin" and not admin_enabled:
        raise HTTPException(
            status_code=503,
            detail="Admin audit is not enabled. Set internal_services.audit.admin_events.enabled: true.",
        )
    if source == "chat" and not chat_enabled:
        raise HTTPException(
            status_code=503,
            detail="Chat request audit is not enabled. Set internal_services.audit.enabled: true.",
        )

    native_admin_filters: dict = {}
    if event_type is not None:
        native_admin_filters["event_type"] = event_type
    if actor_id is not None:
        native_admin_filters["actor_id"] = actor_id
    if success is not None:
        native_admin_filters["success"] = success
    if resource_type is not None:
        native_admin_filters["resource_type"] = resource_type

    native_chat_filters: dict = {}
    if success is not None:
        native_chat_filters["blocked"] = not success
    if call_type is not None:
        native_chat_filters["call_type"] = call_type

    # Always oversample rather than fetching exactly the requested page: the
    # response's "total" is len(filtered) over whatever was fetched, so a plain
    # per-page fetch (previously skipped here whenever source == "admin" and no
    # other filter was active) made "total" collapse to the current page size —
    # reporting no further pages even when older admin events existed.
    fetch_limit = min(offset + (limit * 10), 5000)

    rows: List[dict] = []
    try:
        if source in ("all", "admin") and admin_enabled:
            admin_rows = await audit_service.query_admin_events(
                filters=native_admin_filters,
                limit=fetch_limit,
                offset=0,
                sort_by="timestamp",
                sort_order=-1,
            )
            rows.extend(_normalize_admin(row) for row in admin_rows)

        if source in ("all", "chat") and chat_enabled:
            chat_rows = await audit_service.query_audit_logs(
                filters=native_chat_filters,
                limit=fetch_limit,
                offset=0,
                sort_by="timestamp",
                sort_order=-1,
            )
            rows.extend(_normalize_chat(row) for row in chat_rows)
    except Exception as exc:
        logger.error(f"Failed to query audit events: {exc}")
        raise HTTPException(status_code=500, detail="Failed to query audit events")

    rows.sort(key=lambda row: str(row.get("timestamp", "")), reverse=True)

    q_lower = q.lower() if q else None
    prefix = event_prefix
    since_val = since
    until_val = until

    def keep(row: dict) -> bool:
        if source != "all" and row.get("audit_source") != source:
            return False
        if event_type and row.get("audit_source") != "admin":
            return False
        if prefix:
            if row.get("audit_source") != "admin":
                return False
            if not str(row.get("event_type", "")).startswith(prefix):
                return False
        if actor_id and str(row.get("actor_id") or "") != actor_id:
            return False
        if resource_type:
            if row.get("audit_source") != "admin":
                return False
            if str(row.get("resource_type") or "") != resource_type:
                return False
        if success is not None and bool(row.get("success")) != success:
            return False
        if call_type:
            if row.get("audit_source") != "chat":
                return False
            if (row.get("call_type") or "chat") != call_type:
                return False
        if since_val and str(row.get("timestamp", "")) < since_val:
            return False
        if until_val and str(row.get("timestamp", "")) >= until_val:
            return False
        if q_lower and q_lower not in str(row.get("search_text", "")):
            return False
        return True

    filtered = [row for row in rows if keep(row)]
    total_after_filter = len(filtered)
    page = filtered[offset : offset + limit]

    for row in page:
        row.pop("search_text", None)

    return {
        "events": page,
        "limit": limit,
        "offset": offset,
        "returned": len(page),
        "total": total_after_filter,
        "sources": {
            "admin": admin_enabled,
            "chat": chat_enabled,
        },
    }
