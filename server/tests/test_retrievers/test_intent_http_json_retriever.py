"""
Tests for the HTTP JSON Intent Retriever

This test suite verifies the IntentHTTPJSONRetriever implementation,
including endpoint template substitution, HTTP request execution,
response parsing, and error handling.
"""

import pytest
import sys
import os
import json
from unittest.mock import Mock, AsyncMock
import httpx

# Add the server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from retrievers.implementations.intent.intent_http_json_retriever import IntentHTTPJSONRetriever


@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration for HTTP JSON retriever."""
    return {
        "datasources": {
            "http": {
                "base_url": "https://jsonplaceholder.typicode.com",
                "timeout": 30
            }
        },
        "general": {
        },
        "inference": {
            "openai": {
                "enabled": True,
                "api_key": os.getenv("OPENAI_API_KEY", "test-key"),
                "model": "gpt-4o-mini"
            }
        },
        "embedding": {
            "cohere": {
                "enabled": True,
                "api_key": os.getenv("COHERE_API_KEY", "test-key"),
                "model": "embed-english-v3.0"
            }
        },
        "stores": {
            "vector_stores": {
                "chroma": {
                    "enabled": True,
                    "type": "chroma",
                    "connection_params": {
                        "persist_directory": str(tmp_path / "chroma_db")
                    }
                }
            }
        },
        "adapter_config": {
            "domain_config_path": "utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_domain.yaml",
            "template_library_path": ["utils/http-intent-template/examples/jsonplaceholder/templates/jsonplaceholder_templates.yaml"],
            "template_collection_name": "test_http_templates",
            "store_name": "chroma",
            "confidence_threshold": 0.4,
            "max_templates": 5,
            "return_results": 10,
            "reload_templates_on_start": False,
            "force_reload_templates": False,
            "base_url": "https://jsonplaceholder.typicode.com",
            "default_timeout": 30,
            "enable_retries": True,
            "max_retries": 3,
            "retry_delay": 1.0
        },
        "inference_provider": "openai"
    }


@pytest.fixture
def mock_http_response():
    """Create a mock HTTP response."""
    def _create_response(status_code=200, json_data=None, text=None):
        response = Mock(spec=httpx.Response)
        response.status_code = status_code
        response.headers = {"Content-Type": "application/json"}
        response.text = text or json.dumps(json_data) if json_data else "{}"
        response.json = Mock(return_value=json_data or {})
        response.raise_for_status = Mock()
        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                f"HTTP {status_code}",
                request=Mock(),
                response=response
            )
        return response
    return _create_response


@pytest.fixture
def sample_template():
    """Create a sample HTTP template for testing."""
    return {
        "id": "get_post_by_id",
        "version": "1.0.0",
        "description": "Get a specific post by its ID",
        "http_method": "GET",
        "endpoint_template": "/posts/{post_id}",
        "headers": {
            "Accept": "application/json"
        },
        "parameters": [
            {
                "name": "post_id",
                "type": "integer",
                "required": True,
                "description": "The ID of the post to retrieve",
                "location": "path"
            }
        ],
        "response_mapping": {
            "items_path": "$",
            "fields": [
                {"name": "id", "path": "$.id", "type": "integer"},
                {"name": "title", "path": "$.title", "type": "string"},
                {"name": "body", "path": "$.body", "type": "string"}
            ]
        }
    }


class TestEndpointTemplateProcessing:
    """Test endpoint template processing and parameter substitution."""

    @pytest.mark.asyncio
    async def test_process_endpoint_template_single_braces(self, test_config):
        """Test endpoint template substitution with single braces {param} syntax."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        endpoint_template = "/posts/{post_id}"
        parameters = {"post_id": 5}
        
        result = retriever._process_endpoint_template(endpoint_template, parameters)
        
        assert result == "/posts/5"
        assert "{post_id}" not in result

    @pytest.mark.asyncio
    async def test_process_endpoint_template_double_braces(self, test_config):
        """Test endpoint template substitution with double braces {{param}} syntax."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        endpoint_template = "/posts/{{post_id}}"
        parameters = {"post_id": 5}
        
        result = retriever._process_endpoint_template(endpoint_template, parameters)
        
        assert result == "/posts/5"
        assert "{{post_id}}" not in result

    @pytest.mark.asyncio
    async def test_process_endpoint_template_multiple_params(self, test_config):
        """Test endpoint template with multiple path parameters."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        endpoint_template = "/users/{user_id}/posts/{post_id}"
        parameters = {"user_id": 1, "post_id": 5}
        
        result = retriever._process_endpoint_template(endpoint_template, parameters)
        
        assert result == "/users/1/posts/5"
        assert "{user_id}" not in result
        assert "{post_id}" not in result

    @pytest.mark.asyncio
    async def test_process_endpoint_template_no_substitution(self, test_config):
        """Test endpoint template with no parameters to substitute."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        endpoint_template = "/posts"
        parameters = {}
        
        result = retriever._process_endpoint_template(endpoint_template, parameters)
        
        assert result == "/posts"

    @pytest.mark.asyncio
    async def test_process_endpoint_template_missing_param(self, test_config):
        """Test endpoint template when parameter is missing."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        endpoint_template = "/posts/{post_id}"
        parameters = {}  # Missing post_id
        
        result = retriever._process_endpoint_template(endpoint_template, parameters)
        
        # Should return unchanged if parameter is missing
        assert result == "/posts/{post_id}"


