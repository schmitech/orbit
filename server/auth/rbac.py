"""
Role-Based Access Control (RBAC) Registry
==========================================

Code-defined mapping of role names to the permission strings they grant.
Mirrors the pattern used by server/adapters/capabilities.py: the mapping is
versioned in git rather than editable at runtime, keeping authorization
auditable.

A user may hold multiple roles; their effective permission set is the union
of each role's permissions. The "admin" role holds the wildcard "*", which
grants every permission.
"""

from typing import Dict, Iterable, List, Set

# Every permission string recognized by the system.
ALL_PERMISSIONS: Set[str] = {
    "users.manage",
    "apikeys.manage",
    "adapters.manage",
    "prompts.manage",
    "config.manage",
    "system.manage",
    "logs.read",
    "audit.read",
    "metrics.read",
    "conversations.read",
    "feedback.read",
}

WILDCARD = "*"

# Role -> permissions granted. "user" is the least-privileged default role
# and grants no admin permissions.
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": {WILDCARD},
    "operator": {
        "config.manage",
        "adapters.manage",
        "apikeys.manage",
        "prompts.manage",
        "system.manage",
        "metrics.read",
    },
    "auditor": {
        "logs.read",
        "audit.read",
        "metrics.read",
    },
    "analyst": {
        "conversations.read",
        "feedback.read",
    },
    "user-manager": {
        "users.manage",
    },
    "user": set(),
}


def is_valid_role(role: str) -> bool:
    """Check whether a role name is a known, registered role."""
    return role in ROLE_PERMISSIONS


def get_role_names() -> List[str]:
    """List all registered role names."""
    return list(ROLE_PERMISSIONS.keys())


def permissions_for_roles(roles: Iterable[str]) -> Set[str]:
    """Compute the union of permissions granted by a set of roles.

    Unknown role names are ignored (they grant nothing). If any held role
    grants the wildcard, the result is every registered permission.
    """
    granted: Set[str] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, set())

    if WILDCARD in granted:
        # Keep the literal "*" marker alongside the full expansion so callers
        # that specifically check for wildcard/admin access (has_permission(user, "*"),
        # e.g. require_admin, admin SSO promotion) still see it.
        return set(ALL_PERMISSIONS) | {WILDCARD}
    return granted


def has_permission(user_info: dict, permission: str) -> bool:
    """Check whether a user_info dict (as returned by AuthService) grants a permission."""
    permissions = user_info.get("permissions")
    if permissions is None:
        permissions = permissions_for_roles(user_info.get("roles", []))
    return WILDCARD in permissions or permission in permissions


def has_any_permission(user_info: dict) -> bool:
    """Check whether a user_info dict grants at least one admin permission.

    Used to gate entry to the admin panel: any role beyond the bare "user"
    default may load the shell, with individual tabs/routes further gated
    by their specific required permission.
    """
    permissions = user_info.get("permissions")
    if permissions is None:
        permissions = permissions_for_roles(user_info.get("roles", []))
    return bool(permissions)
