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
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from routes.auth_dependencies import get_auth_service, get_current_user, get_current_user_with_token, require_admin

logger = logging.getLogger(__name__)

# Create the auth router
auth_router = APIRouter(prefix="/auth", tags=["authentication"])


# Request/Response Models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: Dict[str, Any]


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class RegisterResponse(BaseModel):
    id: str
    username: str
    role: str


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    active: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class UserByUsernameResponse(BaseModel):
    id: str
    username: str
    role: str
    active: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    user_id: str
    new_password: str


class DeactivateUserRequest(BaseModel):
    user_id: str


# Authentication Endpoints
@auth_router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
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
        logger.info(f"Login attempt for user: {request.username}")
        
        success, token, user_info = await auth_service.authenticate_user(
            request.username, 
            request.password
        )
        
        logger.info(f"Authentication result: success={success}")
        
        if not success:
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
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during login: {str(e)}"
        )


@auth_router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_user),
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
            active=user["active"],
            created_at=created_at,
            last_login=last_login
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error getting current user info: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while getting user info: {str(e)}"
        )

@auth_router.get("/users", response_model=List[UserResponse])
async def list_users(
    role: Optional[str] = None,
    active_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    admin_user = Depends(require_admin),
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
                active=user["active"],
                created_at=created_at,
                last_login=last_login
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing users: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while listing users: {str(e)}"
        )

@auth_router.get("/users/by-username", response_model=UserByUsernameResponse)
async def get_user_by_username(
    username: str,
    admin_user = Depends(require_admin),
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
            active=user["active"]
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error getting user by username: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while getting user by username: {str(e)}"
        )

@auth_router.post("/register", response_model=RegisterResponse)
async def register_user(
    request: RegisterRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can create new users"
        )
    
    try:
        user_id = await auth_service.create_user(
            request.username,
            request.password,
            request.role
        )
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="Failed to create user. Username may already exist."
            )
        
        return RegisterResponse(
            id=user_id,
            username=request.username,
            role=request.role
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
    user_and_token: tuple[Dict[str, Any], str] = Depends(get_current_user_with_token),
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
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can delete users"
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


@auth_router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can reset user passwords"
        )
    
    # Prevent admin from resetting their own password this way
    if current_user.get("id") == request.user_id:
        raise HTTPException(
            status_code=400,
            detail="Use change-password to change your own password"
        )
    
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
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can deactivate users"
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
    current_user: Dict[str, Any] = Depends(get_current_user),
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
    # Check if current user is admin
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can activate users"
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