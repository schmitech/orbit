"""Main API client for ORBIT CLI."""

from typing import Optional, Dict, Any
from pathlib import Path

from ..config import ConfigManager
from ..core.exceptions import OrbitError, FileOperationError
from ..utils.logging import get_logger
from .base_client import AuthenticatedAPIClient
from .endpoints.auth import AuthAPI
from .endpoints.users import UsersAPI
from .endpoints.keys import ApiKeysAPI
from .endpoints.prompts import PromptsAPI

logger = get_logger(__name__)


class ApiManager:
    """
    Main API Manager for the ORBIT CLI.
    
    This class provides a unified interface to all API endpoints and handles
    configuration, authentication, and file operations.
    """
    
    def __init__(
        self,
        config_manager: ConfigManager,
        server_url: Optional[str] = None,
        load_token: bool = True
    ):
        """
        Initialize the API Manager.
        
        Args:
            config_manager: Configuration manager instance
            server_url: Optional server URL override
            load_token: Whether to load token on initialization (default: True)
        """
        self.config_manager = config_manager
        
        # Get server configuration
        self.server_url = self._get_server_url(server_url)
        self.timeout = config_manager.get('server.timeout', 30)
        self.retry_attempts = config_manager.get('server.retry_attempts', 3)
        self.verify_ssl = config_manager.get('api.verify_ssl', True)
        
        # Get authentication configuration
        storage_method = config_manager.get('auth.credential_storage', 'auto')
        
        # Initialize API endpoints
        client_kwargs = {
            'server_url': self.server_url,
            'timeout': self.timeout,
            'retry_attempts': self.retry_attempts,
            'verify_ssl': self.verify_ssl,
            'storage_method': storage_method
        }
        
        # Create endpoint instances
        self.auth = AuthAPI(**client_kwargs)
        self.users = UsersAPI(**client_kwargs)
        self.keys = ApiKeysAPI(**client_kwargs)
        self.prompts = PromptsAPI(**client_kwargs)
        
        # Share token across all endpoints
        self._endpoints = [self.auth, self.users, self.keys, self.prompts]
        
        # Load token if requested
        if load_token:
            self.load_token()
    
    def _get_server_url(self, override_url: Optional[str] = None) -> str:
        """Get server URL with proper precedence."""
        if override_url:
            return override_url.rstrip('/')
        
        # Use config manager method
        url = self.config_manager.get('server.default_url')
        if url:
            return url.rstrip('/')
        
        # Final fallback
        return "http://localhost:3000"
    
    @property
    def token(self) -> Optional[str]:
        """Get the current authentication token."""
        return self.auth.token
    
    @token.setter
    def token(self, value: Optional[str]) -> None:
        """Set the authentication token for all endpoints."""
        for endpoint in self._endpoints:
            endpoint.token = value
    
    def load_token(self, suppress_legacy_warning: bool = False) -> Optional[str]:
        """
        Load authentication token from storage.
        
        Args:
            suppress_legacy_warning: Whether to suppress legacy storage warnings
            
        Returns:
            Loaded token or None
        """
        token = self.auth.load_token(suppress_legacy_warning)
        if token:
            # Sync token across all endpoints
            self.token = token
        return token
    
    def save_token(self, token: str) -> None:
        """
        Save authentication token to storage.
        
        Args:
            token: Authentication token to save
        """
        self.auth.save_token(token)
        # Sync token across all endpoints
        self.token = token
    
    def clear_token(self) -> None:
        """Clear authentication token from storage."""
        self.auth.clear_token()
        # Clear token from all endpoints
        self.token = None
    
    def ensure_authenticated(self) -> None:
        """Ensure user is authenticated before proceeding."""
        self.auth.ensure_authenticated()
    
    # Convenience methods that delegate to specific endpoints
    
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate a user and return a bearer token."""
        result = self.auth.login(username, password)
        # Sync token across endpoints after successful login
        if self.auth.token:
            self.token = self.auth.token
        return result
    
    def logout(self) -> Dict[str, Any]:
        """Logout the current user."""
        result = self.auth.logout()
        # Clear token from all endpoints
        self.token = None
        return result
    
    def get_current_user(self) -> Dict[str, Any]:
        """Get information about the current user."""
        return self.auth.get_current_user()
    
    def check_auth_status(self) -> Dict[str, Any]:
        """Check authentication status."""
        return self.auth.check_auth_status()
    
    # File operations utilities
    
    def read_file_content(self, file_path: str) -> str:
        """
        Read content from a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content of the file as a string
            
        Raises:
            FileOperationError: If file cannot be read
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileOperationError(f"File not found: {file_path}")
            
            with open(path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileOperationError:
            raise
        except Exception as e:
            raise FileOperationError(f"Error reading file {file_path}: {str(e)}")
    
    def save_file_content(self, file_path: str, content: str) -> None:
        """
        Save content to a file.
        
        Args:
            file_path: Path to the file
            content: Content to save
            
        Raises:
            FileOperationError: If file cannot be saved
        """
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
        except Exception as e:
            raise FileOperationError(f"Error saving file {file_path}: {str(e)}")
    
    # API key operations with prompt support
    
    def create_api_key_with_prompt(
        self,
        collection_name: str,
        client_name: str,
        notes: Optional[str] = None,
        prompt_id: Optional[str] = None,
        prompt_name: Optional[str] = None,
        prompt_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API key for a client, optionally with an associated system prompt.
        
        Args:
            collection_name: The name of the Chroma collection
            client_name: The name of the client
            notes: Optional notes about this API key
            prompt_id: Optional existing system prompt ID to associate
            prompt_name: Optional name for a new system prompt
            prompt_file: Optional path to a file containing a system prompt
            
        Returns:
            Dictionary containing the created API key details
        """
        # First handle prompt if needed
        if prompt_file and (prompt_name or prompt_id):
            prompt_text = self.read_file_content(prompt_file)
            
            if prompt_id:
                # Update an existing prompt
                prompt_result = self.prompts.update_prompt(prompt_id, prompt=prompt_text)
                prompt_id = prompt_result.get("id") or prompt_id
            elif prompt_name:
                # Create a new prompt
                prompt_result = self.prompts.create_prompt(prompt_name, prompt_text)
                prompt_id = prompt_result.get("id")
                if not prompt_id:
                    raise OrbitError("Failed to get prompt ID from created prompt")
        
        # Create the API key
        api_key_result = self.keys.create_api_key(
            collection_name=collection_name,
            client_name=client_name,
            notes=notes
        )
        
        # Associate prompt if we have one
        if prompt_id:
            api_key = api_key_result.get("api_key")
            if not api_key:
                raise OrbitError("Failed to get API key from creation response")
            
            self.keys.associate_prompt_with_api_key(api_key, prompt_id)
            api_key_result["system_prompt_id"] = prompt_id
        
        return api_key_result
    
    # User management convenience methods
    
    def find_user_id_by_username(self, username: str) -> str:
        """
        Find a user's ID by their username.
        
        Args:
            username: The username to search for
            
        Returns:
            The user ID if found
            
        Raises:
            OrbitError: If user is not found
        """
        user_data = self.users.find_user_by_username(username)
        user_id = user_data.get('id') or user_data.get('_id')
        if not user_id:
            raise OrbitError(f"Could not get ID for user '{username}'")
        return user_id
    
    # Batch operations
    
    def deactivate_api_keys_by_collection(self, collection_name: str) -> int:
        """
        Deactivate all API keys for a specific collection.
        
        Args:
            collection_name: The collection name
            
        Returns:
            Number of keys deactivated
        """
        keys = self.keys.list_all_api_keys(collection=collection_name, active_only=True)
        count = 0
        
        for key_info in keys:
            api_key = key_info.get('api_key')
            if api_key:
                try:
                    self.keys.deactivate_api_key(api_key)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to deactivate key {api_key[:20]}...: {e}")
        
        return count
    
    def delete_prompts_by_tag(self, tag: str) -> int:
        """
        Delete all prompts with a specific tag.
        
        Args:
            tag: The tag to filter by
            
        Returns:
            Number of prompts deleted
        """
        prompts = self.prompts.list_all_prompts(tag_filter=tag)
        count = 0
        
        for prompt_info in prompts:
            prompt_id = prompt_info.get('id') or prompt_info.get('_id')
            if prompt_id:
                try:
                    self.prompts.delete_prompt(prompt_id)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete prompt {prompt_id[:20]}...: {e}")
        
        return count
    
    # Health check
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the server.
        
        Returns:
            Health status information
        """
        try:
            response = self.auth.get("/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    # Context manager support
    
    def close(self) -> None:
        """Close all API client connections."""
        for endpoint in self._endpoints:
            endpoint.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()