"""
Shared dependencies and helpers for the admin routes package.
"""

from typing import Optional

from fastapi import Depends, Request

from routes.auth_dependencies import permission_or_api_key, require_permission


def get_api_key_service(request: Request):
    """Get the API key service from app state"""
    return request.app.state.api_key_service


def get_prompt_service(request: Request):
    """Get the prompt service from app state"""
    return request.app.state.prompt_service


def get_tool_skill_service(request: Request):
    """Get the tool skill service from app state (may be None if no database
    service is configured — see ServiceFactory._initialize_tool_skill_service)."""
    return getattr(request.app.state, 'tool_skill_service', None)


def _serialize_created_at(value) -> Optional[float]:
    """Normalize a created_at value (datetime or ISO string) to a Unix timestamp float."""
    if value is None:
        return None
    if hasattr(value, 'timestamp'):
        return value.timestamp()
    if isinstance(value, str):
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except Exception:
            return None
    return value


# Per-resource-group authorization: bearer token holding the permission, or a
# valid X-API-Key for programmatic/automation access. Conversation content is
# bearer-only (require_permission) so a leaked API key cannot read transcripts.
apikeys_auth = Depends(permission_or_api_key("apikeys.manage"))
adapters_auth = Depends(permission_or_api_key("adapters.manage"))
prompts_auth = Depends(permission_or_api_key("prompts.manage"))
config_auth = Depends(permission_or_api_key("config.manage"))
system_auth = Depends(permission_or_api_key("system.manage"))
logs_auth = Depends(permission_or_api_key("logs.read"))
audit_auth = Depends(permission_or_api_key("audit.read"))
conversations_auth = Depends(require_permission("conversations.read"))
