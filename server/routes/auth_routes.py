"""
Authentication Routes
====================

This module contains authentication-related endpoints for:
- User login and logout
- User registration
- Current user information
- Token management
"""

import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from routes.auth_dependencies import get_auth_service, get_current_user, get_current_user_with_token, require_permission
from services.auth_service import AuthService
from services.login_rate_limiter import (
    get_login_rate_limiter,
    login_rate_limited_response,
)
from auth.rbac import has_permission, is_valid_role, get_role_names
from services.user_blacklist_service import (
    ENTRY_TYPES,
    MAX_PATTERN_LENGTH,
    MAX_REASON_LENGTH,
    BlacklistRuleError,
    matches,
    normalize_pattern,
)

logger = logging.getLogger(__name__)

# Create the auth router
auth_router = APIRouter(prefix="/auth", tags=["authentication"])


def validate_username_or_400(username: str) -> None:
    error = AuthService.validate_username(username)
    if error:
        raise HTTPException(status_code=400, detail=error)


def validate_password_or_400(password: str, auth_service: AuthService) -> None:
    error = auth_service.validate_password(password, auth_service.password_policy)
    if error:
        raise HTTPException(status_code=400, detail=error)


@auth_router.get("/password-policy")
async def get_password_policy(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Return the active, non-sensitive local-password rules for the admin UI."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return AuthService.normalize_password_policy(auth_service.password_policy)


# Request/Response Models
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=AuthService.USERNAME_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=AuthService.PASSWORD_MAX_LENGTH)


class LoginResponse(BaseModel):
    token: str
    user: dict[str, Any]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=AuthService.USERNAME_MAX_LENGTH)
    password: str = Field(min_length=1, max_length=AuthService.PASSWORD_MAX_LENGTH)
    role: str = "user"
    roles: Optional[list[str]] = None


class RegisterResponse(BaseModel):
    id: str
    username: str
    role: str
    roles: list[str]


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    roles: list[str] = []
    active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    provider: Optional[str] = None
    email: Optional[str] = None


class UserByUsernameResponse(BaseModel):
    id: str
    username: str
    role: str
    roles: list[str] = []
    active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=AuthService.PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=1, max_length=AuthService.PASSWORD_MAX_LENGTH)


class ResetPasswordRequest(BaseModel):
    user_id: str
    new_password: str = Field(min_length=1, max_length=AuthService.PASSWORD_MAX_LENGTH)


class DeactivateUserRequest(BaseModel):
    user_id: str


class SetRolesRequest(BaseModel):
    roles: list[str]


class SessionResponse(BaseModel):
    id: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    expires: Optional[str] = None


class BlacklistRuleRequest(BaseModel):
    pattern: str = Field(min_length=1, max_length=MAX_PATTERN_LENGTH)
    entry_type: str = Field(description="One of: email, user_id, username")
    reason: Optional[str] = Field(default=None, max_length=MAX_REASON_LENGTH)


class BlacklistRuleResponse(BaseModel):
    id: str
    pattern: str
    entry_type: str
    reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    # Only populated on creation: how many existing users the rule matched and
    # how many of their sessions were revoked.
    matched_users: Optional[int] = None
    revoked_sessions: Optional[int] = None


