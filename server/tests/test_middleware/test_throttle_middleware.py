"""
Tests for ThrottleMiddleware.

Tests cover:
- Throttling when disabled
- Pass-through behavior when quota service is unavailable
- API key extraction
- Excluded paths handling
- Delay calculation algorithms
- Usage percentage calculation
- Priority-based delay multipliers
- Quota exceeded (429) responses
- Response headers
- Fail-open behavior on errors
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from middleware.throttle_middleware import ThrottleMiddleware


class TestThrottleMiddlewareDisabled:
    """Tests for when throttling is disabled."""

    def test_pass_through_when_disabled(self):
        """Test that requests pass through when throttling is disabled."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': False
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.json() == {"message": "test"}
        # No throttle headers when disabled
        assert "X-Throttle-Delay" not in response.headers

    def test_pass_through_when_no_quota_service(self):
        """Test that requests pass through when quota service is not available."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'default_quotas': {'daily_limit': 100, 'monthly_limit': 1000}
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        # No quota_service in app.state
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 200
        assert response.json() == {"message": "test"}

    def test_pass_through_when_no_api_key(self):
        """Test that requests without API key pass through."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Create mock quota service
        mock_quota_service = Mock()
        mock_quota_service.enabled = True
        app.state.quota_service = mock_quota_service

        client = TestClient(app)
        # No API key header
        response = client.get("/test")

        assert response.status_code == 200
        # Quota service should not be called
        mock_quota_service.get_quota_config.assert_not_called()


