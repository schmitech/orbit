"""Unit tests for API decorators."""

import pytest
import time
from unittest.mock import Mock, patch
import requests

from orbit_cli.api.decorators import (
    handle_api_errors,
    retry_on_failure,
    require_auth,
    validate_response,
    paginated,
    rate_limited
)
from orbit_cli.core.exceptions import (
    OrbitError,
    AuthenticationError,
    NetworkError,
    ValidationError
)


class TestHandleApiErrors:
    """Test cases for handle_api_errors decorator."""
    
    def test_successful_request(self):
        """Test decorator with successful request."""
        @handle_api_errors(operation_name="Test operation")
        def test_func():
            return {"success": True}
        
        result = test_func()
        assert result == {"success": True}
    
    def test_http_401_error(self):
        """Test handling of 401 authentication error."""
        @handle_api_errors(operation_name="Test operation")
        def test_func():
            response = Mock()
            response.status_code = 401
            response.text = "Unauthorized"
            raise requests.exceptions.HTTPError(response=response)
        
        with pytest.raises(AuthenticationError) as exc_info:
            test_func()
        
        assert "Authentication failed" in str(exc_info.value)
    
    def test_http_403_error(self):
        """Test handling of 403 permission error."""
        @handle_api_errors(operation_name="Test operation")
        def test_func():
            response = Mock()
            response.status_code = 403
            response.text = "Forbidden"
            raise requests.exceptions.HTTPError(response=response)
        
        with pytest.raises(AuthenticationError) as exc_info:
            test_func()
        
        assert "Permission denied" in str(exc_info.value)
    
    def test_http_404_error(self):
        """Test handling of 404 not found error."""
        @handle_api_errors(operation_name="Test resource")
        def test_func():
            response = Mock()
            response.status_code = 404
            response.text = "Not found"
            raise requests.exceptions.HTTPError(response=response)
        
        with pytest.raises(OrbitError) as exc_info:
            test_func()
        
        assert "Test resource failed: Resource not found" in str(exc_info.value)
    
    def test_custom_error_messages(self):
        """Test decorator with custom error messages."""
        @handle_api_errors(
            operation_name="Test operation",
            custom_errors={404: "Custom not found message"}
        )
        def test_func():
            response = Mock()
            response.status_code = 404
            response.text = "Not found"
            raise requests.exceptions.HTTPError(response=response)
        
        with pytest.raises(OrbitError) as exc_info:
            test_func()
        
        assert "Custom not found message" in str(exc_info.value)
    
    def test_network_error_passthrough(self):
        """Test that NetworkError is passed through."""
        @handle_api_errors()
        def test_func():
            raise NetworkError("Connection failed")
        
        with pytest.raises(NetworkError) as exc_info:
            test_func()
        
        assert "Connection failed" in str(exc_info.value)
    
    def test_unexpected_error(self):
        """Test handling of unexpected errors."""
        @handle_api_errors(operation_name="Test operation")
        def test_func():
            raise ValueError("Unexpected error")
        
        with pytest.raises(OrbitError) as exc_info:
            test_func()
        
        assert "Test operation failed: Unexpected error" in str(exc_info.value)


class TestRetryOnFailure:
    """Test cases for retry_on_failure decorator."""
    
    def test_successful_first_attempt(self):
        """Test successful request on first attempt."""
        attempt_count = 0
        
        @retry_on_failure(max_attempts=3, delay=0.1)
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            return "success"
        
        result = test_func()
        assert result == "success"
        assert attempt_count == 1
    
    def test_retry_on_network_error(self):
        """Test retry on network error."""
        attempt_count = 0
        
        @retry_on_failure(max_attempts=3, delay=0.01)
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise NetworkError("Connection failed")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert attempt_count == 3
    
    def test_max_attempts_exceeded(self):
        """Test failure after max attempts."""
        attempt_count = 0
        
        @retry_on_failure(max_attempts=3, delay=0.01)
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            raise NetworkError("Connection failed")
        
        with pytest.raises(NetworkError):
            test_func()
        
        assert attempt_count == 3
    
    def test_exponential_backoff(self):
        """Test exponential backoff timing."""
        delays = []
        
        @retry_on_failure(max_attempts=3, delay=0.1, backoff="exponential")
        def test_func():
            start = time.time()
            raise NetworkError("Connection failed")
        
        start_time = time.time()
        with pytest.raises(NetworkError):
            test_func()
        
        total_time = time.time() - start_time
        # With exponential backoff: 0.1 + 0.2 = 0.3 seconds minimum
        assert total_time >= 0.3
    
    def test_linear_backoff(self):
        """Test linear backoff timing."""
        @retry_on_failure(max_attempts=3, delay=0.1, backoff="linear")
        def test_func():
            raise NetworkError("Connection failed")
        
        start_time = time.time()
        with pytest.raises(NetworkError):
            test_func()
        
        total_time = time.time() - start_time
        # With linear backoff: 0.1 + 0.2 = 0.3 seconds minimum
        assert total_time >= 0.3
    
    def test_custom_retry_exceptions(self):
        """Test retry with custom exception types."""
        attempt_count = 0
        
        @retry_on_failure(max_attempts=3, delay=0.01, retry_on=(ValueError,))
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Custom error")
            return "success"
        
        result = test_func()
        assert result == "success"
        assert attempt_count == 3