# Authentication Endpoints
@auth_router.post("/login", response_model=LoginResponse)
async def login(
    login_request: LoginRequest,
    request: Request,
    auth_service = Depends(get_auth_service)
):
    """
    Authenticate a user and return a bearer token.
    
    Args:
        request: Login credentials
        auth_service: Authentication service
        
    Returns:
        Login response with token and user info
        
    Raises:
        HTTPException: If login fails
    """
    try:
        limiter = get_login_rate_limiter(request)
        ip_result = await limiter.check_ip(request)
        if not ip_result.allowed:
            request.state.auth_rate_limited = True
            return login_rate_limited_response(ip_result)

        username_result = await limiter.check_username(
            request, login_request.username
        )
        if not username_result.allowed:
            request.state.auth_rate_limited = True
            return login_rate_limited_response(username_result)

        logger.info(f"Login attempt for user: {login_request.username}")
        
        failure_context: dict[str, Any] = {}
        success, token, user_info = await auth_service.authenticate_user(
            login_request.username,
            login_request.password,
            failure_context,
            ip_address=limiter.client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        
        logger.info(f"Authentication result: success={success}")
        
        if not success:
            # AuthService classifies the failure at the service boundary so
            # early failures (notably durable lockout) remain visible here.
            # The middleware permits only this coarse reason into the audit
            # summary; passwords and account-existence details are excluded.
            request.state.audit_context = {
                "summary": {"reason": failure_context.get("reason", "invalid_credentials")}
            }
            username_result = await limiter.record_username_failure(
                request, login_request.username
            )
            if not username_result.allowed:
                request.state.auth_rate_limited = True
                return login_rate_limited_response(username_result)
            # Set these only after rate limiting has declined to supersede the
            # credential failure. This keeps request state internally
            # unambiguous as well as preserving middleware event precedence.
            request.state.auth_login_failed = True
            request.state.auth_login_locked_out = failure_context.get("locked_out", False)
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password"
            )
        
        return LoginResponse(
            token=token,
            user=user_info
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Login error details: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Get information about the currently authenticated user.
    
    Args:
        current_user: Current user from authentication
        auth_service: Authentication service
        
    Returns:
        Current user information with full details
    """
    # ``get_current_user`` deliberately returns None when a request has no
    # bearer credential, because several routes use authentication as an
    # optional input.  /auth/me is not one of them: without this guard the
    # lookup below dereferences None and turns an authentication failure into
    # a misleading 500 response.
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Get complete user data from database
        user = await auth_service.get_user_by_id(current_user["id"])
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )
        
        # Safe datetime conversion
        created_at = None
        if user.get("created_at"):
            try:
                created_at = user["created_at"].isoformat() if hasattr(user["created_at"], 'isoformat') else str(user["created_at"])
            except Exception:
                created_at = None
        
        last_login = None
        if user.get("last_login"):
            try:
                last_login = user["last_login"].isoformat() if hasattr(user["last_login"], 'isoformat') else str(user["last_login"])
            except Exception:
                last_login = None
        
        return UserResponse(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            roles=user.get("roles") or [user["role"]],
            active=user["active"],
            created_at=created_at,
            last_login=last_login
        )

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error getting current user info: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@auth_router.get("/roles", dependencies=[Depends(require_permission("users.manage"))])
async def list_roles():
    """List all registered roles, for populating role-assignment UI."""
    return {"roles": get_role_names()}


@auth_router.get("/users", response_model=list[UserResponse], dependencies=[Depends(require_permission("users.manage"))])
async def list_users(
    role: Optional[str] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    auth_service = Depends(get_auth_service)
):
    """
    List all users in the system with optional filtering and pagination.
    
    Requires admin authentication.
    
    Args:
        role: Optional role filter (user, admin)
        active_only: If True, only return active users
        limit: Maximum number of users to return (default: 100, max: 1000)
        offset: Number of users to skip for pagination (default: 0)
    """
    try:
        # Validate parameters
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 100
        if offset < 0:
            offset = 0
        
        # Build filter query
        filter_query = {}
        if role:
            filter_query["role"] = role
        if active_only:
            filter_query["active"] = True
        
        users = await auth_service.list_users(filter_query=filter_query, limit=limit, offset=offset)
        
        result = []
        for user in users:
            # Safe datetime conversion
            created_at = None
            if user.get("created_at"):
                try:
                    created_at = user["created_at"].isoformat() if hasattr(user["created_at"], 'isoformat') else str(user["created_at"])
                except Exception:
                    created_at = None
            
            last_login = None
            if user.get("last_login"):
                try:
                    last_login = user["last_login"].isoformat() if hasattr(user["last_login"], 'isoformat') else str(user["last_login"])
                except Exception:
                    last_login = None
            
            result.append(UserResponse(
                id=user["id"],
                username=user["username"],
                role=user["role"],
                roles=user.get("roles") or [user["role"]],
                active=user["active"],
                created_at=created_at,
                last_login=last_login,
                provider=user.get("provider"),
                email=user.get("email")
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing users: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Internal server error")

@auth_router.get("/users/by-username", response_model=UserByUsernameResponse, dependencies=[Depends(require_permission("users.manage"))])
async def get_user_by_username(
    username: str,
    auth_service = Depends(get_auth_service)
):
    """
    Get a user by username (admin only).
    
    This endpoint allows efficient lookup of users by username without
    fetching all users and filtering client-side.
    
    Args:
        username: The username to search for
        admin_user: Current admin user (required)
        auth_service: Authentication service
        
    Returns:
        User information for the specified username
        
    Raises:
        HTTPException: If user not found or access denied
    """
    try:
        user = await auth_service.get_user_by_username(username)
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with username '{username}' not found"
            )
        
        return UserByUsernameResponse(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            roles=user.get("roles") or [user["role"]],
            active=user["active"]
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error getting user by username: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@auth_router.post("/register", response_model=RegisterResponse)
async def register_user(
    request: RegisterRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Register a new user (admin only).
    
    Args:
        request: Registration data
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Registration response with user info
        
    Raises:
        HTTPException: If registration fails or user not admin
    """
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can create new users"
        )

    validate_username_or_400(request.username)
    validate_password_or_400(request.password, auth_service)
    assigned_roles = request.roles or [request.role]
    invalid_roles = [r for r in assigned_roles if not is_valid_role(r)]
    if invalid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role(s): {', '.join(invalid_roles)}. Valid roles: {', '.join(get_role_names())}"
        )

    try:
        user_id = await auth_service.create_user(
            request.username,
            request.password,
            roles=assigned_roles
        )

        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="Failed to create user. Username may already exist."
            )

        return RegisterResponse(
            id=user_id,
            username=request.username,
            role=assigned_roles[0],
            roles=assigned_roles
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        # If it's a duplicate key error or already exists, return 400
        if 'duplicate key error' in str(e).lower() or 'already exists' in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail="Failed to create user. Username may already exist."
            )
        raise HTTPException(
            status_code=500,
            detail="Internal server error during registration"
        )


