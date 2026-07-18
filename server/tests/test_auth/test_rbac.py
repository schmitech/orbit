"""Unit tests for the role/permission registry (auth/rbac.py)."""

import pytest

from auth.rbac import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    WILDCARD,
    get_role_names,
    has_any_permission,
    has_permission,
    is_valid_role,
    permissions_for_roles,
)


def test_is_valid_role():
    assert is_valid_role("admin")
    assert is_valid_role("operator")
    assert is_valid_role("user")
    assert not is_valid_role("superadmin")
    assert not is_valid_role("")


def test_get_role_names_matches_registry():
    assert set(get_role_names()) == set(ROLE_PERMISSIONS.keys())


def test_admin_wildcard_expands_to_all_permissions():
    # The literal "*" marker is retained alongside the full expansion so that
    # callers checking has_permission(user, "*") (require_admin, admin SSO
    # promotion) still recognize admins as wildcard holders.
    assert permissions_for_roles(["admin"]) == ALL_PERMISSIONS | {WILDCARD}


def test_user_role_grants_nothing():
    assert permissions_for_roles(["user"]) == set()


def test_operator_excludes_conversation_and_feedback_permissions():
    perms = permissions_for_roles(["operator"])
    assert "conversations.read" not in perms
    assert "feedback.read" not in perms
    assert "config.manage" in perms
    assert "adapters.manage" in perms


def test_operator_excludes_logs_and_audit_permissions():
    """Operator runs day-to-day operations (config/adapters/apikeys/prompts/
    system control) but has no visibility into logs or the audit trail -
    that requires the auditor role."""
    perms = permissions_for_roles(["operator"])
    assert "logs.read" not in perms
    assert "audit.read" not in perms
    assert "metrics.read" in perms


def test_analyst_only_grants_conversation_and_feedback_permissions():
    assert permissions_for_roles(["analyst"]) == {"conversations.read", "feedback.read"}


def test_union_of_multiple_roles():
    perms = permissions_for_roles(["analyst", "auditor"])
    assert perms == {"conversations.read", "feedback.read", "logs.read", "audit.read", "metrics.read"}


def test_union_includes_wildcard_expansion_if_any_role_has_it():
    perms = permissions_for_roles(["user", "admin"])
    assert perms == ALL_PERMISSIONS | {WILDCARD}


def test_unknown_role_grants_nothing():
    assert permissions_for_roles(["not-a-real-role"]) == set()


def test_has_permission_with_explicit_permissions_list():
    user_info = {"permissions": ["conversations.read"]}
    assert has_permission(user_info, "conversations.read")
    assert not has_permission(user_info, "config.manage")


def test_has_permission_falls_back_to_roles_when_permissions_absent():
    user_info = {"roles": ["operator"]}
    assert has_permission(user_info, "config.manage")
    assert not has_permission(user_info, "conversations.read")


def test_has_permission_wildcard_grants_everything():
    user_info = {"permissions": ["*"]}
    assert has_permission(user_info, "config.manage")
    assert has_permission(user_info, "anything.at.all")


def test_has_any_permission():
    assert has_any_permission({"roles": ["analyst"]})
    assert not has_any_permission({"roles": ["user"]})
    assert not has_any_permission({"roles": []})


def test_has_permission_wildcard_check_against_real_user_info_shape():
    """Regression test: require_admin and the admin SSO callback check
    has_permission(user, "*") directly. An admin user's `permissions` list, as
    produced by AuthService._user_info() via permissions_for_roles(), must
    still satisfy that check."""
    user_info = {"roles": ["admin"], "permissions": sorted(permissions_for_roles(["admin"]))}
    assert has_permission(user_info, "*")
    assert has_permission(user_info, "config.manage")
