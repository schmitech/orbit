"""Authentication API endpoints."""

from typing import Dict, Any, Optional

from ..base_client import AuthenticatedAPIClient
from ..decorators import handle_api_errors, require_auth
from ...core.exceptions import AuthenticationError


class AuthAPI(AuthenticatedAPIClient):
    """Handles authentication-related API operations."""
    
    @handle_api_errors(
        operation_name="Login",
        custom_errors={
            401: "Invalid username or password",
            403: "Access denied"
        }
    )
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate a user and return a bearer token.
        
        Args:
            username: The username
            password: The password
            
        Returns:
            Dictionary containing the login response with token and user info
        """
        response = self.post(
            "/auth/login",
            json_data={
                "username": username,
                "password": password
            }
        )
        response.raise_for_status()
        result = response.json()
        
        # Update and save the token if login successful
        if "token" in result:
            self.save_token(result["token"])
        
        return result
    
    @handle_api_errors(operation_name="Logout")
    def logout(self) -> Dict[str, Any]:
        """
        Logout the current user by invalidating their token.
        
        Returns:
            Dictionary containing the logout response
        """
        if not self.token:
            return {"message": "Not logged in"}
        
        try:
            response = self.post("/auth/logout")
            response.raise_for_status()
            result = response.json()
        except Exception as e:
            # Clear token anyway even if server logout fails
            result = {"message": "Logged out locally"}
        
        # Clear the token regardless of server response
        self.clear_token()
        
        return result
    
    @require_auth
    @handle_api_errors(
        operation_name="User registration",
        custom_errors={
            403: "Admin privileges required to register users",
            409: "User already exists"
        }
    )
    def register_user(
        self,
        username: str,
        password: str,
        role: str = "user",
        email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new user (admin only).
        
        Args:
            username: The username for the new user
            password: The password for the new user
            role: The role for the new user (default: "user")
            email: Optional email address
            
        Returns:
            Dictionary containing the registration response
        """
        data = {
            "username": username,
            "password": password,
            "role": role
        }
        if email:
            data["email"] = email
        
        response = self.post("/auth/register", json_data=data)
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Get current user",
        custom_errors={
            401: "Invalid or expired token"
        }
    )
    def get_current_user(self) -> Dict[str, Any]:
        """
        Get information about the currently authenticated user.
        
        Returns:
            Dictionary containing the current user information
        """
        response = self.get("/auth/me")
        response.raise_for_status()
        return response.json()
    
    @require_auth
    @handle_api_errors(
        operation_name="Change password",
        custom_errors={
            400: "Current password is incorrect",
            401: "Authentication required"
        }
    )
    def change_password(self, current_password: str, new_password: str) -> Dict[str, Any]:
        """
        Change the current user's password.
        
        Args:
            current_password: The current password
            new_password: The new password
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(
            "/auth/change-password",
            json_data={
                "current_password": current_password,
                "new_password": new_password
            }
        )
        response.raise_for_status()
        result = response.json()
        
        # Clear token since it's now invalid
        self.clear_token()
        
        return result
    
    @require_auth
    @handle_api_errors(
        operation_name="Reset user password",
        custom_errors={
            403: "Admin privileges required to reset user passwords",
            404: "User not found",
            400: "Cannot reset your own password"
        }
    )
    def reset_user_password(self, user_id: str, new_password: str) -> Dict[str, Any]:
        """
        Reset a user's password (admin only).
        
        Args:
            user_id: The user ID whose password to reset
            new_password: The new password
            
        Returns:
            Dictionary containing the result of the operation
        """
        response = self.post(
            "/auth/reset-password",
            json_data={
                "user_id": user_id,
                "new_password": new_password
            }
        )
        response.raise_for_status()
        return response.json()
    
    def check_auth_status(self) -> Dict[str, Any]:
        """
        Check authentication status and return detailed information.
        
        Returns:
            Dictionary containing authentication status, user info, and security info
        """
        storage_method = self.token_manager.storage_method
        
        # Check if token exists
        if not self.token:
            return {
                "authenticated": False,
                "message": "Not authenticated",
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": self.token_manager.KEYRING_AVAILABLE
                }
            }
        
        # Validate token by making a request
        try:
            user_info = self.get_current_user()
            return {
                "authenticated": True,
                "user": user_info,
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": self.token_manager.KEYRING_AVAILABLE
                }
            }
        except AuthenticationError:
            return {
                "authenticated": False,
                "message": "Token expired or invalid",
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": self.token_manager.KEYRING_AVAILABLE
                }
            }
        except Exception as e:
            return {
                "authenticated": False,
                "message": f"Error checking status: {str(e)}",
                "security": {
                    "storage_method": storage_method,
                    "keyring_available": self.token_manager.KEYRING_AVAILABLE
                }
            }