class TestQueryParameterBuilding:
    """Test query parameter building from templates."""

    @pytest.mark.asyncio
    async def test_build_query_params_from_template(self, test_config):
        """Test building query parameters from template definition."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "query_params": {
                "userId": "{{user_id}}",
                "_limit": "{{limit}}"
            }
        }
        parameters = {"user_id": 1, "limit": 10}
        
        result = retriever._build_query_params(template, parameters)
        
        assert result == {"userId": 1, "_limit": 10}

    @pytest.mark.asyncio
    async def test_build_query_params_from_parameter_definitions(self, test_config):
        """Test building query parameters from parameter definitions with location='query'."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "parameters": [
                {
                    "name": "user_id",
                    "location": "query"
                },
                {
                    "name": "limit",
                    "location": "query"
                }
            ]
        }
        parameters = {"user_id": 1, "limit": 10}
        
        result = retriever._build_query_params(template, parameters)
        
        assert result == {"user_id": 1, "limit": 10}

    @pytest.mark.asyncio
    async def test_build_query_params_static_values(self, test_config):
        """Test building query parameters with static (non-template) values."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "query_params": {
                "format": "json",
                "version": "v1"
            }
        }
        parameters = {}
        
        result = retriever._build_query_params(template, parameters)
        
        assert result == {"format": "json", "version": "v1"}


class TestRequestBuilding:
    """Test request body and header building."""

    @pytest.mark.asyncio
    async def test_build_request_headers(self, test_config):
        """Test building request headers from template."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "headers": {
                "Accept": "application/json",
                "Authorization": "Bearer {{token}}"
            }
        }
        parameters = {"token": "abc123"}
        
        result = retriever._build_request_headers(template, parameters)
        
        assert result["Accept"] == "application/json"
        assert result["Authorization"] == "Bearer abc123"

    @pytest.mark.asyncio
    async def test_build_request_body_from_template(self, test_config):
        """Test building request body from body template."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "body_template": {
                "title": "{{title}}",
                "body": "{{body}}",
                "userId": "{{user_id}}"
            }
        }
        parameters = {
            "title": "Test Post",
            "body": "Test content",
            "user_id": 1
        }
        
        result = retriever._build_request_body(template, parameters)
        
        # Note: Substitution converts values to strings when replacing in template strings
        assert result == {
            "title": "Test Post",
            "body": "Test content",
            "userId": "1"  # String because template value "{{user_id}}" is replaced as string
        }

    @pytest.mark.asyncio
    async def test_build_request_body_from_parameters(self, test_config):
        """Test building request body from parameters with location='body'."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "parameters": [
                {"name": "title", "location": "body"},
                {"name": "body", "location": "body"}
            ]
        }
        parameters = {
            "title": "Test Post",
            "body": "Test content"
        }
        
        result = retriever._build_request_body(template, parameters)
        
        assert result == {
            "title": "Test Post",
            "body": "Test content"
        }


