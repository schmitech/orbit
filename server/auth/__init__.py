"""RBAC role/permission registry."""

from auth.rbac import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    get_role_names,
    has_any_permission,
    has_permission,
    is_valid_role,
    permissions_for_roles,
)

__all__ = [
    'ALL_PERMISSIONS',
    'ROLE_PERMISSIONS',
    'get_role_names',
    'has_any_permission',
    'has_permission',
    'is_valid_role',
    'permissions_for_roles',
]
