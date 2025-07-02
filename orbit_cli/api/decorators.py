"""Decorators for API error handling and retry logic."""

import time
import functools
from typing import Dict, Optional, Callable, Any
import requests

from ..core.exceptions import (
    OrbitError,
    AuthenticationError,
    NetworkError,
    ValidationError
)
from ..utils.logging import get_logger

logger = get_logger(__name__)


def handle_api_errors(
    operation_name: Optional[str] = None,
    custom_errors: Optional[Dict[int, str]] = None
):
    """
    Decorator to centralize HTTP error handling for API methods.
    
    Args:
        operation_name: Optional name of the operation for better error messages
        custom_errors: Optional dict mapping status codes to custom error messages
        
    Example:
        @handle_api_errors(operation_name="Create user")
        def create_user(self, username: str) -> Dict[str, Any]:
            ...
            
        @handle_api_errors(
            operation_name="Delete resource",
            custom_errors={
                404: "Resource not found",
                409: "Resource is in use and cannot be deleted"
            }
        )
        def delete_resource(self, resource_id: str) -> None:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                operation = operation_name or func.__name__.replace('_', ' ').title()
                
                # Log the error
                logger.debug(
                    f"{operation} failed with status {status_code}: {e.response.text}"
                )
                
                # Check for custom error messages first
                if custom_errors and status_code in custom_errors:
                    error_msg = custom_errors[status_code]
                    if status_code in [401, 403]:
                        raise AuthenticationError(error_msg)
                    else:
                        raise OrbitError(error_msg)
                
                # Default error handling based on status codes
                if status_code == 401:
                    raise AuthenticationError(
                        "Authentication failed. Your token may be invalid or expired."
                    )
                elif status_code == 403:
                    raise AuthenticationError(
                        "Permission denied. Admin privileges may be required."
                    )
                elif status_code == 404:
                    raise OrbitError(f"{operation} failed: Resource not found.")
                elif status_code == 409:
                    raise OrbitError(
                        f"{operation} failed: Resource already exists or conflict detected."
                    )
                elif status_code == 400:
                    try:
                        error_detail = e.response.json().get('detail', 'Bad request')
                    except:
                        error_detail = 'Bad request'
                    raise ValidationError(f"{operation} failed: {error_detail}")
                elif status_code == 422:
                    try:
                        error_detail = e.response.json().get('detail', 'Validation error')
                    except:
                        error_detail = 'Validation error'
                    raise ValidationError(f"{operation} failed: {error_detail}")
                elif status_code >= 500:
                    raise OrbitError(
                        f"{operation} failed: Server error ({status_code}). "
                        "Please try again later."
                    )
                else:
                    raise OrbitError(
                        f"{operation} failed: HTTP {status_code} - {e.response.text}"
                    )
            except NetworkError:
                # Re-raise network errors as-is
                raise
            except OrbitError:
                # Re-raise our custom errors
                raise
            except Exception as e:
                # Handle unexpected errors
                operation = operation_name or func.__name__.replace('_', ' ').title()
                logger.error(f"Unexpected error in {operation}: {e}", exc_info=True)
                raise OrbitError(f"{operation} failed: {str(e)}")
        
        return wrapper
    return decorator


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: str = "exponential",
    retry_on: Optional[tuple] = None
):
    """
    Decorator to add retry logic to API methods.
    
    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff strategy ("exponential" or "linear")
        retry_on: Tuple of exception types to retry on (default: NetworkError, requests.ConnectionError)
        
    Example:
        @retry_on_failure(max_attempts=5, delay=2.0)
        def make_api_call(self) -> Dict[str, Any]:
            ...
    """
    if retry_on is None:
        retry_on = (NetworkError, requests.exceptions.ConnectionError, requests.exceptions.Timeout)
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        # Calculate delay
                        if backoff == "exponential":
                            wait_time = delay * (2 ** attempt)
                        else:  # linear
                            wait_time = delay * (attempt + 1)
                        
                        logger.debug(
                            f"Retry {attempt + 1}/{max_attempts} for {func.__name__} "
                            f"after {wait_time}s delay. Error: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        # Last attempt failed
                        logger.debug(
                            f"All {max_attempts} attempts failed for {func.__name__}"
                        )
            
            # If we get here, all attempts failed
            if last_exception:
                raise last_exception
            else:
                raise OrbitError(f"Failed after {max_attempts} attempts")
        
        return wrapper
    return decorator


def require_auth(func: Callable) -> Callable:
    """
    Decorator to ensure the user is authenticated before making API calls.
    
    Example:
        @require_auth
        def get_user_profile(self) -> Dict[str, Any]:
            ...
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, 'token') or not self.token:
            raise AuthenticationError(
                "Authentication required. Please run 'orbit login' first."
            )
        return func(self, *args, **kwargs)
    
    return wrapper