class TestHTTPRequestExecution:
    """Test HTTP request execution with mocked responses."""

    @pytest.mark.asyncio
    async def test_execute_rest_request_success(self, test_config, mock_http_response):
        """Test successful HTTP request execution."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(
            status_code=200,
            json_data={"id": 1, "title": "Test Post", "body": "Test content"}
        )
        
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        response = await retriever._execute_rest_request(
            method="GET",
            endpoint="/posts/1",
            timeout=30
        )
        
        assert response.status_code == 200
        assert response.json() == {"id": 1, "title": "Test Post", "body": "Test content"}
        retriever.http_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_rest_request_404_error(self, test_config, mock_http_response):
        """Test HTTP 404 error handling."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(status_code=404, json_data={})
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        with pytest.raises(httpx.HTTPStatusError):
            await retriever._execute_rest_request(
                method="GET",
                endpoint="/posts/999",
                timeout=30
            )

    @pytest.mark.asyncio
    async def test_execute_rest_request_with_query_params(self, test_config, mock_http_response):
        """Test HTTP request with query parameters."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(
            status_code=200,
            json_data=[{"id": 1}, {"id": 2}]
        )
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        response = await retriever._execute_rest_request(
            method="GET",
            endpoint="/posts",
            params={"userId": 1, "_limit": 10},
            timeout=30
        )
        
        assert response.status_code == 200
        retriever.http_client.request.assert_called_once()
        call_kwargs = retriever.http_client.request.call_args[1]
        assert call_kwargs["params"] == {"userId": 1, "_limit": 10}

    @pytest.mark.asyncio
    async def test_execute_rest_request_with_body(self, test_config, mock_http_response):
        """Test HTTP POST request with JSON body."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(
            status_code=201,
            json_data={"id": 101, "title": "New Post"}
        )
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        response = await retriever._execute_rest_request(
            method="POST",
            endpoint="/posts",
            json_data={"title": "New Post", "body": "Content", "userId": 1},
            timeout=30
        )
        
        assert response.status_code == 201
        retriever.http_client.request.assert_called_once()
        call_kwargs = retriever.http_client.request.call_args[1]
        # httpx uses 'json' parameter, not 'json_data'
        # When passing json_data directly (not through template substitution), original types are preserved
        assert call_kwargs["json"] == {"title": "New Post", "body": "Content", "userId": 1}


