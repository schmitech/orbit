"""
In-memory store for intent-template queries that failed to match (or matched
below threshold), plus human feedback on matches.

Every `no_matching_template` / below-threshold rejection previously only hit
a logger.warning and was lost. This module gives the admin UI something to
list and act on, and gives Phase 1A's eval corpus a way to grow from real
production misses via the feedback endpoint's `expected_template_id`.

Bounded, process-local, not persisted across restarts — deliberately simple;
promoting this to a durable store (e.g. the audit DB) is future work if the
in-memory window proves too small in practice.
"""

import time
from collections import deque
from threading import Lock
from typing import Any, Optional

_MAX_ENTRIES = 500

_misses: deque = deque(maxlen=_MAX_ENTRIES)
_feedback: deque = deque(maxlen=_MAX_ENTRIES)
_lock = Lock()
_next_id = 1


def record_miss(
    adapter: str,
    query: str,
    reason: str,
    candidates: list[dict[str, Any]],
    threshold: float,
) -> str:
    """Record an unmatched or below-threshold query. Returns the miss id."""
    global _next_id
    with _lock:
        miss_id = str(_next_id)
        _next_id += 1
        _misses.appendleft({
            "id": miss_id,
            "adapter": adapter,
            "query": query,
            "reason": reason,
            "candidates": candidates,
            "threshold": threshold,
            "timestamp": time.time(),
        })
    return miss_id


def list_misses(adapter: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        items = list(_misses)
    if adapter:
        items = [m for m in items if m["adapter"] == adapter]
    return items[:limit]


def record_feedback(
    adapter: str,
    verdict: str,
    request_id: Optional[str] = None,
    template_id: Optional[str] = None,
    expected_template_id: Optional[str] = None,
) -> None:
    with _lock:
        _feedback.appendleft({
            "adapter": adapter,
            "verdict": verdict,
            "request_id": request_id,
            "template_id": template_id,
            "expected_template_id": expected_template_id,
            "timestamp": time.time(),
        })


def list_feedback(adapter: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    with _lock:
        items = list(_feedback)
    if adapter:
        items = [f for f in items if f["adapter"] == adapter]
    return items[:limit]