class TestRequireAuth:
    """Test cases for require_auth decorator."""
    
    def test_with_token(self):
        """Test with valid token."""
        class MockClient:
            token = "valid_token"
            
            @require_auth
            def test_method(self):
                return "success"
        
        client = MockClient()
        result = client.test_method()
        assert result == "success"
    
    def test_without_token(self):
        """Test without token."""
        class MockClient:
            token = None
            
            @require_auth
            def test_method(self):
                return "success"
        
        client = MockClient()
        with pytest.raises(AuthenticationError) as exc_info:
            client.test_method()
        
        assert "Authentication required" in str(exc_info.value)
    
    def test_empty_token(self):
        """Test with empty token."""
        class MockClient:
            token = ""
            
            @require_auth
            def test_method(self):
                return "success"
        
        client = MockClient()
        with pytest.raises(AuthenticationError):
            client.test_method()


class TestValidateResponse:
    """Test cases for validate_response decorator."""
    
    def test_valid_response_with_fields(self):
        """Test validation of response with expected fields."""
        @validate_response(expected_fields=['id', 'name'])
        def test_func():
            return {"id": "123", "name": "test", "extra": "field"}
        
        result = test_func()
        assert result["id"] == "123"
        assert result["name"] == "test"
    
    def test_missing_expected_fields(self):
        """Test validation with missing fields."""
        @validate_response(expected_fields=['id', 'name'])
        def test_func():
            return {"id": "123"}
        
        with pytest.raises(ValidationError) as exc_info:
            test_func()
        
        assert "Missing required fields" in str(exc_info.value)
        assert "name" in str(exc_info.value)
    
    def test_response_object_validation(self):
        """Test validation of response object."""
        @validate_response(expected_fields=['data'], expected_status=200)
        def test_func():
            response = Mock()
            response.status_code = 200
            response.json = Mock(return_value={"data": "test"})
            return response
        
        result = test_func()
        assert result["data"] == "test"
    
    def test_unexpected_status_code(self):
        """Test validation with unexpected status code."""
        @validate_response(expected_status=200)
        def test_func():
            response = Mock()
            response.status_code = 404
            response.json = Mock(return_value={})
            return response
        
        with pytest.raises(ValidationError) as exc_info:
            test_func()
        
        assert "Unexpected status code: 404" in str(exc_info.value)


class TestPaginated:
    """Test cases for paginated decorator."""
    
    def test_single_page(self):
        """Test pagination with single page."""
        @paginated(page_size=10)
        def test_func(limit=10, offset=0):
            return [{"id": i} for i in range(offset, min(offset + limit, 5))]
        
        result = test_func()
        assert len(result) == 5
        assert result[0]["id"] == 0
        assert result[4]["id"] == 4
    
    def test_multiple_pages(self):
        """Test pagination with multiple pages."""
        call_count = 0
        
        @paginated(page_size=3)
        def test_func(limit=3, offset=0):
            nonlocal call_count
            call_count += 1
            
            # Simulate 10 total items
            items = []
            for i in range(offset, min(offset + limit, 10)):
                items.append({"id": i})
            return items
        
        result = test_func()
        assert len(result) == 10
        assert call_count == 4  # 3 + 3 + 3 + 1
        assert result[0]["id"] == 0
        assert result[9]["id"] == 9
    
    def test_max_pages_limit(self):
        """Test pagination with max pages limit."""
        @paginated(page_size=2, max_pages=2)
        def test_func(limit=2, offset=0):
            # Simulate many items
            return [{"id": i} for i in range(offset, offset + limit)]
        
        result = test_func()
        assert len(result) == 4  # 2 pages * 2 items
    
    def test_empty_result(self):
        """Test pagination with empty result."""
        @paginated(page_size=10)
        def test_func(limit=10, offset=0):
            return []
        
        result = test_func()
        assert result == []


class TestRateLimited:
    """Test cases for rate_limited decorator."""
    
    def test_rate_limiting(self):
        """Test basic rate limiting."""
        call_times = []
        
        @rate_limited(calls_per_second=10.0)
        def test_func():
            call_times.append(time.time())
            return "success"
        
        # Make rapid calls
        for _ in range(3):
            test_func()
        
        # Check that calls are spaced appropriately
        if len(call_times) >= 2:
            for i in range(1, len(call_times)):
                time_diff = call_times[i] - call_times[i-1]
                assert time_diff >= 0.09  # Allow small margin for 10 calls/sec
    
    def test_rate_limiting_with_different_instances(self):
        """Test rate limiting with different object instances."""
        class TestClass:
            @rate_limited(calls_per_second=10.0)
            def test_method(self):
                return time.time()
        
        obj1 = TestClass()
        obj2 = TestClass()
        
        # Calls to different instances should not interfere
        time1 = obj1.test_method()
        time2 = obj2.test_method()
        
        # Both calls should succeed immediately
        assert abs(time2 - time1) < 0.1