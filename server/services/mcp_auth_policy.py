"""
Re-evaluates whether the /mcp mount must be disabled because
auth.require_authenticated_user or an adapter's
capabilities.requires_authenticated_user now applies.

The /mcp mount bypasses ORBIT's normal API-key/user auth entirely (it
re-invokes routes internally rather than going through the FastAPI dependency
chain), so it cannot honor either setting. inference_server.py checks this
once at startup and skips the mount entirely when already required. This
module re-runs the same check after every adapter hot reload (admin
create/update/delete/reload-adapters, and the sibling-worker poll path under
performance.workers > 1), since a reload can introduce the requirement into a
server that started without it — and a mount left in place stays reachable
with no identity check at all until the process is restarted.

Only disabling is supported. The MCP sub-app's session-manager lifespan is
started once, at server startup (chained into InferenceServer's own lifespan);
a mount removed here cannot be safely restored without a process restart, so
a reload that *removes* the requirement does not attempt to remount.
"""

import logging
from typing import Any, Optional

from routes.auth_helpers import normalize_adapter_auth_override
from utils import is_true_value

logger = logging.getLogger(__name__)


def adapters_requiring_auth_list(config: dict[str, Any]) -> list:
    # Uses the same tri-state normalization as request-time enforcement
    # (is_authenticated_user_required), so a string-valued override from env
    # substitution (requires_authenticated_user: ${REQUIRE_USER}) is
    # recognized here exactly as it would be on the request path — including
    # a "false" string correctly staying excluded, not just a "true" string
    # correctly being included.
    return [
        a.get('name', '<unnamed>') for a in (config.get('adapters') or [])
        if isinstance(a, dict)
        and normalize_adapter_auth_override(a.get('capabilities', {}).get('requires_authenticated_user')) is True
    ]


def apply_mcp_auth_policy(app_state: Any, config: Optional[dict[str, Any]]) -> None:
    """
    Disable the /mcp mount if `config` now requires an authenticated user,
    globally or on any adapter. No-op if the mount is already gone (either
    never created, or already disabled by a previous call).

    `app_state` is `app.state` — every call site already has this (either
    `request.app.state` in an admin route, or the raw `app.state` passed to
    the sibling-worker poll loop). The FastAPI app itself, needed to remove
    the mount route, is reached via `app_state._fastapi_app`, stashed there
    by InferenceServer at startup.
    """
    mount_route = getattr(app_state, "mcp_mount_route", None)
    if mount_route is None or not config:
        return

    require_auth_globally = is_true_value(config.get('auth', {}).get('require_authenticated_user', False))
    adapters_requiring_auth = adapters_requiring_auth_list(config)
    if not (require_auth_globally or adapters_requiring_auth):
        return

    app = getattr(app_state, "_fastapi_app", None)
    if app is None:
        logger.warning(
            "auth.require_authenticated_user now applies but the /mcp mount could not be "
            "disabled (no app reference on app_state); it remains reachable without "
            "authentication until restart."
        )
        return

    app.router.routes = [r for r in app.router.routes if r is not mount_route]
    app_state.mcp_mount_route = None

    if require_auth_globally:
        logger.warning(
            "auth.require_authenticated_user is now enabled; disabling the /mcp mount, "
            "which cannot enforce it. A restart is required to re-enable /mcp."
        )
    else:
        logger.warning(
            "Adapter(s) %s now set capabilities.requires_authenticated_user: true; "
            "disabling the /mcp mount, which cannot enforce a per-adapter requirement "
            "either. A restart is required to re-enable /mcp.",
            ", ".join(adapters_requiring_auth),
        )
