"""
Shared dependencies and helpers for the admin routes package.
"""

from typing import Optional

from fastapi import Depends, Request

from routes.auth_dependencies import require_permission


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
        except (ValueError, TypeError):
            return None
    return value


# Management routes require an authenticated bearer-token user with the
# resource-specific permission. Inference API keys intentionally carry no
# administrative privileges and must never authorize this control plane.
apikeys_auth = Depends(require_permission("apikeys.manage"))
adapters_auth = Depends(require_permission("adapters.manage"))
prompts_auth = Depends(require_permission("prompts.manage"))
config_auth = Depends(require_permission("config.manage"))
system_auth = Depends(require_permission("system.manage"))
logs_auth = Depends(require_permission("logs.read"))
audit_auth = Depends(require_permission("audit.read"))
conversations_auth = Depends(require_permission("conversations.read"))