class TestThrottleMiddlewareExcludePaths:
    """Tests for excluded paths functionality."""

    def test_health_endpoint_excluded(self):
        """Test that /health endpoint is excluded from throttling."""
        app = FastAPI()

        config = {
            'security': {
                'rate_limiting': {
                    'exclude_paths': ['/health', '/metrics']
                },
                'throttling': {
                    'enabled': True
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/health")
        def health_endpoint():
            return {"status": "ok"}

        # Create mock quota service
        mock_quota_service = Mock()
        mock_quota_service.enabled = True
        app.state.quota_service = mock_quota_service

        client = TestClient(app)

        # Should not trigger quota service even with API key
        for _ in range(10):
            response = client.get("/health", headers={"X-API-Key": "test-key"})
            assert response.status_code == 200

        # Quota service should not be called for excluded paths
        mock_quota_service.get_quota_config.assert_not_called()

    def test_subpaths_of_excluded_paths(self):
        """Test that subpaths of excluded paths are also excluded."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'exclude_paths': ['/static']
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/static/style.css")
        def static_file():
            return {"content": "css"}

        mock_quota_service = Mock()
        mock_quota_service.enabled = True
        app.state.quota_service = mock_quota_service

        client = TestClient(app)

        response = client.get("/static/style.css", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200
        mock_quota_service.get_quota_config.assert_not_called()


class TestThrottleMiddlewareConfiguration:
    """Tests for middleware configuration."""

    def test_default_configuration(self):
        """Test middleware uses default values when not configured."""
        config = {}

        app = FastAPI()
        middleware = ThrottleMiddleware(app, config)

        assert not middleware.enabled
        assert middleware.default_daily_limit == 10000
        assert middleware.default_monthly_limit == 100000
        assert middleware.min_delay_ms == 100
        assert middleware.max_delay_ms == 5000
        assert middleware.delay_curve == 'exponential'
        assert middleware.threshold_percent == 0.70

    def test_custom_configuration(self):
        """Test middleware uses custom configuration values."""
        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'default_quotas': {
                        'daily_limit': 5000,
                        'monthly_limit': 50000
                    },
                    'delay': {
                        'min_ms': 200,
                        'max_ms': 10000,
                        'curve': 'linear',
                        'threshold_percent': 80
                    },
                    'priority_multipliers': {
                        1: 0.25,
                        5: 1.0,
                        10: 3.0
                    },
                    'exclude_paths': ['/custom'],
                    'headers': {
                        'delay': 'X-Custom-Delay'
                    }
                }
            },
            'api_keys': {
                'header_name': 'X-Custom-Key'
            }
        }

        app = FastAPI()
        middleware = ThrottleMiddleware(app, config)

        assert middleware.enabled
        assert middleware.default_daily_limit == 5000
        assert middleware.default_monthly_limit == 50000
        assert middleware.min_delay_ms == 200
        assert middleware.max_delay_ms == 10000
        assert middleware.delay_curve == 'linear'
        assert middleware.threshold_percent == 0.80
        assert '/custom' in middleware.exclude_paths
        assert middleware.header_delay == 'X-Custom-Delay'
        assert middleware.api_key_header == 'X-Custom-Key'


class TestThrottleMiddlewareDelayCalculation:
    """Tests for delay calculation algorithms."""

    @pytest.fixture
    def middleware(self):
        """Create middleware with test configuration."""
        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {
                        'min_ms': 100,
                        'max_ms': 5000,
                        'curve': 'exponential',
                        'threshold_percent': 70
                    },
                    'priority_multipliers': {
                        1: 0.5,
                        5: 1.0,
                        10: 2.0
                    }
                }
            }
        }
        app = FastAPI()
        return ThrottleMiddleware(app, config)

    def test_no_delay_below_threshold(self, middleware):
        """Test that no delay is applied below threshold."""
        # 50% usage, below 70% threshold
        delay = middleware._calculate_delay(0.50, priority=5)
        assert delay == 0

        # Exactly at threshold boundary (should still be 0)
        delay = middleware._calculate_delay(0.69, priority=5)
        assert delay == 0

    def test_delay_starts_at_threshold(self, middleware):
        """Test that delay starts at threshold."""
        # Just above threshold
        delay = middleware._calculate_delay(0.71, priority=5)
        assert delay > 0

    def test_max_delay_at_full_usage(self, middleware):
        """Test that max delay is applied at 100% usage."""
        delay = middleware._calculate_delay(1.0, priority=5)
        # With exponential curve at 100%, should be at max
        assert delay == middleware.max_delay_ms

    def test_delay_increases_with_usage(self, middleware):
        """Test that delay increases with usage percentage."""
        delay_75 = middleware._calculate_delay(0.75, priority=5)
        delay_85 = middleware._calculate_delay(0.85, priority=5)
        delay_95 = middleware._calculate_delay(0.95, priority=5)

        assert delay_75 < delay_85 < delay_95

    def test_exponential_curve(self, middleware):
        """Test exponential delay curve."""
        # With exponential, delay at 85% should be less than linear interpolation
        delay = middleware._calculate_delay(0.85, priority=5)
        # 85% is 50% through the threshold-to-max range (70% to 100%)
        # Linear would give ~2550ms, exponential gives less due to squared factor
        assert delay < 2600

    def test_linear_curve(self):
        """Test linear delay curve."""
        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {
                        'min_ms': 100,
                        'max_ms': 5000,
                        'curve': 'linear',
                        'threshold_percent': 70
                    }
                }
            }
        }
        app = FastAPI()
        middleware = ThrottleMiddleware(app, config)

        # At 85%, we're 50% through the 70-100% range
        # Linear delay should be: 100 + (5000 - 100) * 0.5 = 2550
        delay = middleware._calculate_delay(0.85, priority=5)
        assert delay == 2550

    def test_priority_multiplier_premium(self, middleware):
        """Test premium priority (1) gets half delay."""
        delay_standard = middleware._calculate_delay(0.85, priority=5)
        delay_premium = middleware._calculate_delay(0.85, priority=1)

        # Premium gets 0.5x delay (int conversion may cause off-by-one)
        assert delay_premium == int(delay_standard * 0.5)

    def test_priority_multiplier_low(self, middleware):
        """Test low priority (10) gets double delay."""
        delay_standard = middleware._calculate_delay(0.85, priority=5)
        delay_low = middleware._calculate_delay(0.85, priority=10)

        assert delay_low == delay_standard * 2

    def test_priority_interpolation(self, middleware):
        """Test priority interpolation for values between defined levels."""
        # Priority 3 should interpolate between 1 (0.5) and 5 (1.0)
        multiplier = middleware._get_priority_multiplier(3)
        assert 0.5 < multiplier < 1.0

        # Priority 7 should interpolate between 5 (1.0) and 10 (2.0)
        multiplier = middleware._get_priority_multiplier(7)
        assert 1.0 < multiplier < 2.0


class TestThrottleMiddlewareUsagePercentage:
    """Tests for usage percentage calculation."""

    @pytest.fixture
    def middleware(self):
        """Create middleware for testing."""
        config = {'security': {'throttling': {'enabled': True}}}
        app = FastAPI()
        return ThrottleMiddleware(app, config)

    def test_daily_limit_only(self, middleware):
        """Test usage percentage with only daily limit."""
        pct = middleware._calculate_usage_percentage(
            daily_used=500, daily_limit=1000,
            monthly_used=5000, monthly_limit=None
        )
        assert pct == 0.5

    def test_monthly_limit_only(self, middleware):
        """Test usage percentage with only monthly limit."""
        pct = middleware._calculate_usage_percentage(
            daily_used=500, daily_limit=None,
            monthly_used=7500, monthly_limit=10000
        )
        assert pct == 0.75

    def test_both_limits_daily_higher(self, middleware):
        """Test that higher percentage is used when both limits exist."""
        pct = middleware._calculate_usage_percentage(
            daily_used=800, daily_limit=1000,   # 80%
            monthly_used=5000, monthly_limit=10000  # 50%
        )
        assert pct == 0.8

    def test_both_limits_monthly_higher(self, middleware):
        """Test that higher percentage is used when both limits exist."""
        pct = middleware._calculate_usage_percentage(
            daily_used=500, daily_limit=1000,   # 50%
            monthly_used=9000, monthly_limit=10000  # 90%
        )
        assert pct == 0.9

    def test_unlimited_quota(self, middleware):
        """Test that unlimited quota returns 0%."""
        pct = middleware._calculate_usage_percentage(
            daily_used=999999, daily_limit=None,
            monthly_used=999999, monthly_limit=None
        )
        assert pct == 0.0

    def test_over_limit(self, middleware):
        """Test usage percentage can exceed 100%."""
        pct = middleware._calculate_usage_percentage(
            daily_used=1500, daily_limit=1000,  # 150%
            monthly_used=5000, monthly_limit=10000
        )
        assert pct == 1.5


class TestThrottleMiddlewareWithQuotaService:
    """Tests for throttling with mock quota service."""

    @pytest.fixture
    def mock_quota_service(self):
        """Create a mock quota service."""
        mock_service = Mock()
        mock_service.enabled = True

        # Default: 50% daily usage, 30% monthly usage
        mock_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'monthly_limit': 10000,
            'throttle_enabled': True,
            'throttle_priority': 5
        })

        mock_service.increment_usage = AsyncMock(return_value=(
            500,    # daily_used
            3000,   # monthly_used
            43200,  # daily_reset_seconds (12 hours)
            1209600  # monthly_reset_seconds (14 days)
        ))

        return mock_service

    @pytest.mark.asyncio
    async def test_throttle_headers_added(self, mock_quota_service):
        """Test that throttle headers are added to responses."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {
                        'min_ms': 100,
                        'max_ms': 5000,
                        'threshold_percent': 70
                    }
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        app.state.quota_service = mock_quota_service

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key-123"})

        assert response.status_code == 200
        assert "X-Throttle-Delay" in response.headers
        assert "X-Quota-Daily-Remaining" in response.headers
        assert "X-Quota-Monthly-Remaining" in response.headers
        assert "X-Quota-Daily-Reset" in response.headers
        assert "X-Quota-Monthly-Reset" in response.headers

        # Verify header values
        assert response.headers["X-Throttle-Delay"] == "0"  # 50% usage, below 70% threshold
        assert response.headers["X-Quota-Daily-Remaining"] == "500"  # 1000 - 500
        assert response.headers["X-Quota-Monthly-Remaining"] == "7000"  # 10000 - 3000

    @pytest.mark.asyncio
    async def test_no_delay_below_threshold(self, mock_quota_service):
        """Test no delay when usage is below threshold."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {'threshold_percent': 70}
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # 50% usage - below 70% threshold
        app.state.quota_service = mock_quota_service

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 200
        assert response.headers["X-Throttle-Delay"] == "0"

    @pytest.mark.asyncio
    async def test_delay_above_threshold(self, mock_quota_service):
        """Test delay applied when usage exceeds threshold."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {
                        'min_ms': 100,
                        'max_ms': 5000,
                        'threshold_percent': 70
                    }
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # 85% daily usage - above 70% threshold
        mock_quota_service.increment_usage = AsyncMock(return_value=(
            850, 3000, 43200, 1209600
        ))
        app.state.quota_service = mock_quota_service

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 200
        delay = int(response.headers["X-Throttle-Delay"])
        assert delay > 0

    @pytest.mark.asyncio
    async def test_throttling_disabled_for_key(self, mock_quota_service):
        """Test that throttling can be disabled per-key."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Throttling disabled for this key
        mock_quota_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'monthly_limit': 10000,
            'throttle_enabled': False,  # Disabled
            'throttle_priority': 5
        })
        app.state.quota_service = mock_quota_service

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 200
        # No throttle headers when disabled for key
        assert "X-Throttle-Delay" not in response.headers
        # increment_usage should not be called when throttle is disabled
        mock_quota_service.increment_usage.assert_not_called()


class TestThrottleMiddlewareQuotaExceeded:
    """Tests for quota exceeded (429) responses."""

    @pytest.fixture
    def mock_quota_service_exceeded(self):
        """Create mock quota service with exceeded quota."""
        mock_service = Mock()
        mock_service.enabled = True

        mock_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'monthly_limit': 10000,
            'throttle_enabled': True,
            'throttle_priority': 5
        })

        return mock_service

    @pytest.mark.asyncio
    async def test_daily_quota_exceeded(self, mock_quota_service_exceeded):
        """Test 429 response when daily quota is exceeded."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Daily usage exceeds limit
        mock_quota_service_exceeded.increment_usage = AsyncMock(return_value=(
            1001,   # daily_used > daily_limit
            5000,   # monthly_used
            43200,  # daily_reset_seconds
            1209600  # monthly_reset_seconds
        ))
        app.state.quota_service = mock_quota_service_exceeded

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 429
        data = response.json()
        assert "Quota exceeded" in data["detail"]
        assert data["quota_exceeded"] == "daily"
        assert data["daily_remaining"] == 0

    @pytest.mark.asyncio
    async def test_monthly_quota_exceeded(self, mock_quota_service_exceeded):
        """Test 429 response when monthly quota is exceeded."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Monthly usage exceeds limit
        mock_quota_service_exceeded.increment_usage = AsyncMock(return_value=(
            500,    # daily_used
            10001,  # monthly_used > monthly_limit
            43200,  # daily_reset_seconds
            1209600  # monthly_reset_seconds
        ))
        app.state.quota_service = mock_quota_service_exceeded

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 429
        data = response.json()
        assert "Quota exceeded" in data["detail"]
        assert data["quota_exceeded"] == "monthly"
        assert data["monthly_remaining"] == 0

    @pytest.mark.asyncio
    async def test_quota_headers_on_429(self, mock_quota_service_exceeded):
        """Test that quota headers are present on 429 response."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        mock_quota_service_exceeded.increment_usage = AsyncMock(return_value=(
            1001, 5000, 43200, 1209600
        ))
        app.state.quota_service = mock_quota_service_exceeded

        client = TestClient(app)
        response = client.get("/test", headers={"X-API-Key": "test-key"})

        assert response.status_code == 429
        assert "X-Throttle-Delay" in response.headers
        assert "X-Quota-Daily-Remaining" in response.headers
        assert "X-Quota-Daily-Reset" in response.headers


