"""
Tests for RateLimitMiddleware.

Tests cover:
- Rate limiting when Redis is enabled
- Pass-through behavior when Redis is disabled
- IP-based rate limiting
- API key rate limiting
- Excluded paths handling
- Rate limit headers in responses
- 429 response when limits exceeded
"""

import pytest
import time
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from middleware.rate_limit_middleware import RateLimitMiddleware


class TestRateLimitMiddlewareDisabled:
    """Tests for when rate limiting is disabled."""

    def test_pass_through_when_disabled(self):
        """Test that requests pass through when rate limiting is disabled."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json() == {"message": "test"}
        # No rate limit headers when disabled
        assert "X-RateLimit-Limit" not in response.headers

    def test_pass_through_when_no_redis_service(self):
        """Test that requests pass through when Redis service is not available."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 10, 'requests_per_hour': 100}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        client = TestClient(app)
        # No redis_service in app.state
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json() == {"message": "test"}


class TestRateLimitMiddlewareExcludePaths:
    """Tests for excluded paths functionality."""

    def test_health_endpoint_excluded(self):
        """Test that /health endpoint is excluded from rate limiting."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'exclude_paths': ['/health', '/metrics'],
                    'ip_limits': {'requests_per_minute': 1, 'requests_per_hour': 1}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/health")
        def health_endpoint():
            return {"status": "ok"}
        
        client = TestClient(app)
        
        # Should not be rate limited even with very low limits
        for _ in range(10):
            response = client.get("/health")
            assert response.status_code == 200

    def test_metrics_endpoint_excluded(self):
        """Test that /metrics endpoint is excluded from rate limiting."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'exclude_paths': ['/health', '/metrics'],
                    'ip_limits': {'requests_per_minute': 1, 'requests_per_hour': 1}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/metrics")
        def metrics_endpoint():
            return {"metrics": []}
        
        client = TestClient(app)
        
        for _ in range(10):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_subpaths_of_excluded_paths(self):
        """Test that subpaths of excluded paths are also excluded."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'exclude_paths': ['/static'],
                    'ip_limits': {'requests_per_minute': 1, 'requests_per_hour': 1}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/static/style.css")
        def static_file():
            return {"content": "css"}
        
        client = TestClient(app)
        
        for _ in range(10):
            response = client.get("/static/style.css")
            assert response.status_code == 200


class TestRateLimitMiddlewareConfiguration:
    """Tests for middleware configuration."""

    def test_default_configuration(self):
        """Test middleware uses default values when not configured."""
        config = {}
        
        # This should not raise an error
        app = FastAPI()
        middleware = RateLimitMiddleware(app, config)
        
        assert middleware.enabled == False
        assert middleware.ip_requests_per_minute == 60
        assert middleware.ip_requests_per_hour == 1000

    def test_custom_configuration(self):
        """Test middleware uses custom configuration values."""
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {
                        'requests_per_minute': 100,
                        'requests_per_hour': 2000
                    },
                    'api_key_limits': {
                        'requests_per_minute': 200,
                        'requests_per_hour': 10000
                    },
                    'exclude_paths': ['/custom', '/exclude'],
                    'retry_after_seconds': 120
                }
            },
            'api_keys': {
                'header_name': 'X-Custom-Key'
            }
        }
        
        app = FastAPI()
        middleware = RateLimitMiddleware(app, config)
        
        assert middleware.enabled == True
        assert middleware.ip_requests_per_minute == 100
        assert middleware.ip_requests_per_hour == 2000
        assert middleware.api_key_requests_per_minute == 200
        assert middleware.api_key_requests_per_hour == 10000
        assert '/custom' in middleware.exclude_paths
        assert '/exclude' in middleware.exclude_paths
        assert middleware.retry_after_seconds == 120
        assert middleware.api_key_header == 'X-Custom-Key'


class TestRateLimitMiddlewareClientIP:
    """Tests for client IP extraction with proxy trust controls."""

    def test_proxy_headers_ignored_by_default(self):
        """Test that proxy headers are ignored when trust_proxy_headers is False (default)."""
        app = FastAPI()
        config = {'security': {'rate_limiting': {'enabled': False}}}
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18"}
        mock_request.client = Mock(host="10.0.0.1")

        # Should return direct IP, not the spoofed X-Forwarded-For
        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"

    def test_proxy_headers_trusted_when_enabled(self):
        """Test IP extraction from X-Forwarded-For when trust_proxy_headers is True."""
        app = FastAPI()
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False,
                    'trust_proxy_headers': True
                }
            }
        }
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
        mock_request.client = Mock(host="10.0.0.1")

        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.195"

    def test_x_real_ip_trusted_when_enabled(self):
        """Test IP extraction from X-Real-IP when trust_proxy_headers is True."""
        app = FastAPI()
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False,
                    'trust_proxy_headers': True
                }
            }
        }
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {"X-Real-IP": "203.0.113.195"}
        mock_request.client = Mock(host="10.0.0.1")

        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.195"

    def test_trusted_proxies_allows_trusted_ip(self):
        """Test that proxy headers are accepted from trusted proxy IPs."""
        app = FastAPI()
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False,
                    'trust_proxy_headers': True,
                    'trusted_proxies': ['10.0.0.0/8']
                }
            }
        }
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "203.0.113.195"}
        mock_request.client = Mock(host="10.0.0.1")  # Trusted proxy

        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.195"

    def test_trusted_proxies_rejects_untrusted_ip(self):
        """Test that proxy headers are ignored from untrusted IPs."""
        app = FastAPI()
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False,
                    'trust_proxy_headers': True,
                    'trusted_proxies': ['10.0.0.0/8']
                }
            }
        }
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "203.0.113.195"}
        mock_request.client = Mock(host="192.168.1.100")  # Not in trusted range

        # Should return direct IP, not the X-Forwarded-For from untrusted source
        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_extract_ip_from_client_direct(self):
        """Test IP extraction from request.client when no proxy headers."""
        app = FastAPI()
        config = {'security': {'rate_limiting': {'enabled': False}}}
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = Mock(host="192.168.1.100")

        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_extract_ip_unknown_fallback(self):
        """Test IP extraction falls back to 'unknown' when no client info."""
        app = FastAPI()
        config = {'security': {'rate_limiting': {'enabled': False}}}
        middleware = RateLimitMiddleware(app, config)

        mock_request = Mock()
        mock_request.headers = {}
        mock_request.client = None

        ip = middleware._get_client_ip(mock_request)
        assert ip == "unknown"

    def test_trusted_proxies_with_single_ip(self):
        """Test trusted proxies with a single IP address."""
        app = FastAPI()
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': False,
                    'trust_proxy_headers': True,
                    'trusted_proxies': ['127.0.0.1']
                }
            }
        }
        middleware = RateLimitMiddleware(app, config)

        # From trusted localhost
        mock_request = Mock()
        mock_request.headers = {"X-Forwarded-For": "8.8.8.8"}
        mock_request.client = Mock(host="127.0.0.1")
        assert middleware._get_client_ip(mock_request) == "8.8.8.8"

        # From untrusted IP
        mock_request.client = Mock(host="1.2.3.4")
        assert middleware._get_client_ip(mock_request) == "1.2.3.4"


class TestRateLimitMiddlewareWithRedis:
    """Tests for rate limiting with Redis mock."""

    @pytest.fixture
    def mock_redis_service(self):
        """Create a mock Redis service with counter tracking."""
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.initialized = True

        # Track counters for testing
        counters = {}

        async def mock_script_call(keys, args):
            """Mock registered Lua script execution - atomic INCR with EXPIRE."""
            key = keys[0]
            counters[key] = counters.get(key, 0) + 1
            return counters[key]

        # Create a mock registered script that behaves like a callable
        mock_script = AsyncMock(side_effect=mock_script_call)

        mock_service.client = Mock()
        mock_service.client.register_script = Mock(return_value=mock_script)
        mock_service._counters = counters  # Expose for testing

        return mock_service

    @pytest.mark.asyncio
    async def test_rate_limit_headers_added(self, mock_redis_service):
        """Test that rate limit headers are added to responses."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 60, 'requests_per_hour': 1000}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        # Inject mock redis service
        app.state.redis_service = mock_redis_service
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        
        # Verify header values
        assert response.headers["X-RateLimit-Limit"] == "60"
        remaining = int(response.headers["X-RateLimit-Remaining"])
        assert remaining == 59  # 60 - 1 request

    @pytest.mark.asyncio
    async def test_ip_rate_limit_exceeded(self, mock_redis_service):
        """Test 429 response when IP rate limit is exceeded."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 2, 'requests_per_hour': 100},
                    'retry_after_seconds': 30
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        app.state.redis_service = mock_redis_service
        
        client = TestClient(app)
        
        # First two requests should succeed
        response1 = client.get("/test")
        assert response1.status_code == 200
        
        response2 = client.get("/test")
        assert response2.status_code == 200
        
        # Third request should be rate limited
        response3 = client.get("/test")
        assert response3.status_code == 429
        assert "Rate limit exceeded" in response3.json()["detail"]
        assert response3.json()["retry_after"] == 30
        assert response3.headers["Retry-After"] == "30"

    @pytest.mark.asyncio
    async def test_api_key_gets_higher_limits(self, mock_redis_service):
        """Test that requests with API key get higher rate limits."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 2, 'requests_per_hour': 100},
                    'api_key_limits': {'requests_per_minute': 5, 'requests_per_hour': 500}
                }
            },
            'api_keys': {
                'header_name': 'X-API-Key'
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        app.state.redis_service = mock_redis_service
        
        client = TestClient(app)
        
        # Requests with API key should use higher limits
        headers = {"X-API-Key": "test-api-key-123"}
        
        # Should get API key limit in headers
        response = client.get("/test", headers=headers)
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "5"  # API key limit

    @pytest.mark.asyncio
    async def test_both_ip_and_api_key_checked(self, mock_redis_service):
        """Test that both IP and API key limits are checked."""
        app = FastAPI()

        # Set low limits for both
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 10, 'requests_per_hour': 100},
                    'api_key_limits': {'requests_per_minute': 2, 'requests_per_hour': 50}
                }
            },
            'api_keys': {
                'header_name': 'X-API-Key'
            }
        }

        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        app.state.redis_service = mock_redis_service

        client = TestClient(app)
        headers = {"X-API-Key": "test-api-key-123"}

        # First two requests should succeed
        response1 = client.get("/test", headers=headers)
        assert response1.status_code == 200

        response2 = client.get("/test", headers=headers)
        assert response2.status_code == 200

        # Third request should hit API key limit (lower than IP limit)
        response3 = client.get("/test", headers=headers)
        assert response3.status_code == 429

    @pytest.mark.asyncio
    async def test_hour_limit_exceeded(self, mock_redis_service):
        """Test 429 response when hour limit is exceeded while minute limit is OK."""
        app = FastAPI()

        # High minute limit, low hour limit
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 100, 'requests_per_hour': 2},
                    'retry_after_seconds': 60
                }
            }
        }

        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        app.state.redis_service = mock_redis_service

        client = TestClient(app)

        # First two requests should succeed (within hour limit)
        response1 = client.get("/test")
        assert response1.status_code == 200

        response2 = client.get("/test")
        assert response2.status_code == 200

        # Third request should hit hour limit (minute limit is 100, hour limit is 2)
        response3 = client.get("/test")
        assert response3.status_code == 429
        assert "Rate limit exceeded" in response3.json()["detail"]
        assert response3.headers["Retry-After"] == "60"


