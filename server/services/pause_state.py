"""
Cross-process server pause flag, durable across cache flushes and worker restarts.

Backed by the primary database_service (MongoDB/SQLite/Postgres — whichever backend
is configured), not the ephemeral cache_service. The cache layer is routinely
invalidated (startup clear, TTLs, admin cache-clear endpoints), and Memcached in
particular can only invalidate by flushing its entire keyspace with no way to spare
a specific key — any snapshot-around-the-flush approach races with a concurrent
pause/resume. database_service is never subject to cache invalidation, and is
guaranteed to be initialized whenever the admin endpoints are reachable at all
(auth is always enabled, and auth requires database_service).

Reads use find_one_strict(), which raises DatabaseOperationError on a query failure
instead of silently returning None like find_one() - a database outage must not be
misread as "no pause document, so not paused". ensure_initialized() is called once
at server startup so the row/document already exists by the time any request can
reach it, so a find_one_strict() failure at request time can only mean a real
outage, never "row not created yet".
"""

from typing import Any

from services.database_service import DatabaseOperationError

_COLLECTION = "system_state"
_DOC_ID = "server_paused"


async def ensure_initialized(app_state: Any) -> None:
    """
    Create the pause-state row if it doesn't exist yet. Called once at server
    startup, before any request can reach is_paused()/set_paused() - see
    inference_server.py. Best-effort: if the database is unreachable at startup,
    the server has bigger problems than this, and later reads will correctly
    fail closed.
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        return

    try:
        existing = await db.find_one(_COLLECTION, {"_id": _DOC_ID})
        if existing is None:
            await db.insert_one(_COLLECTION, {"_id": _DOC_ID, "value": False})
    except Exception:
        pass


async def set_paused(app_state: Any, paused: bool) -> bool:
    """
    Durably set the pause flag on app.state and in database_service.

    Returns True if the write succeeded, False otherwise. Callers must treat False
    as a failed pause/resume and not report success — app.state is left untouched
    in that case, since applying the change only locally would reproduce the exact
    per-worker inconsistency this module exists to prevent.
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        # No durable store available (shouldn't happen in practice - see module
        # docstring) - fall back to a process-local flag as a last resort.
        app_state.paused = paused
        return True

    try:
        existing = await db.find_one(_COLLECTION, {"_id": _DOC_ID})
        if existing is not None:
            if bool(existing.get("value")) == paused:
                # Already in the desired state (e.g. /pause called while already
                # paused) - skip the write. MongoDB's update_one() reports "not
                # modified" (False) for a $set to an unchanged value, which would
                # otherwise look like a write failure for a no-op call.
                ok = True
            else:
                ok = await db.update_one(_COLLECTION, {"_id": _DOC_ID}, {"$set": {"value": paused}})
                if not ok:
                    # Treat "matched but not reported as modified" as success too,
                    # in case another writer raced us to the same value in between.
                    confirmed = await db.find_one(_COLLECTION, {"_id": _DOC_ID})
                    ok = confirmed is not None and bool(confirmed.get("value")) == paused
        else:
            ok = await db.insert_one(_COLLECTION, {"_id": _DOC_ID, "value": paused}) is not None
    except Exception:
        ok = False

    if not ok:
        return False

    app_state.paused = paused
    return True


async def is_paused(app_state: Any) -> bool:
    """
    Check the pause flag from the durable store.

    Fails closed: a failed read (DatabaseOperationError) is treated as paused
    rather than risk silently accepting traffic during a database outage. A
    genuinely absent document (None, no exception) means "never paused".
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        return getattr(app_state, "paused", False)

    try:
        doc = await db.find_one_strict(_COLLECTION, {"_id": _DOC_ID})
    except DatabaseOperationError:
        return True

    if doc is None:
        return False

    return bool(doc.get("value", False))
