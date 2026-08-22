"""
Token usage and cost aggregation endpoint.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    audit_auth,
)
from utils.text_utils import mask_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


async def _label_api_key_groups(request: Request, groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Decorate `api_key`-grouped rows with a `label` field resolved from the
    `api_keys` collection's `client_name`.

    A group's `key` is now either an active key's stable document id (Phase 4
    — exact, unambiguous, matched directly by `_id`) or, for rows written
    before that column existed, the masked value (matched by masking each
    stored plaintext key the same way the audit writer masks it: show_last,
    6 chars — still subject to suffix collisions, which is exactly the
    ambiguity Phase 4 fixes going forward).

    Falls back to leaving `label` unset (the caller/frontend fall back to the
    masked `key`) when the api key service is unavailable, on lookup failure,
    or when no active key matches. Never returns or logs plaintext keys.
    """
    api_key_service = getattr(request.app.state, "api_key_service", None)
    if api_key_service is None or not groups:
        return groups

    page_size = 500
    active_keys: List[Dict[str, Any]] = []
    try:
        skip = 0
        while True:
            page = await api_key_service.database.find_many(
                api_key_service.collection_name, {"active": True}, limit=page_size, skip=skip
            )
            active_keys.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
    except Exception:
        logger.warning("Failed to resolve API key labels for cost aggregation", exc_info=True)
        return groups

    id_to_name: Dict[str, str] = {}
    masked_to_names: Dict[str, list] = {}
    for doc in active_keys:
        client_name = doc.get("client_name")
        doc_id = doc.get("_id")
        if doc_id is not None and client_name:
            # _id is unique by construction, so an id match is exact — no
            # collision handling needed here, unlike the masked-suffix path.
            id_to_name[str(doc_id)] = client_name
        plaintext = doc.get("api_key")
        if not plaintext:
            continue
        masked = mask_api_key(plaintext, show_last=True, num_chars=6)
        masked_to_names.setdefault(masked, []).append(client_name)

    for group in groups:
        key = group.get("key")
        if key in id_to_name:
            group["label"] = id_to_name[key]
            continue
        names = masked_to_names.get(key)
        if not names:
            continue
        # Ambiguity is about two distinct *keys* sharing a masked suffix, not
        # about their client_name happening to differ — two active keys with
        # the same name still collide and must not silently pick one.
        if len(names) > 1:
            group["label"] = None
            group["ambiguous"] = True
        elif names[0]:
            group["label"] = names[0]

    return groups


# -------------------------------------------------------------------------
# Observability — token usage / cost aggregation (admin panel "Costs" tab)
# -------------------------------------------------------------------------

@router.get("/observability/usage", dependencies=[audit_auth])
async def get_observability_usage(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    bucket: str = Query("day", pattern="^(hour|day)$"),
    group_by: str = Query("model", pattern="^(model|provider|adapter_name|user_id|call_type|api_key|none)$"),
    provider: Optional[str] = Query(None),
    adapter_name: Optional[str] = Query(None),
    call_type: Optional[str] = Query(None, pattern="^(chat|embedding|reranking|image|video|audio|document)$"),
    api_key: Optional[str] = Query(None),
    limit_groups: int = Query(10, ge=1, le=100),
):
    """
    Aggregate token usage and estimated cost over a time window, for the
    admin panel's Costs tab. Cost is an ESTIMATE from the local
    rate table in config/pricing.yaml, not a provider invoice.

    Grouping by `api_key` groups on the masked key recorded on each audit
    row (`...` + last 6 characters), never the key itself. Each group row
    gains a `label` (the matching active key's `client_name`) when exactly
    one active key resolves to that masked value; if two active keys share
    a masked suffix, `label` is null and `ambiguous` is set instead of
    guessing. Rows with no matching active key have no `label` field at
    all — the caller falls back to the masked `key`.

    `api_key` (the filter param) narrows the whole response — totals, series,
    and groups — to one key, identified by its masked value exactly as
    returned in a group row's `key` (e.g. `...abc123`); it composes with the
    other filters rather than replacing them.

    Reuses the audit.read permission (the same dependency that gates
    /admin/audit/events) — it already grants reading full chat
    queries/responses, which is strictly more sensitive than aggregate
    token counts, so a separate permission would only create a role that
    could never be granted meaningfully.
    """
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None or not audit_service.chat_events_enabled:
        raise HTTPException(
            status_code=503,
            detail="Chat request audit is not enabled. Set internal_services.audit.enabled: true.",
        )

    # Audit records are stored with naive local timestamps (see
    # AuditService.log_conversation's `datetime.now()`), not UTC — the
    # since/until bounds must be constructed in that same naive-local domain,
    # or the string-based range predicates used by every aggregate_usage
    # backend shift the window by the host's UTC offset. `now` (UTC-aware) is
    # kept separately for the response envelope and pricing-staleness check.
    now = datetime.now(timezone.utc)
    now_local = datetime.now()
    since_dt = now_local - timedelta(days=days)
    since = since_dt.isoformat()
    until = now_local.isoformat()

    filters: Dict[str, Any] = {}
    if provider:
        filters["provider"] = provider
    if adapter_name:
        filters["adapter_name"] = adapter_name
    if call_type:
        # Keep legacy NULL rows in the default/all view. An explicit
        filters["call_type"] = call_type
    if api_key:
        filters["api_key"] = api_key

    result = await audit_service.aggregate_usage(
        since=since,
        until=until,
        bucket=bucket,
        group_by=group_by,
        filters=filters,
        limit_groups=limit_groups,
    )

    pricing_service = getattr(request.app.state, "pricing_service", None)
    pricing_updated = getattr(pricing_service, "updated", None) if pricing_service else None
    stale = False
    if pricing_updated:
        try:
            updated_dt = datetime.fromisoformat(pricing_updated).replace(tzinfo=timezone.utc)
            stale_after_days = getattr(pricing_service, "_stale_after_days", 120)
            stale = (now - updated_dt).days > stale_after_days
        except ValueError:
            pass

    groups = result.get("groups", [])
    if group_by == "api_key":
        groups = await _label_api_key_groups(request, groups)

    return {
        "window": {"since": since, "until": until, "bucket": bucket, "days": days},
        "totals": result.get("totals", {}),
        "series": result.get("series", []),
        "groups": groups,
        "pricing": {"updated": pricing_updated, "stale": stale},
    }
