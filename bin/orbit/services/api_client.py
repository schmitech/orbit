"""
HTTP client for ORBIT server API.

This module provides a clean HTTP client interface with retry logic
and error handling. It does not handle authentication - that's done
by the auth service.
"""

import time
import logging
from typing import Any, Dict, Optional
import requests

from bin.orbit.utils.exceptions import NetworkError, OrbitError, AuthenticationError

logger = logging.getLogger(__name__)


def handle_api_errors(operation_name: str = None, custom_errors: Dict[int, str] = None):
    """
    Decorator to centralize HTTP error handling for API methods.
    
    Args:
        operation_name: Optional name of the operation for better error messages
        custom_errors: Optional dict mapping status codes to custom error messages
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                
                # Check for custom error messages first
                if custom_errors and status_code in custom_errors:
                    if status_code in [401, 403]:
                        raise AuthenticationError(custom_errors[status_code])
                    else:
                        raise OrbitError(custom_errors[status_code])
                
                # Default error handling based on status codes
                if status_code == 401:
                    raise AuthenticationError("Authentication failed. Your token may be invalid or expired.")
                elif status_code == 403:
                    raise AuthenticationError("Permission denied. Admin privileges may be required.")
                elif status_code == 404:
                    operation = operation_name or "Resource"
                    raise OrbitError(f"{operation} not found.")
                elif status_code == 409:
                    raise OrbitError("Resource already exists or conflict detected.")
                elif status_code == 400:
                    try:
                        error_detail = e.response.json().get('detail', 'Bad request')
                    except Exception:
                        error_detail = 'Bad request'
                    raise OrbitError(f"Bad request: {error_detail}")
                else:
                    operation = operation_name or "Operation"
                    raise OrbitError(f"{operation} failed: {status_code} {e.response.text}")
            except NetworkError:
                # Re-raise network errors as-is
                raise
            except Exception as e:
                # Handle unexpected errors
                operation = operation_name or "Operation"
                raise OrbitError(f"{operation} failed: {str(e)}")
        return wrapper
    return decorator


class ApiClient:
    """
    HTTP client for ORBIT server API.
    
    This class provides a clean interface for making HTTP requests to the
    ORBIT server with retry logic and error handling. It does not handle
    authentication - tokens should be provided in headers by callers.
    """
    
    def __init__(self, server_url: str, timeout: int = 30, retry_attempts: int = 3):
        """
        Initialize the API client.
        
        Args:
            server_url: Base URL of the ORBIT server
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for failed requests
        """
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.retry_attempts = retry_attempts
    
    def request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        retry: bool = True
    ) -> requests.Response:
        """
        Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path (e.g., "/admin/api-keys")
            headers: Request headers
            json_data: JSON data for POST/PUT requests
            params: Query parameters
            retry: Whether to retry on failure
            
        Returns:
            Response object
            
        Raises:
            NetworkError: On network failures
        """
        headers = headers or {}
        url = f"{self.server_url}{endpoint}"
        attempts = self.retry_attempts if retry else 1
        
        for attempt in range(attempts):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json_data,
                    params=params,
                    timeout=self.timeout
                )
                return response
            except requests.exceptions.ConnectionError as e:
                if attempt < attempts - 1:
                    logger.debug(f"Connection error (attempt {attempt + 1}/{attempts}): {e}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise NetworkError(f"Failed to connect to server at {self.server_url}")
            except requests.exceptions.Timeout:
                if attempt < attempts - 1:
                    logger.debug(f"Request timeout (attempt {attempt + 1}/{attempts})")
                    time.sleep(2 ** attempt)
                else:
                    raise NetworkError(f"Request timed out after {self.timeout} seconds")
            except Exception as e:
                raise NetworkError(f"Unexpected error: {e}")
    
    def get(self, endpoint: str, headers: Optional[Dict[str, str]] = None,
            params: Optional[Dict[str, Any]] = None, retry: bool = True) -> requests.Response:
        """Make a GET request."""
        return self.request("GET", endpoint, headers=headers, params=params, retry=retry)
    
    def post(self, endpoint: str, headers: Optional[Dict[str, str]] = None,
             json_data: Optional[Dict[str, Any]] = None,
             params: Optional[Dict[str, Any]] = None, retry: bool = True) -> requests.Response:
        """Make a POST request."""
        return self.request("POST", endpoint, headers=headers, json_data=json_data, params=params, retry=retry)
    
    def put(self, endpoint: str, headers: Optional[Dict[str, str]] = None,
            json_data: Optional[Dict[str, Any]] = None, retry: bool = True) -> requests.Response:
        """Make a PUT request."""
        return self.request("PUT", endpoint, headers=headers, json_data=json_data, retry=retry)
    
    def patch(self, endpoint: str, headers: Optional[Dict[str, str]] = None,
              json_data: Optional[Dict[str, Any]] = None,
              params: Optional[Dict[str, Any]] = None, retry: bool = True) -> requests.Response:
        """Make a PATCH request."""
        return self.request("PATCH", endpoint, headers=headers, json_data=json_data, params=params, retry=retry)
    
    def delete(self, endpoint: str, headers: Optional[Dict[str, str]] = None, retry: bool = True) -> requests.Response:
        """Make a DELETE request."""
        return self.request("DELETE", endpoint, headers=headers, retry=retry)
    
    def read_file_content(self, file_path: str) -> str:
        """
        Read content from a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content of the file as a string
            
        Raises:
            OrbitError: If file cannot be read
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            raise OrbitError(f"File not found: {file_path}")
        except Exception as e:
            raise OrbitError(f"Error reading file {file_path}: {str(e)}")