@auth_router.post("/logout")
async def logout(
    user_and_token: tuple[dict[str, Any], str] = Depends(get_current_user_with_token),
    auth_service = Depends(get_auth_service)
):
    """
    Logout the current user by invalidating their token.
    
    Args:
        user_and_token: Tuple of (current_user, token)
        auth_service: Authentication service
        
    Returns:
        Logout confirmation
    """
    try:
        current_user, token = user_and_token
        
        # Invalidate the token
        success = await auth_service.logout(token)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to logout"
            )
        
        return {"message": "Logout successful"}
        
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during logout"
        )


@auth_router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Delete a user (admin only).
    
    Args:
        user_id: The ID of the user to delete
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Deletion confirmation
        
    Raises:
        HTTPException: If deletion fails or user not admin
    """
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can delete users"
        )
    
    # Prevent admin from deleting themselves
    if current_user.get("id") == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account"
        )
    
    try:
        success = await auth_service.delete_user(user_id)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="User not found or could not be deleted"
            )
        
        return {"message": "User deleted successfully", "user_id": user_id}

    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"User deletion error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during user deletion"
        )


@auth_router.put("/users/{user_id}/roles")
async def set_user_roles(
    user_id: str,
    request: SetRolesRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """Replace a user's role assignment (users.manage permission required)."""
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can assign roles"
        )

    if current_user.get("id") == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot change your own roles"
        )

    invalid_roles = [r for r in request.roles if not is_valid_role(r)]
    if invalid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role(s): {', '.join(invalid_roles)}. Valid roles: {', '.join(get_role_names())}"
        )

    success = await auth_service.set_roles(user_id, request.roles)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or roles could not be updated")

    return {"message": "Roles updated successfully", "user_id": user_id, "roles": request.roles}


