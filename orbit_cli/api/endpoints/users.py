"""User management API endpoints."""

from typing import Dict, Any, List, Optional

from ..base_client import AuthenticatedAPIClient
from ..decorators import handle_api_errors, require_auth, paginated
from ...core.exceptions import OrbitError


class UsersAPI(AuthenticatedAPIClient):
    """Handles user management API operations."""
    
    @require_auth
    @handle_api_errors(
        operation_name="List users",
        custom_errors={
            403: "Admin privileges required to list users",
            404: "User management endpoint not found. Check if the server is running and authentication is enabled"
        }
    )
    def list_users(
        self,
        role: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all users in the system with optional server-side filtering.
        
        Args:
            role: Optional role filter (user, admin)
            active_only: If True, only return active users
            limit: Maximum number of users to return (default: 100, max: 1000)
            offset: Number of users to skip for pagination (default: 0)
            
        Returns:
            List of dictionaries containing user information
        """
        params = {
            'limit': str(min(limit, 1000)),
            'offset': str(offset)
        }
        
        if role:
            params['role'] = role
        if active_only:
            params['active_only'] = 'true'
        
        response = self.get("/auth/users", params=params)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @paginated(page_size=100)
    def list_all_users(
        self,
        role: Optional[str] = None,
        active_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all users with automatic pagination.
        
        This method will automatically fetch all pages of results.
        
        Args:
            role: Optional role filter (user, admin)
            active_only: If True, only return active users
            limit: Used internally by paginated decorator
            offset: Used internally by paginated decorator
            
        Returns:
            Complete list of all users
        """
        return self.list_users(role, active_only, limit, offset)
    
    @require_auth
    @handle_api_errors(
        operation_name="Find user by username",
        custom_errors={
            403: "Admin privileges required to find users by username",
            404: "User not found"
        }
    )
    def find_user_by_username(self, username: str) -> Dict[str, Any]:
        """
        Find a user by their username using efficient server-side lookup.
        
        Args:
            username: The username to search for
            
        Returns:
            User information dictionary
            
        Raises:
            OrbitError: If user is not found
        """
        response = self.get("/auth/users/by-username", params={"username": username})
        
        if response.status_code == 404:
            raise OrbitError(f"User with username '{username}' not found")
        
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Get user by ID",
        custom_errors={
            403: "Admin privileges required to view user details",
            404: "User not found"
        }
    )
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific user.
        
        Args:
            user_id: The user ID
            
        Returns:
            User information dictionary
        """
        response = self.get(f"/auth/users/{user_id}")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Delete user",
        custom_errors={
            403: "Admin privileges required to delete users",
            404: "User not found",
            400: "Cannot delete your own account"
        }
    )
    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """
        Delete a user.
        
        Args:
            user_id: The user ID to delete
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.delete(f"/auth/users/{user_id}")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Deactivate user",
        custom_errors={
            403: "Admin privileges required to deactivate users",
            404: "User not found",
            400: "Cannot deactivate your own account"
        }
    )
    def deactivate_user(self, user_id: str) -> Dict[str, Any]:
        """
        Deactivate a user.
        
        Args:
            user_id: The user ID to deactivate
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(f"/auth/users/{user_id}/deactivate")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Activate user",
        custom_errors={
            403: "Admin privileges required to activate users",
            404: "User not found"
        }
    )
    def activate_user(self, user_id: str) -> Dict[str, Any]:
        """
        Activate a previously deactivated user.
        
        Args:
            user_id: The user ID to activate
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(f"/auth/users/{user_id}/activate")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Update user",
        custom_errors={
            403: "Admin privileges required to update users",
            404: "User not found",
            409: "Username already exists"
        }
    )
    def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update user information.
        
        Args:
            user_id: The user ID to update
            username: New username (optional)
            email: New email (optional)
            role: New role (optional)
            
        Returns:
            Updated user information
        """
        data = {}
        if username is not None:
            data["username"] = username
        if email is not None:
            data["email"] = email
        if role is not None:
            data["role"] = role
        
        response = self.patch(f"/auth/users/{user_id}", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(operation_name="Search users")
    def search_users(
        self,
        query: str,
        search_fields: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search for users by query string.
        
        Args:
            query: Search query
            search_fields: Fields to search in (default: username, email)
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of matching users
        """
        params = {
            'q': query,
            'limit': str(min(limit, 1000)),
            'offset': str(offset)
        }
        
        if search_fields:
            params['fields'] = ','.join(search_fields)
        
        response = self.get("/auth/users/search", params=params)
        response.raise_for_status()
        return response.json()