class TestResponseParsing:
    """Test HTTP response parsing."""

    @pytest.mark.asyncio
    async def test_parse_response_single_object(self, test_config, mock_http_response):
        """Test parsing a single object response."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "response_mapping": {
                "items_path": "$",
                "fields": [
                    {"name": "id", "path": "$.id"},
                    {"name": "title", "path": "$.title"}
                ]
            }
        }
        
        response = mock_http_response(
            status_code=200,
            json_data={"id": 1, "title": "Test Post", "body": "Content"}
        )
        
        results = retriever._parse_response(response, template)
        
        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["title"] == "Test Post"

    @pytest.mark.asyncio
    async def test_parse_response_array(self, test_config, mock_http_response):
        """Test parsing an array response."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "response_mapping": {
                "items_path": "$",
                "fields": [
                    {"name": "id", "path": "$.id"},
                    {"name": "title", "path": "$.title"}
                ]
            }
        }
        
        response = mock_http_response(
            status_code=200,
            json_data=[
                {"id": 1, "title": "Post 1"},
                {"id": 2, "title": "Post 2"}
            ]
        )
        
        results = retriever._parse_response(response, template)
        
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_parse_response_with_field_mapping(self, test_config, mock_http_response):
        """Test parsing response with field mapping."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "response_mapping": {
                "items_path": "$",
                "fields": [
                    {"name": "post_id", "path": "$.id"},
                    {"name": "post_title", "path": "$.title"}
                ]
            }
        }
        
        response = mock_http_response(
            status_code=200,
            json_data={"id": 1, "title": "Test Post"}
        )
        
        results = retriever._parse_response(response, template)
        
        assert len(results) == 1
        assert "post_id" in results[0]
        assert "post_title" in results[0]
        assert results[0]["post_id"] == 1
        assert results[0]["post_title"] == "Test Post"


class TestTemplateExecution:
    """Test full template execution flow."""

    @pytest.mark.asyncio
    async def test_execute_template_success(self, test_config, sample_template, mock_http_response):
        """Test successful template execution."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(
            status_code=200,
            json_data={"id": 5, "title": "Post 5", "body": "Content", "userId": 1}
        )
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        parameters = {"post_id": 5}
        results, error = await retriever._execute_template(sample_template, parameters)
        
        assert error is None
        assert len(results) == 1
        assert results[0]["id"] == 5
        assert results[0]["title"] == "Post 5"
        
        # Verify the endpoint was correctly substituted
        call_kwargs = retriever.http_client.request.call_args[1]
        assert call_kwargs["url"] == "/posts/5"

    @pytest.mark.asyncio
    async def test_execute_template_404_error(self, test_config, sample_template, mock_http_response):
        """Test template execution with 404 error."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        mock_response = mock_http_response(status_code=404, json_data={})
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        parameters = {"post_id": 999}
        results, error = await retriever._execute_template(sample_template, parameters)
        
        assert len(results) == 0
        assert error is not None
        assert "404" in error

    @pytest.mark.asyncio
    async def test_execute_template_with_query_params(self, test_config, mock_http_response):
        """Test template execution with query parameters."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        template = {
            "id": "list_posts",
            "http_method": "GET",
            "endpoint_template": "/posts",
            "query_params": {
                "userId": "{{user_id}}",
                "_limit": "{{limit}}"
            },
            "response_mapping": {
                "items_path": "$"
            }
        }
        
        mock_response = mock_http_response(
            status_code=200,
            json_data=[{"id": 1}, {"id": 2}]
        )
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        parameters = {"user_id": 1, "limit": 10}
        results, error = await retriever._execute_template(template, parameters)
        
        assert error is None
        assert len(results) == 2
        
        # Verify query parameters were included
        call_kwargs = retriever.http_client.request.call_args[1]
        assert call_kwargs["params"] == {"userId": 1, "_limit": 10}

    @pytest.mark.asyncio
    async def test_execute_template_post_with_body(self, test_config, mock_http_response):
        """Test POST template execution with request body."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        template = {
            "id": "create_post",
            "http_method": "POST",
            "endpoint_template": "/posts",
            "body_template": {
                "title": "{{title}}",
                "body": "{{body}}",
                "userId": "{{user_id}}"
            },
            "response_mapping": {
                "items_path": "$"
            }
        }
        
        mock_response = mock_http_response(
            status_code=201,
            json_data={"id": 101, "title": "New Post"}
        )
        retriever.http_client.request = AsyncMock(return_value=mock_response)
        
        parameters = {
            "title": "New Post",
            "body": "Content",
            "user_id": 1
        }
        results, error = await retriever._execute_template(template, parameters)
        
        assert error is None
        assert len(results) == 1
        
        # Verify request body was included
        call_kwargs = retriever.http_client.request.call_args[1]
        # httpx uses 'json' parameter, not 'json_data'
        # Note: Substitution converts values to strings when replacing in template strings
        assert call_kwargs["json"] == {
            "title": "New Post",
            "body": "Content",
            "userId": "1"  # String because template value "{{user_id}}" is replaced as string
        }
        assert call_kwargs["method"] == "POST"


class TestErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_execute_template_network_error(self, test_config, sample_template):
        """Test template execution with network error."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        retriever.http_client.request = AsyncMock(side_effect=httpx.NetworkError("Connection failed"))
        
        parameters = {"post_id": 5}
        results, error = await retriever._execute_template(sample_template, parameters)
        
        assert len(results) == 0
        assert error is not None
        assert "Connection failed" in error

    @pytest.mark.asyncio
    async def test_execute_template_timeout(self, test_config, sample_template):
        """Test template execution with timeout error."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        await retriever._initialize_http_client()
        
        retriever.http_client.request = AsyncMock(side_effect=httpx.TimeoutException("Request timeout"))
        
        parameters = {"post_id": 5}
        results, error = await retriever._execute_template(sample_template, parameters)
        
        assert len(results) == 0
        assert error is not None
        assert "timeout" in error.lower()

    @pytest.mark.asyncio
    async def test_parse_response_invalid_json(self, test_config):
        """Test parsing response with invalid JSON."""
        retriever = IntentHTTPJSONRetriever(config=test_config)
        
        template = {
            "response_mapping": {
                "items_path": "$"
            }
        }
        
        response = Mock(spec=httpx.Response)
        response.headers = {"Content-Type": "application/json"}
        response.text = "Invalid JSON {"
        response.json = Mock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
        
        results = retriever._parse_response(response, template)
        
        # Should return text response when JSON parsing fails
        assert len(results) == 1
        assert "response" in results[0]
        assert "Invalid JSON" in results[0]["response"]

