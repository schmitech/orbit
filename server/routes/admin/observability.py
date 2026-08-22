"""
Token usage and cost aggregation endpoint.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, HTTPException, Query

from routes.admin._shared import (
    audit_auth,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    call_type: Optional[str] = Query(None, pattern="^(inference|embedding|reranking|image|video|audio|document)$"),
    limit_groups: int = Query(10, ge=1, le=100),
):
    """
    Aggregate token usage and estimated cost over a time window, for the
    admin panel's Costs tab. Cost is an ESTIMATE from the local
    rate table in config/pricing.yaml, not a provider invoice.

    Grouping by `api_key` groups on the masked key recorded on each audit
    row (`...` + last 6 characters), never the key itself.

    Reuses the audit.read permission (the same dependency that gates
    /admin/audit/events) — it already grants reading full inference
    queries/responses, which is strictly more sensitive than aggregate
    token counts, so a separate permission would only create a role that
    could never be granted meaningfully.
    """
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None or not audit_service.inference_events_enabled:
        raise HTTPException(
            status_code=503,
            detail="Inference request audit is not enabled. Set internal_services.audit.enabled: true.",
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
        # inference filter intentionally follows the audit-events endpoint's
        # semantics, where NULL is interpreted as inference by the backend.
        filters["call_type"] = call_type

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

    return {
        "window": {"since": since, "until": until, "bucket": bucket, "days": days},
        "totals": result.get("totals", {}),
        "series": result.get("series", []),
        "groups": result.get("groups", []),
        "pricing": {"updated": pricing_updated, "stale": stale},
    }
