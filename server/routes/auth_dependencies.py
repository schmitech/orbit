"""
Authentication Dependencies
==========================

FastAPI dependencies for authentication and authorization.
These dependencies are used to protect routes and extract user information.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Header, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config.config_manager import _is_true_value

logger = logging.getLogger(__name__)

# Create a bearer token security scheme
bearer_scheme = HTTPBearer(auto_error=False)


async def get_auth_service(request: Request):
    """Get the authentication service from app state"""
    # Check if authentication is disabled in configuration
    auth_enabled = _is_true_value(request.app.state.config.get('auth', {}).get('enabled', False))
    
    if not auth_enabled:
        logger.info("Authentication service disabled in configuration")
        return None
    
    if not hasattr(request.app.state, 'auth_service') or request.app.state.auth_service is None:
        raise HTTPException(status_code=503, detail="Authentication service not available")
    return request.app.state.auth_service


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    auth_service = Depends(get_auth_service)
) -> Optional[Dict[str, Any]]:
    """
    Get the current authenticated user from bearer token.
    
    This dependency extracts the bearer token from the Authorization header
    and validates it using the authentication service.
    
    Args:
        request: The FastAPI request object
        credentials: The bearer token credentials
        auth_service: The authentication service (None if auth is disabled)
        
    Returns:
        User info dict if authenticated, None otherwise
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    # If auth service is None (auth disabled), return None
    if auth_service is None:
        return None
    
    if not credentials or not credentials.credentials:
        return None
    
    token = credentials.credentials
    
    # Validate token
    is_valid, user_info = await auth_service.validate_token(token)
    
    if not is_valid:
        # Token is invalid or expired
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user_info


async def get_current_user_with_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    auth_service = Depends(get_auth_service)
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Get the current authenticated user and their token.
    
    This dependency is useful for operations that need both user info and token
    (like logout).
    
    Args:
        request: The FastAPI request object
        credentials: The bearer token credentials
        auth_service: The authentication service (None if auth is disabled)
        
    Returns:
        Tuple of (user_info, token) if authenticated, (None, None) otherwise
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    # If auth service is None (auth disabled), return None, None
    if auth_service is None:
        return None, None
    
    if not credentials or not credentials.credentials:
        return None, None
    
    token = credentials.credentials
    
    # Validate token
    is_valid, user_info = await auth_service.validate_token(token)
    
    if not is_valid:
        # Token is invalid or expired
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return user_info, token


async def require_admin(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Require an authenticated admin user.
    
    This dependency ensures that the current user is authenticated
    and has admin role.
    
    Args:
        current_user: The current user info from get_current_user
        
    Returns:
        The admin user info
        
    Raises:
        HTTPException: If not authenticated or not an admin
    """
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if current_user.get('role') != 'admin':
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    
    return current_user


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    auth_service = Depends(get_auth_service)
) -> Optional[Dict[str, Any]]:
    """
    Get the current user if authenticated, but don't require it.
    
    This dependency is useful for endpoints that have different behavior
    for authenticated vs anonymous users.
    
    Args:
        request: The FastAPI request object
        credentials: The bearer token credentials
        auth_service: The authentication service (None if auth is disabled)
        
    Returns:
        User info dict if authenticated, None otherwise
    """
    # If auth service is None (auth disabled), return None
    if auth_service is None:
        return None
    
    if not credentials or not credentials.credentials:
        return None
    
    token = credentials.credentials
    
    # Validate token
    is_valid, user_info = await auth_service.validate_token(token)
    
    # Return user info if valid, None otherwise
    return user_info if is_valid else None


# For backward compatibility with API key authentication
async def check_admin_or_api_key(
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> bool:
    """
    Check if the request has either admin authentication or a valid API key.
    
    This allows existing API key functionality to continue working
    while also supporting the new admin authentication.
    
    IMPORTANT: When authentication is disabled in configuration, this function
    allows access without any authentication requirements.
    
    Args:
        request: The FastAPI request object
        current_user: The current user if authenticated
        x_api_key: The API key from header
        
    Returns:
        True if authorized, raises exception otherwise
        
    Raises:
        HTTPException: If neither admin auth nor valid API key (only when auth is enabled)
    """
    # Check if authentication is disabled in configuration
    auth_enabled = _is_true_value(request.app.state.config.get('auth', {}).get('enabled', False))
    
    # If authentication is disabled, allow access without any requirements
    if not auth_enabled:
        logger.info("Authentication disabled - allowing admin access without authentication")
        return True
    
    # If we have an admin user, allow access
    if current_user and current_user.get('role') == 'admin':
        return True
    
    # Otherwise, check API key using existing service
    if hasattr(request.app.state, 'api_key_service') and x_api_key:
        api_key_service = request.app.state.api_key_service
        is_valid, _, _ = await api_key_service.validate_api_key(x_api_key)
        if is_valid:
            return True
    
    # Neither admin auth nor valid API key
    raise HTTPException(
        status_code=401,
        detail="Admin authentication or valid API key required"
    ) 