def validate_response(
    expected_fields: Optional[list] = None,
    expected_status: Optional[int] = None
):
    """
    Decorator to validate API response structure.
    
    Args:
        expected_fields: List of fields that must be present in the response
        expected_status: Expected HTTP status code
        
    Example:
        @validate_response(expected_fields=['id', 'username'], expected_status=201)
        def create_user(self, username: str) -> Dict[str, Any]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # If result is a Response object, extract JSON
            if hasattr(result, 'json'):
                try:
                    data = result.json()
                except:
                    raise ValidationError("Invalid JSON response from server")
                    
                # Check status code if specified
                if expected_status and result.status_code != expected_status:
                    raise ValidationError(
                        f"Unexpected status code: {result.status_code} "
                        f"(expected {expected_status})"
                    )
            else:
                data = result
            
            # Validate expected fields
            if expected_fields and isinstance(data, dict):
                missing_fields = [
                    field for field in expected_fields 
                    if field not in data
                ]
                if missing_fields:
                    raise ValidationError(
                        f"Missing required fields in response: {', '.join(missing_fields)}"
                    )
            
            return data
        
        return wrapper
    return decorator


def paginated(
    page_size: int = 100,
    max_pages: Optional[int] = None
):
    """
    Decorator to handle paginated API responses.
    
    Args:
        page_size: Number of items per page
        max_pages: Maximum number of pages to fetch (None = all)
        
    Example:
        @paginated(page_size=50)
        def list_all_users(self) -> List[Dict[str, Any]]:
            # Implementation should yield pages
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            all_items = []
            page = 0
            
            while True:
                # Add pagination parameters
                kwargs['limit'] = page_size
                kwargs['offset'] = page * page_size
                
                # Get page of results
                page_results = func(*args, **kwargs)
                
                if not page_results:
                    break
                
                all_items.extend(page_results)
                page += 1
                
                # Check if we've hit the page limit
                if max_pages and page >= max_pages:
                    break
                
                # Check if we got fewer items than page_size (last page)
                if len(page_results) < page_size:
                    break
            
            return all_items
        
        return wrapper
    return decorator


def rate_limited(
    calls_per_second: float = 10.0
):
    """
    Decorator to add rate limiting to API methods.
    
    Args:
        calls_per_second: Maximum number of calls per second
        
    Example:
        @rate_limited(calls_per_second=5.0)
        def make_api_call(self) -> Dict[str, Any]:
            ...
    """
    min_interval = 1.0 / calls_per_second
    last_called = {}
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Use function name and first arg (usually self) as key
            key = (func.__name__, id(args[0]) if args else None)
            
            # Check if we need to wait
            if key in last_called:
                elapsed = time.time() - last_called[key]
                if elapsed < min_interval:
                    sleep_time = min_interval - elapsed
                    logger.debug(f"Rate limiting: sleeping for {sleep_time:.3f}s")
                    time.sleep(sleep_time)
            
            # Update last called time
            last_called[key] = time.time()
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator