"""
Unit tests for auth endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.api.endpoints.auth import AuthEndpoints
from orbit_cli.core.exceptions import AuthenticationError, APIError


class TestAuthEndpoints:
    """Test cases for AuthEndpoints class."""

    @pytest.mark.unit
    def test_init(self, mock_base_client):
        """Test AuthEndpoints initialization."""
        auth_endpoints = AuthEndpoints(mock_base_client)
        assert auth_endpoints.client == mock_base_client

    @pytest.mark.unit
    def test_login_success(self, mock_base_client, mock_api_response):
        """Test successful login."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "token": "test_token_123",
                "user": {"id": "user123", "username": "testuser"}
            }
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.login("testuser", "password123")
            
            assert result["token"] == "test_token_123"
            assert result["user"]["username"] == "testuser"
            mock_base_client.post.assert_called_once_with(
                "/auth/login",
                data={"username": "testuser", "password": "password123"}
            )

    @pytest.mark.unit
    def test_login_invalid_credentials(self, mock_base_client):
        """Test login with invalid credentials."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"error": "Invalid credentials"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(AuthenticationError, match="Invalid credentials"):
                auth_endpoints.login("invalid", "wrong")

    @pytest.mark.unit
    def test_logout_success(self, mock_base_client, mock_api_response):
        """Test successful logout."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.logout()
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with("/auth/logout")

    @pytest.mark.unit
    def test_refresh_token_success(self, mock_base_client, mock_api_response):
        """Test successful token refresh."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"token": "new_token_456"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.refresh_token()
            
            assert result["token"] == "new_token_456"
            mock_base_client.post.assert_called_once_with("/auth/refresh")

    @pytest.mark.unit
    def test_refresh_token_expired(self, mock_base_client):
        """Test token refresh with expired token."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"error": "Token expired"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(AuthenticationError, match="Token expired"):
                auth_endpoints.refresh_token()

    @pytest.mark.unit
    def test_register_success(self, mock_base_client, mock_api_response):
        """Test successful user registration."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "user": {"id": "user123", "username": "newuser"},
                "token": "registration_token"
            }
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.register(
                username="newuser",
                email="newuser@example.com",
                password="password123"
            )
            
            assert result["user"]["username"] == "newuser"
            assert result["token"] == "registration_token"
            mock_base_client.post.assert_called_once_with(
                "/auth/register",
                data={
                    "username": "newuser",
                    "email": "newuser@example.com",
                    "password": "password123"
                }
            )

    @pytest.mark.unit
    def test_register_duplicate_username(self, mock_base_client):
        """Test registration with duplicate username."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Username already exists"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Username already exists"):
                auth_endpoints.register("existinguser", "email@example.com", "password")

    @pytest.mark.unit
    def test_register_invalid_email(self, mock_base_client):
        """Test registration with invalid email."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Invalid email format"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Invalid email format"):
                auth_endpoints.register("user", "invalid-email", "password")

    @pytest.mark.unit
    def test_register_weak_password(self, mock_base_client):
        """Test registration with weak password."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Password too weak"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Password too weak"):
                auth_endpoints.register("user", "email@example.com", "123")

    @pytest.mark.unit
    def test_verify_token_success(self, mock_base_client, mock_api_response):
        """Test successful token verification."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"valid": True, "user": {"id": "user123"}}
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.verify_token("test_token")
            
            assert result["valid"] is True
            assert result["user"]["id"] == "user123"
            mock_base_client.get.assert_called_once_with("/auth/verify")

    @pytest.mark.unit
    def test_verify_token_invalid(self, mock_base_client):
        """Test token verification with invalid token."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"error": "Invalid token"}
        
        with patch.object(mock_base_client, 'get', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(AuthenticationError, match="Invalid token"):
                auth_endpoints.verify_token("invalid_token")

    @pytest.mark.unit
    def test_change_password_success(self, mock_base_client, mock_api_response):
        """Test successful password change."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.change_password("oldpass", "newpass")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with(
                "/auth/change-password",
                data={"old_password": "oldpass", "new_password": "newpass"}
            )

    @pytest.mark.unit
    def test_change_password_wrong_old_password(self, mock_base_client):
        """Test password change with wrong old password."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Incorrect old password"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Incorrect old password"):
                auth_endpoints.change_password("wrong", "newpass")

    @pytest.mark.unit
    def test_reset_password_request_success(self, mock_base_client, mock_api_response):
        """Test successful password reset request."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.reset_password_request("user@example.com")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with(
                "/auth/reset-password-request",
                data={"email": "user@example.com"}
            )

    @pytest.mark.unit
    def test_reset_password_success(self, mock_base_client, mock_api_response):
        """Test successful password reset."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.reset_password("reset_token", "newpassword")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with(
                "/auth/reset-password",
                data={"token": "reset_token", "new_password": "newpassword"}
            )

    @pytest.mark.unit
    def test_reset_password_invalid_token(self, mock_base_client):
        """Test password reset with invalid token."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Invalid reset token"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Invalid reset token"):
                auth_endpoints.reset_password("invalid_token", "newpassword")

    @pytest.mark.unit
    def test_get_current_user_success(self, mock_base_client, mock_api_response):
        """Test successful current user retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"id": "user123", "username": "testuser", "email": "test@example.com"}
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.get_current_user()
            
            assert result["username"] == "testuser"
            assert result["email"] == "test@example.com"
            mock_base_client.get.assert_called_once_with("/auth/me")

    @pytest.mark.unit
    def test_get_current_user_not_authenticated(self, mock_base_client):
        """Test current user retrieval without authentication."""
        response = Mock()
        response.status_code = 401
        response.json.return_value = {"error": "Not authenticated"}
        
        with patch.object(mock_base_client, 'get', return_value=response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            
            with pytest.raises(AuthenticationError, match="Not authenticated"):
                auth_endpoints.get_current_user()

    @pytest.mark.unit
    def test_login_with_remember_me(self, mock_base_client, mock_api_response):
        """Test login with remember me option."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"token": "long_lived_token"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.login("user", "pass", remember_me=True)
            
            assert result["token"] == "long_lived_token"
            mock_base_client.post.assert_called_once_with(
                "/auth/login",
                data={"username": "user", "password": "pass", "remember_me": True}
            )

    @pytest.mark.unit
    def test_login_with_mfa_token(self, mock_base_client, mock_api_response):
        """Test login with MFA token."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"token": "mfa_authenticated_token"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            auth_endpoints = AuthEndpoints(mock_base_client)
            result = auth_endpoints.login("user", "pass", mfa_token="123456")
            
            assert result["token"] == "mfa_authenticated_token"
            mock_base_client.post.assert_called_once_with(
                "/auth/login",
                data={"username": "user", "password": "pass", "mfa_token": "123456"}
            ) 