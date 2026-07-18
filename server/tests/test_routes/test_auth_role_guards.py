"""Regression tests for user-role management route guards."""

import pytest
from fastapi import HTTPException

from routes.auth_routes import SetRolesRequest, set_user_roles


class _RoleService:
    async def set_roles(self, *_args):
        raise AssertionError("Self-role updates must not reach the service")


@pytest.mark.asyncio
async def test_set_user_roles_rejects_self_assignment():
    with pytest.raises(HTTPException) as exc_info:
        await set_user_roles(
            user_id="current-user-id",
            request=SetRolesRequest(roles=["user"]),
            current_user={"id": "current-user-id", "permissions": ["users.manage"]},
            auth_service=_RoleService(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Cannot change your own roles"
