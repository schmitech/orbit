"""
Token usage and cost aggregation endpoint.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    audit_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _label_api_key_groups(request: Request, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Decorate `api_key`-grouped rows with a `label` field resolved from the
    `api_keys` collection's `client_name`.

    A group's `key` is either an active key's stable document id (exact,
    unambiguous, matched directly by `_id`) or its masked `key_suffix` value
    (still subject to suffix collisions across different keys).

    Falls back to leaving `label` unset (the caller/frontend fall back to the
    masked `key`) when the api key service is unavailable, on lookup failure,
    or when no active key matches. Never returns or logs plaintext keys.
    """
    api_key_service = getattr(request.app.state, "api_key_service", None)
    if api_key_service is None or not groups:
        return groups

    # A group's `key` is either an exact `_id` or a masked `...<suffix>` value —
    # narrow the lookup to just the ones actually present instead of scanning
    # the whole active-keys collection.
    keys_present = {group.get("key") for group in groups if group.get("key")}
    id_candidates = [k for k in keys_present if not k.startswith("...")]
    suffix_candidates = [k[3:] for k in keys_present if k.startswith("...")]
    if not id_candidates and not suffix_candidates:
        return groups

    # Two separate `_id`/`key_suffix` queries rather than one `$or` of both —
    # MongoDBService._convert_string_ids_to_objectid only converts `_id`
    # string candidates to ObjectId when `_id` is a top-level query key, not
    # when it's nested inside an `$or` list, so wrapping both in one `$or`
    # would silently fail to match any id-keyed group on MongoDB. Each query
    # is paginated in full (not just find_many's default first page) since a
    # suffix can match more active keys than there are suffix candidates.
    async def _find_all(query: dict[str, Any]) -> list[dict[str, Any]]:
        page_size = 500
        docs: list[dict[str, Any]] = []
        skip = 0
        while True:
            page = await api_key_service.database.find_many(
                api_key_service.collection_name, query, limit=page_size, skip=skip
            )
            docs.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        return docs

    try:
        matched_by_id: dict[str, dict[str, Any]] = {}
        if id_candidates:
            for doc in await _find_all({"active": True, "_id": {"$in": id_candidates}}):
                matched_by_id[str(doc.get("_id"))] = doc
        if suffix_candidates:
            for doc in await _find_all({"active": True, "key_suffix": {"$in": suffix_candidates}}):
                # A key matching both an id and a suffix candidate (same
                # document) must be counted once, or the suffix group would
                # see a spurious second "match" and be flagged ambiguous.
                matched_by_id[str(doc.get("_id"))] = doc
    except Exception:
        logger.warning("Failed to resolve API key labels for cost aggregation", exc_info=True)
        return groups

    id_to_name: dict[str, str] = {}
    masked_to_names: dict[str, list] = {}
    for doc in matched_by_id.values():
        client_name = doc.get("client_name")
        doc_id = doc.get("_id")
        if doc_id is not None and client_name:
            # _id is unique by construction, so an id match is exact — no
            # collision handling needed here, unlike the masked-suffix path.
            id_to_name[str(doc_id)] = client_name
        suffix = doc.get("key_suffix")
        if not suffix:
            continue
        masked = f"...{suffix}"
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
    call_type: Optional[str] = Query(None, pattern="^(chat|decision|moderation|embedding|reranking|image|video|audio|document)$"),
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

    filters: dict[str, Any] = {}
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
