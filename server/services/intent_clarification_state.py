"""In-memory pending-clarification store backing the intent clarification
flow (Phase 5 of docs/roadmap/intent-template-retrieval.md).

When a retriever asks a disambiguation or slot-fill question, it stashes
what it needs to resume — the pinned template (and/or partially-extracted
parameters) — keyed by (adapter, session_id). The next turn on that session
pops the pending entry and resumes against the pinned template instead of
re-matching from scratch.

Process-local, best-effort, and short-lived (TTL-bounded): a restart, a
different worker in a load-balanced deployment, or simply waiting too long
between turns loses the pending state, and the retriever just falls back to
matching the new message from scratch. That's an acceptable failure mode for
a conversational nudge — mirrors services/template_misses.py rather than
introducing a durable store for it.
"""

import time
from typing import Any, Dict, Optional, Tuple

_MAX_ENTRIES = 1000
_DEFAULT_TTL_SECONDS = 300.0

_pending: Dict[Tuple[str, str], Dict[str, Any]] = {}


def store_pending(adapter: str, session_id: str, payload: Dict[str, Any], ttl: float = _DEFAULT_TTL_SECONDS) -> None:
    """Stash a pending clarification for this adapter/session, replacing any prior one."""
    if not session_id:
        return
    _pending[(adapter, session_id)] = {"payload": payload, "expires_at": time.time() + ttl}
    while len(_pending) > _MAX_ENTRIES:
        _pending.pop(next(iter(_pending)))


def pop_pending(adapter: str, session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve and clear the pending clarification for this adapter/session, if any and unexpired."""
    if not session_id:
        return None
    entry = _pending.pop((adapter, session_id), None)
    if entry is None or entry["expires_at"] < time.time():
        return None
    return entry["payload"]


def clear_pending(adapter: str, session_id: str) -> None:
    if not session_id:
        return
    _pending.pop((adapter, session_id), None)