class TestRateLimitMiddlewareRedisFailure:
    """Tests for graceful handling of Redis failures."""

    @pytest.mark.asyncio
    async def test_redis_error_allows_request(self):
        """Test that Redis errors result in allowing the request (fail-open)."""
        app = FastAPI()

        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 1, 'requests_per_hour': 1}
                }
            }
        }

        app.add_middleware(RateLimitMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Create a mock Redis service that raises errors when script is called
        mock_script = AsyncMock(side_effect=Exception("Redis connection error"))
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.initialized = True
        mock_service.client = Mock()
        mock_service.client.register_script = Mock(return_value=mock_script)

        app.state.redis_service = mock_service

        client = TestClient(app)

        # Request should succeed despite Redis error
        response = client.get("/test")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_redis_not_initialized(self):
        """Test handling when Redis service exists but is not initialized."""
        app = FastAPI()
        
        config = {
            'security': {
                'rate_limiting': {
                    'enabled': True,
                    'ip_limits': {'requests_per_minute': 1, 'requests_per_hour': 1}
                }
            }
        }
        
        app.add_middleware(RateLimitMiddleware, config=config)
        
        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}
        
        # Create a mock Redis service that is not initialized and fails to initialize
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.initialized = False
        mock_service.initialize = AsyncMock(side_effect=Exception("Failed to connect"))
        
        app.state.redis_service = mock_service
        
        client = TestClient(app)
        
        # Request should succeed even when Redis fails to initialize
        response = client.get("/test")
        assert response.status_code == 200

