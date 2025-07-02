"""Base API client for ORBIT CLI."""

import time
from typing import Dict, Optional, Any, Union
from urllib.parse import urljoin
import requests

from ..core.exceptions import NetworkError, AuthenticationError
from ..utils.logging import get_logger
from ..utils.security import TokenManager

logger = get_logger(__name__)


class BaseAPIClient:
    """Base class for API clients with common functionality."""
    
    def __init__(
        self,
        server_url: str,
        token: Optional[str] = None,
        timeout: int = 30,
        retry_attempts: int = 3,
        verify_ssl: bool = True
    ):
        """
        Initialize the base API client.
        
        Args:
            server_url: Base URL of the API server
            token: Optional authentication token
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for failed requests
            verify_ssl: Whether to verify SSL certificates
        """
        self.server_url = server_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.verify_ssl = verify_ssl
        self._session = None
    
    @property
    def session(self) -> requests.Session:
        """Get or create a requests session with connection pooling."""
        if self._session is None:
            self._session = requests.Session()
            
            # Configure connection pooling
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10,
                pool_maxsize=10,
                max_retries=0  # We handle retries ourselves
            )
            self._session.mount('http://', adapter)
            self._session.mount('https://', adapter)
            
            # Set default headers
            self._session.headers.update({
                'User-Agent': 'ORBIT-CLI',
                'Accept': 'application/json',
            })
        
        return self._session
    
    def _build_url(self, endpoint: str) -> str:
        """
        Build full URL for an endpoint.
        
        Args:
            endpoint: API endpoint path
            
        Returns:
            Full URL
        """
        # Ensure endpoint starts with /
        if not endpoint.startswith('/'):
            endpoint = f'/{endpoint}'
        return urljoin(self.server_url, endpoint)
    
    def _get_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Get request headers with authentication.
        
        Args:
            additional_headers: Additional headers to include
            
        Returns:
            Headers dictionary
        """
        headers = {}
        
        # Add authentication header if we have a token
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        # Add any additional headers
        if additional_headers:
            headers.update(additional_headers)
        
        return headers
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        retry: bool = True
    ) -> requests.Response:
        """
        Make an HTTP request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            headers: Optional request headers
            params: Optional query parameters
            json_data: Optional JSON data for request body
            data: Optional form data for request body
            retry: Whether to retry on failure
            
        Returns:
            Response object
            
        Raises:
            NetworkError: On network failures
        """
        url = self._build_url(endpoint)
        headers = self._get_headers(headers)
        attempts = self.retry_attempts if retry else 1
        
        for attempt in range(attempts):
            try:
                logger.debug(f"{method} {url} (attempt {attempt + 1}/{attempts})")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    data=data,
                    timeout=self.timeout,
                    verify=self.verify_ssl
                )
                
                # Log response status
                logger.debug(f"Response: {response.status_code}")
                
                return response
                
            except requests.exceptions.ConnectionError as e:
                if attempt < attempts - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.debug(
                        f"Connection error (attempt {attempt + 1}/{attempts}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    raise NetworkError(f"Failed to connect to server at {self.server_url}")
                    
            except requests.exceptions.Timeout:
                if attempt < attempts - 1:
                    logger.debug(
                        f"Request timeout (attempt {attempt + 1}/{attempts}). Retrying..."
                    )
                    time.sleep(2 ** attempt)
                else:
                    raise NetworkError(f"Request timed out after {self.timeout} seconds")
                    
            except requests.exceptions.RequestException as e:
                raise NetworkError(f"Request failed: {str(e)}")
                
            except Exception as e:
                raise NetworkError(f"Unexpected error: {str(e)}")
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> requests.Response:
        """Make a GET request."""
        return self._make_request('GET', endpoint, params=params, **kwargs)
    
    def post(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> requests.Response:
        """Make a POST request."""
        return self._make_request('POST', endpoint, json_data=json_data, data=data, **kwargs)
    
    def put(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> requests.Response:
        """Make a PUT request."""
        return self._make_request('PUT', endpoint, json_data=json_data, data=data, **kwargs)
    
    def patch(
        self,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> requests.Response:
        """Make a PATCH request."""
        return self._make_request('PATCH', endpoint, json_data=json_data, data=data, **kwargs)
    
    def delete(
        self,
        endpoint: str,
        **kwargs
    ) -> requests.Response:
        """Make a DELETE request."""
        return self._make_request('DELETE', endpoint, **kwargs)
    
    def close(self) -> None:
        """Close the session and clean up resources."""
        if self._session:
            self._session.close()
            self._session = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


class AuthenticatedAPIClient(BaseAPIClient):
    """API client with authentication token management."""
    
    def __init__(
        self,
        server_url: str,
        token: Optional[str] = None,
        storage_method: str = "auto",
        **kwargs
    ):
        """
        Initialize authenticated API client.
        
        Args:
            server_url: Base URL of the API server
            token: Optional authentication token
            storage_method: Token storage method ("keyring", "file", or "auto")
            **kwargs: Additional arguments for BaseAPIClient
        """
        super().__init__(server_url, token, **kwargs)
        self.token_manager = TokenManager(storage_method)
        
        # Load token if not provided
        if not self.token:
            self.load_token()
    
    def load_token(self, suppress_legacy_warning: bool = False) -> Optional[str]:
        """
        Load authentication token from storage.
        
        Args:
            suppress_legacy_warning: Whether to suppress legacy storage warnings
            
        Returns:
            Loaded token or None
        """
        result = self.token_manager.load_token(suppress_legacy_warning)
        if result:
            self.token, stored_url = result
            # Update server URL if not explicitly set
            if stored_url and self.server_url == "http://localhost:3000":
                self.server_url = stored_url
        return self.token
    
    def save_token(self, token: str) -> None:
        """
        Save authentication token to storage.
        
        Args:
            token: Authentication token to save
        """
        self.token = token
        self.token_manager.save_token(token, self.server_url)
    
    def clear_token(self) -> None:
        """Clear authentication token from storage."""
        self.token = None
        self.token_manager.clear_token()
    
    def ensure_authenticated(self) -> None:
        """
        Ensure the client has a valid authentication token.
        
        Raises:
            AuthenticationError: If not authenticated
        """
        if not self.token:
            raise AuthenticationError(
                "Authentication required. Please run 'orbit login' first."
            )