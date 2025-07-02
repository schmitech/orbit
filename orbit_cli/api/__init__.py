"""API client module for ORBIT CLI."""

from .client import ApiManager
from .base_client import BaseAPIClient, AuthenticatedAPIClient
from .decorators import (
    handle_api_errors,
    retry_on_failure,
    require_auth,
    validate_response,
    paginated,
    rate_limited
)

# Import endpoint classes if needed elsewhere
from .endpoints.auth import AuthAPI
from .endpoints.users import UsersAPI
from .endpoints.keys import ApiKeysAPI
from .endpoints.prompts import PromptsAPI

__all__ = [
    # Main client
    'ApiManager',
    
    # Base clients
    'BaseAPIClient',
    'AuthenticatedAPIClient',
    
    # Decorators
    'handle_api_errors',
    'retry_on_failure',
    'require_auth',
    'validate_response',
    'paginated',
    'rate_limited',
    
    # Endpoint classes
    'AuthAPI',
    'UsersAPI',
    'ApiKeysAPI',
    'PromptsAPI'
]