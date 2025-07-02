"""
Unit tests for API keys endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.api.endpoints.keys import KeysEndpoints
from orbit_cli.core.exceptions import APIError, AuthenticationError


class TestKeysEndpoints:
    """Test cases for KeysEndpoints class."""

    @pytest.mark.unit
    def test_init(self, mock_base_client):
        """Test KeysEndpoints initialization."""
        keys_endpoints = KeysEndpoints(mock_base_client)
        assert keys_endpoints.client == mock_base_client

    @pytest.mark.unit
    def test_list_keys_success(self, mock_base_client, mock_api_response):
        """Test successful API key listing."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "keys": [
                    {"id": "key1", "name": "Key 1", "key": "sk-***", "created_at": "2024-01-01T00:00:00Z"},
                    {"id": "key2", "name": "Key 2", "key": "sk-***", "created_at": "2024-01-02T00:00:00Z"}
                ],
                "total": 2
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            keys_endpoints = KeysEndpoints(mock_base_client)
            result = keys_endpoints.list_keys()
            
            assert len(result["keys"]) == 2
            assert result["total"] == 2
            mock_base_client.get.assert_called_once_with("/keys")

    @pytest.mark.unit
    def test_get_key_success(self, mock_base_client, mock_api_response, sample_api_key_data):
        """Test successful API key retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": sample_api_key_data
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            keys_endpoints = KeysEndpoints(mock_base_client)
            result = keys_endpoints.get_key("key123")
            
            assert result["id"] == "key123"
            assert result["name"] == "Test API Key"
            mock_base_client.get.assert_called_once_with("/keys/key123")

    @pytest.mark.unit
    def test_create_key_success(self, mock_base_client, mock_api_response):
        """Test successful API key creation."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "id": "newkey123",
                "name": "New API Key",
                "key": "sk-newkey1234567890abcdef",
                "created_at": "2024-01-01T00:00:00Z"
            }
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            keys_endpoints = KeysEndpoints(mock_base_client)
            result = keys_endpoints.create_key("New API Key")
            
            assert result["name"] == "New API Key"
            assert result["key"].startswith("sk-")
            mock_base_client.post.assert_called_once_with(
                "/keys",
                data={"name": "New API Key"}
            )

    @pytest.mark.unit
    def test_delete_key_success(self, mock_base_client, mock_api_response):
        """Test successful API key deletion."""
        with patch.object(mock_base_client, 'delete', return_value=mock_api_response):
            keys_endpoints = KeysEndpoints(mock_base_client)
            result = keys_endpoints.delete_key("key123")
            
            assert result["status"] == "success"
            mock_base_client.delete.assert_called_once_with("/keys/key123")

    @pytest.mark.unit
    def test_revoke_key_success(self, mock_base_client, mock_api_response):
        """Test successful API key revocation."""
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            keys_endpoints = KeysEndpoints(mock_base_client)
            result = keys_endpoints.revoke_key("key123")
            
            assert result["status"] == "success"
            mock_base_client.post.assert_called_once_with("/keys/key123/revoke") 