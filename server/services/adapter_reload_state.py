"""
Cross-process propagation for adapter/template hot-reloads under
performance.workers > 1.

Each worker has its own independent DynamicAdapterManager, config_manager
module-level config cache, and adapter_cache - a POST /admin/reload-adapters
(or /admin/reload-templates) request only updates whichever single worker
happened to accept() that connection off the shared listening socket, since
uvicorn's Multiprocess supervisor exposes no way to message a specific
worker or all workers (no pub/sub primitive exists anywhere in this
codebase either - see server/services/cache_backends/).

Backed by database_service, same as pause_state.py and for the same
reasons: never subject to cache invalidation, and guaranteed to be
initialized whenever the admin endpoints are reachable at all. Unlike
pause_state's security-critical fail-closed reads, a failed read here just
means "skip this poll tick" - this is an eventual-consistency concern, not
a security gate.

database_service.update_one() only supports MongoDB-style $set (not $inc -
see sqlite_service.py/postgres_service.py's implementations), so bumping the
generation counter is read-then-write, not atomic. A lost update under two
concurrent bumps just means sibling workers do one full reload instead of
two - always safe, since "reload everything" is already the existing
no-adapter-name path. So this module intentionally does NOT track a
per-adapter hint: any detected generation change triggers a full reload,
which keeps this correct under races without needing atomic increments.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_COLLECTION = "adapter_reload_state"
_KINDS = ("adapter_config", "templates")
_POLL_INTERVAL_SECONDS = 5


def _doc_id(kind: str) -> str:
    return f"reload:{kind}"


async def ensure_initialized(app_state: Any) -> None:
    """
    Create both kinds' rows if missing. Called from every worker's own
    lifespan startup - idempotent, safe to race (see pause_state.py).
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        return

    for kind in _KINDS:
        try:
            existing = await db.find_one(_COLLECTION, {"_id": _doc_id(kind)})
            if existing is None:
                await db.insert_one(_COLLECTION, {"_id": _doc_id(kind), "generation": 0})
        except Exception:
            pass


async def bump_generation(app_state: Any, kind: str) -> Optional[int]:
    """
    Increment the durable generation counter for `kind`, signalling every
    other worker to fully reload on its next poll tick.

    Returns the new generation number on success, or None on failure. A
    failure is non-fatal to the caller (the local reload already happened
    by the time this is called) - only propagation to siblings is at risk,
    and self-heals on the next successful bump for that kind.
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        return None

    try:
        existing = await db.find_one(_COLLECTION, {"_id": _doc_id(kind)})
        new_generation = (existing.get("generation", 0) if existing else 0) + 1
        if existing is not None:
            ok = await db.update_one(
                _COLLECTION, {"_id": _doc_id(kind)}, {"$set": {"generation": new_generation}}
            )
        else:
            ok = await db.insert_one(_COLLECTION, {"_id": _doc_id(kind), "generation": new_generation}) is not None
    except Exception:
        logger.warning("Failed to bump reload generation for '%s'", kind, exc_info=True)
        return None

    if not ok:
        logger.warning(
            "Failed to bump reload generation for '%s' - other workers may not pick up this change", kind
        )
        return None

    return new_generation


async def get_generation(app_state: Any, kind: str) -> Optional[int]:
    """
    Read the current generation for `kind`.

    Returns None on any read failure or if the row is genuinely absent -
    fail-open: the caller just retries next tick, unlike pause_state's
    fail-closed semantics (this isn't a security gate).
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        return None

    try:
        doc = await db.find_one(_COLLECTION, {"_id": _doc_id(kind)})
    except Exception:
        return None

    if doc is None:
        return None
    return doc.get("generation", 0)


async def _apply_reload(app_state: Any, kind: str) -> bool:
    """
    Fully reload `kind` locally - called when a sibling worker's bump is
    detected. Returns whether the reload actually succeeded, so the caller
    can decide whether it's safe to advance its `last_seen` baseline past
    this generation - advancing on a failed reload would abandon that
    generation forever (no retry until another admin reload bumps it again).
    """
    adapter_manager = getattr(app_state, "adapter_manager", None)
    if adapter_manager is None:
        return False

    try:
        if kind == "adapter_config":
            from config.config_manager import reload_adapters_config

            config_path = getattr(app_state, "config_path", None)
            if not config_path:
                logger.warning("Cannot propagate adapter reload: config_path unavailable")
                return False
            new_config = reload_adapters_config(config_path)
            summary = await adapter_manager.reload_adapter_configs(new_config, None)
            logger.info("Propagated adapter reload from another worker: %s", summary)
        elif kind == "templates":
            summary = await adapter_manager.reload_templates(None)
            logger.info("Propagated template reload from another worker: %s", summary)
        else:
            return False
    except Exception as e:
        logger.warning("Failed to propagate %s reload from another worker: %s", kind, e)
        return False

    return True


async def poll_and_apply_reloads(app_state: Any, interval_seconds: float = _POLL_INTERVAL_SECONDS) -> None:
    """
    Background loop (one per worker): watches both kinds' generation
    counters and applies a full reload locally whenever a sibling worker's
    admin-triggered reload bumps them. Runs until cancelled.

    Shares its `last_seen` baseline on `app_state._adapter_reload_last_seen`
    so admin_routes.py can update it immediately after a local bump,
    keeping the worker that served the reload request from redundantly
    reloading itself again on its own next tick.
    """
    db = getattr(app_state, "database_service", None)
    if db is None:
        logger.info("Multi-worker adapter reload sync unavailable: no database_service configured")
        return

    await ensure_initialized(app_state)

    last_seen: Dict[str, int] = {}
    for kind in _KINDS:
        generation = await get_generation(app_state, kind)
        last_seen[kind] = generation if generation is not None else 0

    app_state._adapter_reload_last_seen = last_seen

    while True:
        await asyncio.sleep(interval_seconds)
        for kind in _KINDS:
            generation = await get_generation(app_state, kind)
            if generation is None or generation == last_seen[kind]:
                continue

            # Only advance past this generation if the reload actually
            # succeeded - otherwise this generation is retried on every
            # subsequent tick until it succeeds (or a newer bump replaces
            # it, at which point a full reload is applied anyway).
            if await _apply_reload(app_state, kind):
                last_seen[kind] = generation
