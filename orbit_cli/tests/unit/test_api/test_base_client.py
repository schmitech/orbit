"""
Unit tests for BaseAPIClient.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests

from orbit_cli.api.base_client import BaseAPIClient
from orbit_cli.core.exceptions import NetworkError, AuthenticationError


class TestBaseAPIClient:
    """Test cases for BaseAPIClient class."""

    @pytest.mark.unit
    def test_init_default_values(self):
        """Test BaseAPIClient initialization with default values."""
        client = BaseAPIClient("http://localhost:8000")
        
        assert client.server_url == "http://localhost:8000"
        assert client.timeout == 30
        assert client.retry_attempts == 3
        assert client.verify_ssl is True
        assert client.token is None

    @pytest.mark.unit
    def test_init_custom_values(self):
        """Test BaseAPIClient initialization with custom values."""
        client = BaseAPIClient(
            server_url="https://api.example.com",
            token="test_token",
            timeout=60,
            retry_attempts=5,
            verify_ssl=False
        )
        
        assert client.server_url == "https://api.example.com"
        assert client.token == "test_token"
        assert client.timeout == 60
        assert client.retry_attempts == 5
        assert client.verify_ssl is False

    @pytest.mark.unit
    def test_build_url_absolute(self):
        """Test building absolute URLs."""
        client = BaseAPIClient("https://api.example.com")
        
        url = client._build_url("/test")
        assert url == "https://api.example.com/test"

    @pytest.mark.unit
    def test_build_url_relative(self):
        """Test building relative URLs."""
        client = BaseAPIClient("https://api.example.com")
        
        url = client._build_url("test")
        assert url == "https://api.example.com/test"

    @pytest.mark.unit
    def test_build_url_trailing_slash(self):
        """Test URL building with trailing slash in server_url."""
        client = BaseAPIClient("https://api.example.com/")
        
        url = client._build_url("/test")
        assert url == "https://api.example.com/test"

    @pytest.mark.unit
    def test_get_headers_no_token(self):
        """Test getting headers without authentication token."""
        client = BaseAPIClient("http://localhost:8000")
        
        headers = client._get_headers()
        assert "Authorization" not in headers

    @pytest.mark.unit
    def test_get_headers_with_token(self):
        """Test getting headers with authentication token."""
        client = BaseAPIClient("http://localhost:8000", token="test_token_123")
        
        headers = client._get_headers()
        assert headers["Authorization"] == "Bearer test_token_123"

    @pytest.mark.unit
    def test_get_headers_with_additional(self):
        """Test getting headers with additional headers."""
        client = BaseAPIClient("http://localhost:8000", token="test_token")
        additional = {"Custom-Header": "custom_value"}
        
        headers = client._get_headers(additional)
        assert headers["Authorization"] == "Bearer test_token"
        assert headers["Custom-Header"] == "custom_value"

    @pytest.mark.unit
    def test_session_property(self):
        """Test session property creates and reuses session."""
        client = BaseAPIClient("http://localhost:8000")
        
        # First access creates session
        session1 = client.session
        assert isinstance(session1, requests.Session)
        
        # Second access returns same session
        session2 = client.session
        assert session1 is session2

    @pytest.mark.unit
    def test_get_success(self, mock_api_response):
        """Test successful GET request."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.get("/test")
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='GET',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=None,
                json=None,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_get_with_params(self, mock_api_response):
        """Test GET request with query parameters."""
        client = BaseAPIClient("http://localhost:8000")
        params = {"key": "value", "page": 1}
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.get("/test", params=params)
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='GET',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=params,
                json=None,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_post_success(self, mock_api_response):
        """Test successful POST request."""
        client = BaseAPIClient("http://localhost:8000")
        data = {"key": "value"}
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.post("/test", json_data=data)
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='POST',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=None,
                json=data,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_put_success(self, mock_api_response):
        """Test successful PUT request."""
        client = BaseAPIClient("http://localhost:8000")
        data = {"key": "updated_value"}
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.put("/test", json_data=data)
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='PUT',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=None,
                json=data,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_delete_success(self, mock_api_response):
        """Test successful DELETE request."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.delete("/test")
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='DELETE',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=None,
                json=None,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_request_connection_error(self):
        """Test handling of connection errors."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', side_effect=requests.ConnectionError):
            with pytest.raises(NetworkError, match="Failed to connect to server"):
                client.get("/test")

    @pytest.mark.unit
    def test_request_timeout_error(self):
        """Test handling of timeout errors."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', side_effect=requests.Timeout):
            with pytest.raises(NetworkError, match="Request timed out"):
                client.get("/test")

    @pytest.mark.unit
    def test_request_retry_logic(self):
        """Test retry logic on connection errors."""
        client = BaseAPIClient("http://localhost:8000", retry_attempts=2)
        
        with patch.object(client.session, 'request') as mock_request:
            with patch('time.sleep'):  # Skip actual sleep
                # First call fails, second succeeds
                mock_request.side_effect = [
                    requests.ConnectionError("Connection failed"),
                    Mock(status_code=200)
                ]
                
                response = client.get("/test")
                
                assert mock_request.call_count == 2
                assert response.status_code == 200

    @pytest.mark.unit
    def test_request_retry_exhausted(self):
        """Test retry logic when all attempts fail."""
        client = BaseAPIClient("http://localhost:8000", retry_attempts=2)
        
        with patch.object(client.session, 'request') as mock_request:
            with patch('time.sleep'):  # Skip actual sleep
                mock_request.side_effect = requests.ConnectionError("Connection failed")
                
                with pytest.raises(NetworkError, match="Failed to connect to server"):
                    client.get("/test")
                
                assert mock_request.call_count == 2

    @pytest.mark.unit
    def test_request_no_retry_on_success(self):
        """Test that no retry happens on successful requests."""
        client = BaseAPIClient("http://localhost:8000", retry_attempts=3)
        
        with patch.object(client.session, 'request') as mock_request:
            mock_request.return_value = Mock(status_code=200)
            
            response = client.get("/test")
            
            assert mock_request.call_count == 1
            assert response.status_code == 200

    @pytest.mark.unit 
    def test_close_session(self):
        """Test closing the session."""
        client = BaseAPIClient("http://localhost:8000")
        
        # Access session to create it
        session = client.session
        
        with patch.object(session, 'close') as mock_close:
            client.close()
            mock_close.assert_called_once()

    @pytest.mark.unit
    def test_context_manager(self):
        """Test using client as context manager."""
        with patch('orbit_cli.api.base_client.BaseAPIClient.close') as mock_close:
            with BaseAPIClient("http://localhost:8000") as client:
                assert isinstance(client, BaseAPIClient)
            
            mock_close.assert_called_once()

    @pytest.mark.unit
    def test_custom_headers_in_request(self, mock_api_response):
        """Test passing custom headers to request."""
        client = BaseAPIClient("http://localhost:8000", token="test_token")
        custom_headers = {"X-Custom": "custom_value"}
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            client.get("/test", headers=custom_headers)
            
            # Verify the headers were merged correctly
            expected_headers = {
                "Authorization": "Bearer test_token",
                "X-Custom": "custom_value"
            }
            
            call_args = client.session.request.call_args
            assert call_args[1]['headers'] == expected_headers

    @pytest.mark.unit
    def test_url_trailing_slash_handling(self):
        """Test URL building handles trailing slashes correctly."""
        # Server URL with trailing slash
        client1 = BaseAPIClient("http://localhost:8000/")
        url1 = client1._build_url("/api/test")
        assert url1 == "http://localhost:8000/api/test"
        
        # Server URL without trailing slash
        client2 = BaseAPIClient("http://localhost:8000")
        url2 = client2._build_url("/api/test")
        assert url2 == "http://localhost:8000/api/test"

    @pytest.mark.unit
    def test_patch_method(self, mock_api_response):
        """Test PATCH method."""
        client = BaseAPIClient("http://localhost:8000")
        data = {"key": "patched_value"}
        
        with patch.object(client.session, 'request', return_value=mock_api_response):
            response = client.patch("/test", json_data=data)
            
            assert response == mock_api_response
            client.session.request.assert_called_once_with(
                method='PATCH',
                url="http://localhost:8000/test",
                headers=client._get_headers(),
                params=None,
                json=data,
                data=None,
                timeout=30,
                verify=True
            )

    @pytest.mark.unit
    def test_request_exception_handling(self):
        """Test general request exception handling."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', side_effect=requests.RequestException("General error")):
            with pytest.raises(NetworkError, match="Request failed"):
                client.get("/test")

    @pytest.mark.unit
    def test_unexpected_exception_handling(self):
        """Test handling of unexpected exceptions."""
        client = BaseAPIClient("http://localhost:8000")
        
        with patch.object(client.session, 'request', side_effect=ValueError("Unexpected error")):
            with pytest.raises(NetworkError, match="Unexpected error"):
                client.get("/test") 