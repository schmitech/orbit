"""
Unit tests for prompts endpoints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from orbit_cli.api.endpoints.prompts import PromptsEndpoints
from orbit_cli.core.exceptions import APIError, AuthenticationError


class TestPromptsEndpoints:
    """Test cases for PromptsEndpoints class."""

    @pytest.mark.unit
    def test_init(self, mock_base_client):
        """Test PromptsEndpoints initialization."""
        prompts_endpoints = PromptsEndpoints(mock_base_client)
        assert prompts_endpoints.client == mock_base_client

    @pytest.mark.unit
    def test_list_prompts_success(self, mock_base_client, mock_api_response):
        """Test successful prompt listing."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "prompts": [
                    {"id": "prompt1", "name": "Prompt 1", "category": "general"},
                    {"id": "prompt2", "name": "Prompt 2", "category": "specialized"}
                ],
                "total": 2
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.list_prompts()
            
            assert len(result["prompts"]) == 2
            assert result["total"] == 2
            mock_base_client.get.assert_called_once_with("/prompts")

    @pytest.mark.unit
    def test_get_prompt_success(self, mock_base_client, mock_api_response, sample_prompt_data):
        """Test successful prompt retrieval."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": sample_prompt_data
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.get_prompt("prompt123")
            
            assert result["id"] == "prompt123"
            assert result["name"] == "Test Prompt"
            mock_base_client.get.assert_called_once_with("/prompts/prompt123")

    @pytest.mark.unit
    def test_create_prompt_success(self, mock_base_client, mock_api_response):
        """Test successful prompt creation."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "id": "newprompt123",
                "name": "New Prompt",
                "content": "You are a helpful assistant.",
                "category": "general"
            }
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.create_prompt(
                name="New Prompt",
                content="You are a helpful assistant.",
                category="general"
            )
            
            assert result["name"] == "New Prompt"
            assert result["content"] == "You are a helpful assistant."
            mock_base_client.post.assert_called_once_with(
                "/prompts",
                data={
                    "name": "New Prompt",
                    "content": "You are a helpful assistant.",
                    "category": "general"
                }
            )

    @pytest.mark.unit
    def test_update_prompt_success(self, mock_base_client, mock_api_response):
        """Test successful prompt update."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "id": "prompt123",
                "name": "Updated Prompt",
                "content": "Updated content."
            }
        }
        
        with patch.object(mock_base_client, 'put', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.update_prompt(
                "prompt123",
                name="Updated Prompt",
                content="Updated content."
            )
            
            assert result["name"] == "Updated Prompt"
            assert result["content"] == "Updated content."
            mock_base_client.put.assert_called_once_with(
                "/prompts/prompt123",
                data={
                    "name": "Updated Prompt",
                    "content": "Updated content."
                }
            )

    @pytest.mark.unit
    def test_delete_prompt_success(self, mock_base_client, mock_api_response):
        """Test successful prompt deletion."""
        with patch.object(mock_base_client, 'delete', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.delete_prompt("prompt123")
            
            assert result["status"] == "success"
            mock_base_client.delete.assert_called_once_with("/prompts/prompt123")

    @pytest.mark.unit
    def test_search_prompts_success(self, mock_base_client, mock_api_response):
        """Test successful prompt search."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "prompts": [{"id": "prompt1", "name": "Test Prompt"}],
                "total": 1
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.search_prompts("test")
            
            assert len(result["prompts"]) == 1
            assert result["prompts"][0]["name"] == "Test Prompt"
            mock_base_client.get.assert_called_once_with(
                "/prompts/search",
                params={"q": "test"}
            )

    @pytest.mark.unit
    def test_get_prompts_by_category_success(self, mock_base_client, mock_api_response):
        """Test successful prompt retrieval by category."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "prompts": [
                    {"id": "prompt1", "name": "General Prompt", "category": "general"}
                ]
            }
        }
        
        with patch.object(mock_base_client, 'get', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.get_prompts_by_category("general")
            
            assert len(result["prompts"]) == 1
            assert result["prompts"][0]["category"] == "general"
            mock_base_client.get.assert_called_once_with(
                "/prompts/category/general"
            )

    @pytest.mark.unit
    def test_duplicate_prompt_success(self, mock_base_client, mock_api_response):
        """Test successful prompt duplication."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {
                "id": "duplicate123",
                "name": "Test Prompt (Copy)",
                "content": "You are a helpful assistant."
            }
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.duplicate_prompt("prompt123", "Test Prompt (Copy)")
            
            assert result["name"] == "Test Prompt (Copy)"
            mock_base_client.post.assert_called_once_with(
                "/prompts/prompt123/duplicate",
                data={"name": "Test Prompt (Copy)"}
            )

    @pytest.mark.unit
    def test_export_prompts_success(self, mock_base_client, mock_api_response):
        """Test successful prompt export."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"export_url": "https://example.com/prompts.json"}
        }
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.export_prompts(format="json")
            
            assert result["export_url"] == "https://example.com/prompts.json"
            mock_base_client.post.assert_called_once_with(
                "/prompts/export",
                data={"format": "json"}
            )

    @pytest.mark.unit
    def test_import_prompts_success(self, mock_base_client, mock_api_response):
        """Test successful prompt import."""
        mock_api_response.json.return_value = {
            "status": "success",
            "data": {"imported": 5, "skipped": 1}
        }
        
        prompts_data = [
            {"name": "Prompt 1", "content": "Content 1"},
            {"name": "Prompt 2", "content": "Content 2"}
        ]
        
        with patch.object(mock_base_client, 'post', return_value=mock_api_response):
            prompts_endpoints = PromptsEndpoints(mock_base_client)
            result = prompts_endpoints.import_prompts(prompts_data)
            
            assert result["imported"] == 5
            assert result["skipped"] == 1
            mock_base_client.post.assert_called_once_with(
                "/prompts/import",
                data={"prompts": prompts_data}
            ) 