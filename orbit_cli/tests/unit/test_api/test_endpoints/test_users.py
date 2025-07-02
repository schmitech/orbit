"""
Unit tests for users endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.api.endpoints.users import UsersEndpoints
from orbit_cli.core.exceptions import APIError, AuthenticationError


class TestUsersEndpoints:
    """Test cases for UsersEndpoints class."""

    @pytest.mark.unit
    def test_init(self, mock_base_client):
        """Test UsersEndpoints initialization."""
        users_endpoints = UsersEndpoints(mock_base_client)
        assert users_endpoints.client == mock_base_client

    @pytest.mark.unit
    def test_list_users_success(self, mock_base_client, mock_api_response):
        """Test successful user listing."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "users": [
                    {"id": "user1", "username": "user1", "email": "user1@example.com"},
                    {"id": "user2", "username": "user2", "email": "user2@example.com"}
                ],
                "total": 2,
                "page": 1,
                "per_page": 10
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.list_users()
            
            assert len(result["users"]) == 2
            assert result["total"] == 2
            mock_base_client.get.assert_called_once_with("/users")

    @pytest.mark.unit
    def test_list_users_with_pagination(self, mock_base_client, mock_api_response):
        """Test user listing with pagination parameters."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"users": [], "total": 0, "page": 2, "per_page": 5}
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.list_users(page=2, per_page=5)
            
            assert result["page"] == 2
            assert result["per_page"] == 5
            mock_base_client.get.assert_called_once_with(
                "/users",
                params={"page": 2, "per_page": 5}
            )

    @pytest.mark.unit
    def test_get_user_success(self, mock_base_client, mock_api_response, sample_user_data):
        """Test successful user retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": sample_user_data
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.get_user("user123")
            
            assert result["id"] == "user123"
            assert result["username"] == "testuser"
            mock_base_client.get.assert_called_once_with("/users/user123")

    @pytest.mark.unit
    def test_get_user_not_found(self, mock_base_client):
        """Test user retrieval for non-existent user."""
        response = Mock()
        response.status_code = 404
        response.json.return_value = {"error": "User not found"}
        
        with patch.object(mock_base_client, 'get', return_value=response):
            users_endpoints = UsersEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="User not found"):
                users_endpoints.get_user("nonexistent")

    @pytest.mark.unit
    def test_create_user_success(self, mock_base_client, mock_api_response):
        """Test successful user creation."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"id": "newuser123", "username": "newuser", "email": "new@example.com"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.create_user(
                username="newuser",
                email="new@example.com",
                password="password123"
            )
            
            assert result["username"] == "newuser"
            assert result["email"] == "new@example.com"
            mock_base_client.post.assert_called_once_with(
                "/users",
                data={
                    "username": "newuser",
                    "email": "new@example.com",
                    "password": "password123"
                }
            )

    @pytest.mark.unit
    def test_create_user_duplicate_username(self, mock_base_client):
        """Test user creation with duplicate username."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Username already exists"}
        
        with patch.object(mock_base_client, 'post', return_value=response):
            users_endpoints = UsersEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Username already exists"):
                users_endpoints.create_user("existinguser", "email@example.com", "password")

    @pytest.mark.unit
    def test_update_user_success(self, mock_base_client, mock_api_response):
        """Test successful user update."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"id": "user123", "username": "updateduser", "email": "updated@example.com"}
        }
        
        with patch.object(mock_base_client, 'put', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.update_user(
                "user123",
                username="updateduser",
                email="updated@example.com"
            )
            
            assert result["username"] == "updateduser"
            assert result["email"] == "updated@example.com"
            mock_base_client.put.assert_called_once_with(
                "/users/user123",
                data={"username": "updateduser", "email": "updated@example.com"}
            )

    @pytest.mark.unit
    def test_update_user_not_found(self, mock_base_client):
        """Test user update for non-existent user."""
        response = Mock()
        response.status_code = 404
        response.json.return_value = {"error": "User not found"}
        
        with patch.object(mock_base_client, 'put', return_value=response):
            users_endpoints = UsersEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="User not found"):
                users_endpoints.update_user("nonexistent", username="newuser")

    @pytest.mark.unit
    def test_delete_user_success(self, mock_base_client, mock_api_response):
        """Test successful user deletion."""
        with patch.object(mock_base_client, 'delete', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.delete_user("user123")
            
            assert result["status"] == "success"
            mock_base_client.delete.assert_called_once_with("/users/user123")

    @pytest.mark.unit
    def test_delete_user_not_found(self, mock_base_client):
        """Test user deletion for non-existent user."""
        response = Mock()
        response.status_code = 404
        response.json.return_value = {"error": "User not found"}
        
        with patch.object(mock_base_client, 'delete', return_value=response):
            users_endpoints = UsersEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="User not found"):
                users_endpoints.delete_user("nonexistent")

    @pytest.mark.unit
    def test_activate_user_success(self, mock_base_client, mock_api_response):
        """Test successful user activation."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.activate_user("user123")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with("/users/user123/activate")

    @pytest.mark.unit
    def test_deactivate_user_success(self, mock_base_client, mock_api_response):
        """Test successful user deactivation."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.deactivate_user("user123")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with("/users/user123/deactivate")

    @pytest.mark.unit
    def test_change_user_role_success(self, mock_base_client, mock_api_response):
        """Test successful user role change."""
        with patch.object(mock_base_client, 'put', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.change_user_role("user123", "admin")
            
            assert result["status"] == "success"
            mock_base_client.put.assert_called_once_with(
                "/users/user123/role",
                data={"role": "admin"}
            )

    @pytest.mark.unit
    def test_change_user_role_invalid_role(self, mock_base_client):
        """Test user role change with invalid role."""
        response = Mock()
        response.status_code = 400
        response.json.return_value = {"error": "Invalid role"}
        
        with patch.object(mock_base_client, 'put', return_value=response):
            users_endpoints = UsersEndpoints(mock_base_client)
            
            with pytest.raises(APIError, match="Invalid role"):
                users_endpoints.change_user_role("user123", "invalid_role")

    @pytest.mark.unit
    def test_search_users_success(self, mock_base_client, mock_api_response):
        """Test successful user search."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "users": [{"id": "user1", "username": "testuser"}],
                "total": 1
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.search_users("test")
            
            assert len(result["users"]) == 1
            assert result["users"][0]["username"] == "testuser"
            mock_base_client.get.assert_called_once_with(
                "/users/search",
                params={"q": "test"}
            )

    @pytest.mark.unit
    def test_get_user_stats_success(self, mock_base_client, mock_api_response):
        """Test successful user statistics retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "total_users": 100,
                "active_users": 85,
                "inactive_users": 15,
                "new_users_this_month": 10
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.get_user_stats()
            
            assert result["total_users"] == 100
            assert result["active_users"] == 85
            mock_base_client.get.assert_called_once_with("/users/stats")

    @pytest.mark.unit
    def test_bulk_operations_success(self, mock_base_client, mock_api_response):
        """Test successful bulk user operations."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"processed": 5, "successful": 4, "failed": 1}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.bulk_activate_users(["user1", "user2", "user3"])
            
            assert result["processed"] == 5
            assert result["successful"] == 4
            mock_base_client.post.assert_called_once_with(
                "/users/bulk/activate",
                data={"user_ids": ["user1", "user2", "user3"]}
            )

    @pytest.mark.unit
    def test_get_user_activity_success(self, mock_base_client, mock_api_response):
        """Test successful user activity retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "activities": [
                    {"action": "login", "timestamp": "2024-01-01T00:00:00Z"},
                    {"action": "logout", "timestamp": "2024-01-01T01:00:00Z"}
                ]
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.get_user_activity("user123")
            
            assert len(result["activities"]) == 2
            assert result["activities"][0]["action"] == "login"
            mock_base_client.get.assert_called_once_with("/users/user123/activity")

    @pytest.mark.unit
    def test_export_users_success(self, mock_base_client, mock_api_response):
        """Test successful user export."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"export_url": "https://example.com/export.csv"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            users_endpoints = UsersEndpoints(mock_base_client)
            result = users_endpoints.export_users(format="csv")
            
            assert result["export_url"] == "https://example.com/export.csv"
            mock_base_client.post.assert_called_once_with(
                "/users/export",
                data={"format": "csv"}
            ) 