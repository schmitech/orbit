"""
Admin Audit Storage Strategy
============================

Abstract base class + record type for admin/auth audit events.

These events capture privileged operations performed via `/admin/*` and `/auth/*`
endpoints (user CRUD, API key management, config changes, login/logout, etc.) —
distinct from the conversation-level records handled by `AuditStorageStrategy`.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AdminAuditRecord:
    """Structured record for a single admin or auth audit event."""

    timestamp: datetime
    event_type: str              # e.g. "auth.login", "admin.api_key.create"
    action: str                  # CREATE | UPDATE | DELETE | LOGIN | LOGOUT | CONTROL
    resource_type: str           # user | api_key | adapter | config | prompt | session | server | ...
    method: str                  # HTTP method
    path: str                    # request path (concrete, not template)
    status_code: int
    success: bool
    ip: str
    ip_metadata: Dict[str, Any] = field(default_factory=dict)
    actor_type: str = "anonymous"   # user | api_key | anonymous
    actor_id: Optional[str] = None
    actor_username: Optional[str] = None
    resource_id: Optional[str] = None
    user_agent: Optional[str] = None
    error_message: Optional[str] = None
    request_summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Nested representation (for MongoDB / Elasticsearch)."""
        result: Dict[str, Any] = {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "event_type": self.event_type,
            "action": self.action,
            "resource_type": self.resource_type,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "success": self.success,
            "ip": self.ip,
            "ip_metadata": self.ip_metadata,
            "actor_type": self.actor_type,
        }
        if self.actor_id is not None:
            result["actor_id"] = self.actor_id
        if self.actor_username is not None:
            result["actor_username"] = self.actor_username
        if self.resource_id is not None:
            result["resource_id"] = self.resource_id
        if self.user_agent is not None:
            result["user_agent"] = self.user_agent
        if self.error_message is not None:
            result["error_message"] = self.error_message
        if self.request_summary:
            result["request_summary"] = self.request_summary
        return result

    def to_flat_dict(self) -> Dict[str, Any]:
        """Flattened representation (for SQLite)."""
        return {
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "event_type": self.event_type,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "actor_username": self.actor_username,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "success": 1 if self.success else 0,
            "ip": self.ip,
            "ip_type": self.ip_metadata.get("type", "unknown"),
            "ip_is_local": 1 if self.ip_metadata.get("isLocal", False) else 0,
            "ip_source": self.ip_metadata.get("source", "unknown"),
            "ip_original_value": self.ip_metadata.get("originalValue", ""),
            "user_agent": self.user_agent,
            "error_message": self.error_message,
            "request_summary": json.dumps(self.request_summary) if self.request_summary else None,
        }


class AdminAuditStorageStrategy(ABC):
    """
    Abstract base class for admin audit storage backends.

    Mirrors the shape of AuditStorageStrategy but stores AdminAuditRecord into
    a separate collection/table (default: `audit_admin_logs`).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def store(self, record: AdminAuditRecord) -> bool:
        ...

    @abstractmethod
    async def query(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "timestamp",
        sort_order: int = -1,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    @abstractmethod
    async def clear(self) -> bool:
        ...

    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def backend_name(self) -> str:
        return self.__class__.__name__.replace("AdminAuditStrategy", "").lower()