@auth_router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Change the current user's password.
    
    Args:
        request: Password change request with current and new passwords
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Password change confirmation
        
    Raises:
        HTTPException: If password change fails
    """
    try:
        validate_password_or_400(request.new_password, auth_service)
        success = await auth_service.change_password(
            current_user["id"],
            request.current_password,
            request.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect or password change failed"
            )
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Password change error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during password change"
        )


@auth_router.post("/reset-password")
async def reset_user_password(
    request: ResetPasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Reset a user's password (admin only).
    
    Args:
        request: Password reset request with user ID and new password
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Password reset confirmation
        
    Raises:
        HTTPException: If password reset fails or user not admin
    """
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can reset user passwords"
        )
    
    # Prevent admin from resetting their own password this way
    if current_user.get("id") == request.user_id:
        raise HTTPException(
            status_code=400,
            detail="Use change-password to change your own password"
        )

    validate_password_or_400(request.new_password, auth_service)
    
    try:
        success = await auth_service.reset_user_password(
            request.user_id,
            request.new_password
        )
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="User not found or password reset failed"
            )
        
        return {"message": "Password reset successfully", "user_id": request.user_id}
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during password reset"
        )


@auth_router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Deactivate a user (admin only).
    
    Args:
        user_id: The ID of the user to deactivate
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Deactivation confirmation
        
    Raises:
        HTTPException: If deactivation fails or user not admin
    """
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can deactivate users"
        )
    
    # Prevent admin from deactivating themselves
    if current_user.get("id") == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot deactivate your own account"
        )
    
    try:
        success = await auth_service.update_user_status(user_id, False)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="User not found or could not be deactivated"
            )
        
        return {"message": "User deactivated successfully", "user_id": user_id}
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"User deactivation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during user deactivation"
        )


@auth_router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Activate a user (admin only).
    
    Args:
        user_id: The ID of the user to activate
        current_user: Current authenticated user
        auth_service: Authentication service
        
    Returns:
        Activation confirmation
        
    Raises:
        HTTPException: If activation fails or user not admin
    """
    if not has_permission(current_user, "users.manage"):
        raise HTTPException(
            status_code=403,
            detail="Only users with the users.manage permission can activate users"
        )
    
    try:
        success = await auth_service.update_user_status(user_id, True)
        
        if not success:
            raise HTTPException(
                status_code=404,
                detail="User not found or could not be activated"
            )
        
        return {"message": "User activated successfully", "user_id": user_id}
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"User activation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during user activation"
        ) 


# Blacklist Endpoints

def _require_blacklist(auth_service):
    """Return the blacklist service, or 503 if auth hasn't initialized it yet."""
    blacklist = getattr(auth_service, "blacklist", None)
    if blacklist is None:
        raise HTTPException(
            status_code=503, detail="User blacklist service is not available"
        )
    return blacklist


def _publish_rule_audit_context(request: Request, rule: dict[str, Any]) -> None:
    """Hand the audit middleware the values that were actually persisted.

    The submitted pattern is not canonical - the service trims and lowercases it
    before storing - and on create the rule id doesn't exist until after the
    insert. Recording the raw request would leave the ledger identifying a rule
    that isn't what's in the database, breaking search and correlation.

    Only fields on this route's audit allowlist survive the merge, so this
    cannot widen what the ledger stores. A stored value of None is published
    as-is to clear the field - a reason submitted as whitespace normalizes to
    None, and the ledger should not keep showing the raw spaces.
    """
    request.state.audit_context = {
        "resource_id": str(rule.get("_id") or rule.get("id") or "") or None,
        "summary": {key: rule.get(key) for key in ("pattern", "entry_type", "reason")},
    }


def _validate_rule_or_400(
    request: "BlacklistRuleRequest", current_user: dict[str, Any]
) -> str:
    """Validate a submitted rule and return its normalized pattern.

    Shared by create and update so the self-lockout guard can't be enforced on
    one path but not the other - editing a rule to match yourself locks you out
    exactly as surely as creating one does.
    """
    if request.entry_type not in ENTRY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"entry_type must be one of: {', '.join(ENTRY_TYPES)}",
        )

    try:
        normalized = normalize_pattern(request.pattern)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))

    self_value = {
        "email": current_user.get("email"),
        "user_id": current_user.get("id"),
        "username": current_user.get("username"),
    }[request.entry_type]
    if matches(normalized, self_value):
        raise HTTPException(
            status_code=400,
            detail="This rule would block your own account. Refine the pattern.",
        )
    return normalized