class TestThrottleMiddlewareFailOpen:
    """Tests for fail-open behavior on errors."""

    @pytest.mark.asyncio
    async def test_quota_service_error_allows_request(self):
        """Test that quota service errors result in allowing the request."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        # Create a mock quota service that raises errors
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_quota_config = AsyncMock(
            side_effect=Exception("Database connection error")
        )
        app.state.quota_service = mock_service

        client = TestClient(app)

        # Request should succeed despite quota service error
        response = client.get("/test", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_increment_error_allows_request(self):
        """Test that increment errors result in allowing the request."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'throttle_enabled': True,
            'throttle_priority': 5
        })
        mock_service.increment_usage = AsyncMock(
            side_effect=Exception("Redis connection error")
        )
        app.state.quota_service = mock_service

        client = TestClient(app)

        # Request should succeed despite Redis error
        response = client.get("/test", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_quota_service_disabled_allows_request(self):
        """Test handling when quota service exists but is disabled."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {'enabled': True}
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        mock_service = Mock()
        mock_service.enabled = False  # Disabled
        app.state.quota_service = mock_service

        client = TestClient(app)

        response = client.get("/test", headers={"X-API-Key": "test-key"})
        assert response.status_code == 200


class TestThrottleMiddlewarePriorityMultipliers:
    """Tests for priority-based delay multipliers."""

    @pytest.fixture
    def app_with_quota_service(self):
        """Create app with mock quota service."""
        app = FastAPI()

        config = {
            'security': {
                'throttling': {
                    'enabled': True,
                    'delay': {
                        'min_ms': 100,
                        'max_ms': 5000,
                        'curve': 'linear',
                        'threshold_percent': 70
                    },
                    'priority_multipliers': {
                        1: 0.5,
                        5: 1.0,
                        10: 2.0
                    }
                }
            }
        }

        app.add_middleware(ThrottleMiddleware, config=config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        return app

    @pytest.mark.asyncio
    async def test_premium_priority_less_delay(self, app_with_quota_service):
        """Test that premium priority (1) gets less delay."""
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'monthly_limit': None,
            'throttle_enabled': True,
            'throttle_priority': 1  # Premium
        })
        mock_service.increment_usage = AsyncMock(return_value=(
            850, 0, 43200, 1209600  # 85% daily usage
        ))
        app_with_quota_service.state.quota_service = mock_service

        client = TestClient(app_with_quota_service)
        response = client.get("/test", headers={"X-API-Key": "premium-key"})

        assert response.status_code == 200
        delay = int(response.headers["X-Throttle-Delay"])
        # Premium should get 0.5x delay
        # At 85% with linear curve: base = 100 + (5000-100)*0.5 = 2550
        # With 0.5x multiplier: 1275
        assert delay == 1275

    @pytest.mark.asyncio
    async def test_low_priority_more_delay(self, app_with_quota_service):
        """Test that low priority (10) gets more delay."""
        mock_service = Mock()
        mock_service.enabled = True
        mock_service.get_quota_config = AsyncMock(return_value={
            'daily_limit': 1000,
            'monthly_limit': None,
            'throttle_enabled': True,
            'throttle_priority': 10  # Low priority
        })
        mock_service.increment_usage = AsyncMock(return_value=(
            850, 0, 43200, 1209600  # 85% daily usage
        ))
        app_with_quota_service.state.quota_service = mock_service

        client = TestClient(app_with_quota_service)
        response = client.get("/test", headers={"X-API-Key": "low-priority-key"})

        assert response.status_code == 200
        delay = int(response.headers["X-Throttle-Delay"])
        # Low priority should get 2.0x delay
        # At 85% with linear curve: base = 100 + (5000-100)*0.5 = 2550
        # With 2.0x multiplier: 5100
        assert delay == 5100
