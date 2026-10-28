"""In-memory "last resolved turn" store backing follow-up query rewriting for
intent retrievers.

When an intent retriever (SQL/HTTP) successfully resolves a turn — either a
fresh template match or a completed clarification round — it stashes the
standalone "effective query" plus the resolved template/parameters, keyed by
(adapter, session_id). The next turn's follow-up-rewrite step reads this to
decide whether the new message is a follow-up ("what about Ottawa") and, if
so, rewrite it into a standalone question using this prior context.

Process-local, best-effort, and short-lived (TTL-bounded) — same tradeoffs as
services/intent_clarification_state.py, which this module mirrors: losing
this state just disables the rewrite for that turn and the retriever falls
back to matching the new message from scratch.
"""

import time
from typing import Any

_MAX_ENTRIES = 1000
_DEFAULT_TTL_SECONDS = 300.0

_last_turn: dict[tuple[str, str], dict[str, Any]] = {}


def store_last_turn(adapter: str, session_id: str, payload: dict[str, Any], ttl: float = _DEFAULT_TTL_SECONDS) -> None:
    """Stash the resolved turn (effective_query/template_id/parameters) for this
    adapter/session, replacing any prior one."""
    if not session_id:
        return
    _last_turn[(adapter, session_id)] = {"payload": payload, "expires_at": time.time() + ttl}
    while len(_last_turn) > _MAX_ENTRIES:
        _last_turn.pop(next(iter(_last_turn)))


def get_last_turn(adapter: str, session_id: str) -> dict[str, Any] | None:
    """Retrieve the last resolved turn for this adapter/session, if any and unexpired.
    Non-destructive: unlike clarification's pop_pending, a turn may be read by the
    rewrite step and later still exist for the retriever to update it anew."""
    if not session_id:
        return None
    entry = _last_turn.get((adapter, session_id))
    if entry is None:
        return None
    if entry["expires_at"] < time.time():
        _last_turn.pop((adapter, session_id), None)
        return None
    return entry["payload"]


def clear_last_turn(adapter: str, session_id: str) -> None:
    if not session_id:
        return
    _last_turn.pop((adapter, session_id), None)