def _serialize_rule(rule: dict[str, Any]) -> BlacklistRuleResponse:
    created_at = rule.get("created_at")
    if created_at is not None:
        created_at = (
            created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        )
    return BlacklistRuleResponse(
        id=str(rule.get("_id") or rule.get("id")),
        pattern=rule["pattern"],
        entry_type=rule["entry_type"],
        reason=rule.get("reason"),
        created_by=rule.get("created_by"),
        created_at=created_at,
        matched_users=rule.get("matched_users"),
        revoked_sessions=rule.get("revoked_sessions"),
    )


@auth_router.get(
    "/blacklist",
    response_model=list[BlacklistRuleResponse],
    dependencies=[Depends(require_permission("users.manage"))],
)
async def list_blacklist_rules(auth_service=Depends(get_auth_service)):
    """List every blacklist rule, newest first (users.manage permission required)."""
    blacklist = _require_blacklist(auth_service)
    try:
        rules = await blacklist.list_rules()
        return [_serialize_rule(rule) for rule in rules]
    except Exception as e:
        logger.error(f"Error listing blacklist rules: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.post(
    "/blacklist",
    response_model=BlacklistRuleResponse,
    dependencies=[Depends(require_permission("users.manage"))],
)
async def create_blacklist_rule(
    request: BlacklistRuleRequest,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Block an identity pattern and revoke any matching live sessions.

    The rule is refused if it would match the requesting administrator, since
    the blacklist is enforced at token validation and would otherwise lock the
    caller out of the admin panel they'd need to undo it.
    """
    blacklist = _require_blacklist(auth_service)
    normalized = _validate_rule_or_400(request, current_user)

    try:
        rule = await blacklist.add_rule(
            pattern=normalized,
            entry_type=request.entry_type,
            reason=request.reason,
            created_by=current_user.get("username"),
        )
        _publish_rule_audit_context(http_request, rule)
        return _serialize_rule(rule)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating blacklist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.put(
    "/blacklist/{rule_id}",
    response_model=BlacklistRuleResponse,
    dependencies=[Depends(require_permission("users.manage"))],
)
async def update_blacklist_rule(
    rule_id: str,
    request: BlacklistRuleRequest,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Edit an existing rule, re-revoking sessions for whoever it now matches.

    Subject to the same validation and self-lockout guard as creation.
    """
    blacklist = _require_blacklist(auth_service)
    normalized = _validate_rule_or_400(request, current_user)

    try:
        rule = await blacklist.update_rule(
            rule_id=rule_id,
            pattern=normalized,
            entry_type=request.entry_type,
            reason=request.reason,
        )
        if rule is None:
            raise HTTPException(status_code=404, detail="Blacklist rule not found")
        _publish_rule_audit_context(http_request, rule)
        return _serialize_rule(rule)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating blacklist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.delete(
    "/blacklist/{rule_id}",
    dependencies=[Depends(require_permission("users.manage"))],
)
async def delete_blacklist_rule(rule_id: str, auth_service=Depends(get_auth_service)):
    """Remove a blacklist rule (users.manage permission required).

    Removing a rule restores the ability to authenticate; it does not restore
    the sessions that were revoked when the rule was added.
    """
    blacklist = _require_blacklist(auth_service)
    try:
        if not await blacklist.delete_rule(rule_id):
            raise HTTPException(status_code=404, detail="Blacklist rule not found")
        return {"status": "deleted", "id": rule_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting blacklist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Allowlist Endpoints
#
# The mirror of the blacklist above: these rules pre-clear external (Entra /
# Auth0) identities under `auth.providers.access_control: allowlist`, where an
# unmatched subject is never provisioned an ORBIT account at all. The request
# and response shapes are identical, so the models and serializer are shared.
#
# The self-lockout guard is inverted. Creating a deny rule can lock you out, so
# POST /blacklist guards against it; creating an *allow* rule only ever grants,
# so POST here needs no guard. It is DELETE and a narrowing PUT that revoke
# access, so the guard lives on those instead.


def _require_allowlist(auth_service):
    """Return the allowlist service, or 503 if auth hasn't initialized it yet."""
    allowlist = getattr(auth_service, "allowlist", None)
    if allowlist is None:
        raise HTTPException(
            status_code=503, detail="User allowlist service is not available"
        )
    return allowlist


def _validate_allowlist_rule_or_400(request: "BlacklistRuleRequest") -> str:
    """Validate a submitted allowlist rule and return its normalized pattern."""
    if request.entry_type not in ENTRY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"entry_type must be one of: {', '.join(ENTRY_TYPES)}",
        )
    try:
        # A wildcard-only pattern is rejected here as it is for the blacklist.
        # "Clear everyone" is a mode, not a rule: set access_control to 'open'.
        return normalize_pattern(request.pattern)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _guard_own_clearance(
    allowlist, current_user: dict[str, Any], rules: list[dict[str, Any]]
) -> None:
    """Refuse a mutation that would revoke the caller's own clearance.

    Only bites when the caller is themselves an external identity: a local
    password administrator is never gated by the allowlist, so no rule change
    can lock them out. Without this, an external admin could delete the rule
    that admits them and lose the panel they'd need to re-add it.
    """
    if await allowlist.clears_under(rules, current_user):
        return
    raise HTTPException(
        status_code=400,
        detail=(
            "This change would revoke your own access. Add a rule covering your "
            "identity first, or make the change from a local admin account."
        ),
    )


async def _revoke_uncleared(allowlist, rules: list[dict[str, Any]]) -> dict[str, int]:
    """Revoke sessions of external users the given rule set no longer clears."""
    uncleared = await allowlist.find_uncleared_users(rules)
    return {
        "matched_users": len(uncleared),
        "revoked_sessions": await allowlist.revoke_sessions_for(uncleared),
    }


@auth_router.get(
    "/allowlist",
    response_model=list[BlacklistRuleResponse],
    dependencies=[Depends(require_permission("users.manage"))],
)
async def list_allowlist_rules(auth_service=Depends(get_auth_service)):
    """List every allowlist rule, newest first (users.manage permission required)."""
    allowlist = _require_allowlist(auth_service)
    try:
        return [_serialize_rule(rule) for rule in await allowlist.list_rules()]
    except Exception as e:
        logger.error(f"Error listing allowlist rules: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.post(
    "/allowlist",
    response_model=BlacklistRuleResponse,
    dependencies=[Depends(require_permission("users.manage"))],
)
async def create_allowlist_rule(
    request: BlacklistRuleRequest,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Pre-clear an identity pattern for external login.

    Adding a rule only ever grants access, so nothing is revoked and no
    self-lockout guard applies. Matching identities are provisioned on their
    next login; existing users become able to authenticate again within the
    rule cache's TTL.
    """
    allowlist = _require_allowlist(auth_service)
    normalized = _validate_allowlist_rule_or_400(request)

    try:
        rule = await allowlist.add_rule(
            pattern=normalized,
            entry_type=request.entry_type,
            reason=request.reason,
            created_by=current_user.get("username"),
        )
        # add_rule reports who the pattern matches, which for a deny rule means
        # who was cut off. Here it means who was granted, and nothing is
        # revoked - drop the counts rather than report a misleading zero/one.
        rule.pop("revoked_sessions", None)
        rule.pop("matched_users", None)
        _publish_rule_audit_context(http_request, rule)
        return _serialize_rule(rule)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating allowlist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.put(
    "/allowlist/{rule_id}",
    response_model=BlacklistRuleResponse,
    dependencies=[Depends(require_permission("users.manage"))],
)
async def update_allowlist_rule(
    rule_id: str,
    request: BlacklistRuleRequest,
    http_request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Edit an allowlist rule, revoking sessions it no longer covers.

    Narrowing a rule denies whoever it stops matching, so this is guarded
    against revoking the caller's own clearance and reports the sessions it cut.
    """
    allowlist = _require_allowlist(auth_service)
    normalized = _validate_allowlist_rule_or_400(request)

    try:
        current = await allowlist.get_rule(rule_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Allowlist rule not found")

        # Evaluate the post-edit rule set before writing it.
        prospective = await allowlist.rules_excluding(rule_id)
        prospective.append(
            {**current, "pattern": normalized, "entry_type": request.entry_type}
        )
        await _guard_own_clearance(allowlist, current_user, prospective)

        rule = await allowlist.update_rule(
            rule_id=rule_id,
            pattern=normalized,
            entry_type=request.entry_type,
            reason=request.reason,
        )
        if rule is None:
            raise HTTPException(status_code=404, detail="Allowlist rule not found")

        rule.update(await _revoke_uncleared(allowlist, await allowlist.list_rules()))
        _publish_rule_audit_context(http_request, rule)
        return _serialize_rule(rule)
    except BlacklistRuleError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating allowlist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.delete(
    "/allowlist/{rule_id}",
    dependencies=[Depends(require_permission("users.manage"))],
)
async def delete_allowlist_rule(
    rule_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Remove an allowlist rule and revoke the sessions it was clearing.

    Unlike deleting a blacklist rule (which restores access), this *withdraws*
    access, so it revokes live sessions the same way adding a blacklist rule
    does - otherwise a de-approved user keeps working until token expiry.
    """
    allowlist = _require_allowlist(auth_service)
    try:
        prospective = await allowlist.rules_excluding(rule_id)
        await _guard_own_clearance(allowlist, current_user, prospective)

        if not await allowlist.delete_rule(rule_id):
            raise HTTPException(status_code=404, detail="Allowlist rule not found")

        revocation = await _revoke_uncleared(allowlist, prospective)
        return {"status": "deleted", "id": rule_id, **revocation}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting allowlist rule: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _serialize_session(session: dict[str, Any]) -> SessionResponse:
    def _iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    return SessionResponse(
        id=session["id"],
        ip_address=session.get("ip_address"),
        user_agent=session.get("user_agent"),
        created_at=_iso(session.get("created_at")),
        last_seen_at=_iso(session.get("last_seen_at")),
        expires=_iso(session.get("expires")),
    )


@auth_router.get("/sessions", response_model=list[SessionResponse])
async def list_my_sessions(
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """List the caller's own active sessions. No special permission required,
    the same way ``GET /auth/me`` needs none - a user can always see their
    own sessions."""
    # get_current_user returns None (rather than raising) when a request has
    # no bearer credential at all, since several routes treat authentication
    # as optional. This route does not - mirror /auth/me's explicit guard.
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        sessions = await auth_service.list_sessions(current_user["id"])
        return [_serialize_session(session) for session in sessions]
    except Exception as e:
        logger.error(f"Error listing sessions: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.delete("/sessions/{session_id}")
async def revoke_my_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Revoke one of the caller's own sessions (e.g. sign out another device)."""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        revoked = await auth_service.revoke_session(session_id, current_user)
        if not revoked:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "revoked", "id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.get(
    "/users/{user_id}/sessions",
    response_model=list[SessionResponse],
    dependencies=[Depends(require_permission("sessions.manage"))],
)
async def list_user_sessions(user_id: str, auth_service=Depends(get_auth_service)):
    """List another user's active sessions (sessions.manage permission required)."""
    try:
        sessions = await auth_service.list_sessions(user_id)
        return [_serialize_session(session) for session in sessions]
    except Exception as e:
        logger.error(f"Error listing sessions for user {user_id}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@auth_router.delete(
    "/users/{user_id}/sessions/{session_id}",
    dependencies=[Depends(require_permission("sessions.manage"))],
)
async def revoke_user_session(
    user_id: str,
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    auth_service=Depends(get_auth_service),
):
    """Revoke another user's session (sessions.manage permission required)."""
    try:
        # Confirm session_id actually belongs to user_id before revoking, so
        # this route can't be used to revoke an unrelated user's session by
        # guessing/enumerating a session id.
        sessions = await auth_service.list_sessions(user_id)
        if not any(session["id"] == session_id for session in sessions):
            raise HTTPException(status_code=404, detail="Session not found")

        revoked = await auth_service.revoke_session(session_id, current_user)
        if not revoked:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "revoked", "id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking session {session_id} for user {user_id}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
