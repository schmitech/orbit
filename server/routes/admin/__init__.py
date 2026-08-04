"""
Admin routes for ORBIT.

The admin surface is split by concern; this module composes the per-concern
sub-routers into the single ``admin_router`` mounted by the app. Route order
matters: FastAPI matches in registration order, so modules declaring literal
paths that could be shadowed by another module's path parameter are included
first.
"""

from fastapi import APIRouter

from routes.admin import (
    adapters,
    api_keys,
    audit,
    chat_history,
    config,
    jobs,
    lifecycle,
    logs,
    mcp,
    observability,
    prompts,
)
from routes.admin._shared import (
    adapters_auth,
    apikeys_auth,
    audit_auth,
    config_auth,
    conversations_auth,
    logs_auth,
    prompts_auth,
    system_auth,
)

admin_router = APIRouter(prefix="/admin", tags=["admin"])

for _module in (
    api_keys,
    adapters,
    prompts,
    chat_history,
    jobs,
    config,
    lifecycle,
    logs,
    audit,
    observability,
    mcp,
):
    admin_router.include_router(_module.router)

__all__ = [
    "admin_router",
    "adapters_auth",
    "apikeys_auth",
    "audit_auth",
    "config_auth",
    "conversations_auth",
    "logs_auth",
    "prompts_auth",
    "system_auth",
]
