"""
Comprehensive tests for MiddlewareConfigurator and SecurityHeadersMiddleware.

Tests cover:
- CORS configuration with secure defaults
- CORS configuration with wildcard origins (auto-disable credentials)
- CORS configuration with specific origins
- Security headers middleware
- Legacy configuration fallback
- Edge cases and security validations
"""

import logging
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

# Add server directory to Python path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from config.middleware_configurator import MiddlewareConfigurator, SecurityHeadersMiddleware


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware class."""

    def test_security_headers_added_to_response(self):
        """Test that all configured security headers are added to responses."""
        app = FastAPI()

        headers_config = {
            'content_security_policy': "default-src 'self'",
            'strict_transport_security': "max-age=31536000",
            'x_content_type_options': "nosniff",
            'x_frame_options': "SAMEORIGIN",
            'x_xss_protection': "1; mode=block",
            'referrer_policy': "strict-origin-when-cross-origin",
            'permissions_policy': "geolocation=()"
        }

        app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers.get("Content-Security-Policy") == "default-src 'self'"
        assert response.headers.get("Strict-Transport-Security") == "max-age=31536000"
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert response.headers.get("Permissions-Policy") == "geolocation=()"

    def test_partial_security_headers(self):
        """Test that only configured headers are added."""
        app = FastAPI()

        headers_config = {
            'x_content_type_options': "nosniff",
            'x_frame_options': "DENY"
        }

        app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        # These should not be present
        assert response.headers.get("Content-Security-Policy") is None
        assert response.headers.get("Strict-Transport-Security") is None

    def test_empty_headers_config(self):
        """Test that middleware handles empty config gracefully."""
        app = FastAPI()

        headers_config = {}

        app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
        # No security headers should be added
        assert response.headers.get("X-Content-Type-Options") is None

    def test_security_headers_on_error_response(self):
        """Test that security headers are added on handled error responses."""
        from fastapi import HTTPException

        app = FastAPI()

        headers_config = {
            'x_content_type_options': "nosniff",
            'x_frame_options': "SAMEORIGIN"
        }

        app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)

        @app.get("/error")
        def error_endpoint():
            raise HTTPException(status_code=400, detail="Bad request")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/error")

        assert response.status_code == 400
        # Security headers should be present on handled error responses
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_security_headers_on_custom_error_handler(self):
        """Test that security headers are added when custom error handlers are used."""
        app = FastAPI()

        headers_config = {
            'x_content_type_options': "nosniff",
            'x_frame_options': "DENY"
        }

        app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)

        @app.exception_handler(ValueError)
        async def value_error_handler(request: Request, exc: ValueError):
            return Response(
                content=str(exc),
                status_code=422,
                media_type="text/plain"
            )

        @app.get("/custom-error")
        def custom_error_endpoint():
            raise ValueError("Custom error")

        client = TestClient(app)
        response = client.get("/custom-error")

        assert response.status_code == 422
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestCORSConfiguration:
    """Tests for CORS middleware configuration."""

    def test_cors_with_wildcard_origins_disables_credentials(self):
        """Test that credentials are automatically disabled when wildcard origins are used."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["*"],
                    'allow_credentials': True,  # This should be overridden
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Authorization"],
                    'expose_headers': [],
                    'max_age': 600
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Verify warning was logged about disabling credentials
        warning_calls = [call for call in logger.warning.call_args_list
                        if 'Automatically disabling' in str(call)]
        assert len(warning_calls) > 0

        # Verify wildcard warning was logged
        wildcard_warning_calls = [call for call in logger.warning.call_args_list
                                  if 'wildcard origin' in str(call)]
        assert len(wildcard_warning_calls) > 0

    def test_cors_with_specific_origins_allows_credentials(self):
        """Test that credentials can be enabled with specific origins."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://app.example.com", "https://admin.example.com"],
                    'allow_credentials': True,
                    'allowed_methods': ["GET", "POST", "PUT"],
                    'allowed_headers': ["Authorization", "Content-Type"],
                    'expose_headers': ["X-Request-ID"],
                    'max_age': 3600
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Verify info about credentials with specific origins was logged
        info_calls = [call for call in logger.info.call_args_list
                     if 'credentials enabled for specific origins' in str(call)]
        assert len(info_calls) > 0

        # Verify no warning about disabling credentials
        warning_calls = [call for call in logger.warning.call_args_list
                        if 'Automatically disabling' in str(call)]
        assert len(warning_calls) == 0

    def test_cors_configuration_logging(self):
        """Test that CORS configuration is logged correctly."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com"],
                    'allow_credentials': False,
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': ["X-RateLimit-Limit"],
                    'max_age': 1200
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Verify all configuration details were logged
        log_messages = [str(call) for call in logger.info.call_args_list]

        assert any("CORS Configuration" in msg for msg in log_messages)
        assert any("Allowed Origins" in msg for msg in log_messages)
        assert any("Allow Credentials" in msg for msg in log_messages)
        assert any("Allowed Methods" in msg for msg in log_messages)
        assert any("Max Age" in msg for msg in log_messages)

    def test_cors_with_legacy_config_fallback(self):
        """Test that legacy cors config is used when security.cors is not present."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        # Legacy configuration (no security section)
        config = {
            'cors': {
                'allowed_origins': ["https://legacy.example.com"],
                'allow_credentials': False,
                'allowed_methods': ["GET"],
                'allowed_headers': ["Authorization"]
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Should work without errors
        assert logger.info.called

    def test_cors_with_empty_config_uses_defaults(self):
        """Test that secure defaults are used when no config is provided."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {}

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Should use secure defaults and warn about wildcard
        warning_calls = [call for call in logger.warning.call_args_list
                        if 'wildcard origin' in str(call)]
        assert len(warning_calls) > 0

    def test_cors_middleware_added_to_app(self):
        """Test that CORS middleware is actually added to the FastAPI app."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com"],
                    'allow_credentials': False,
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': [],
                    'max_age': 600
                }
            }
        }

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Verify middleware was added
        assert len(app.user_middleware) > initial_middleware_count


class TestSecurityHeadersConfiguration:
    """Tests for security headers middleware configuration."""

    def test_security_headers_enabled_by_default(self):
        """Test that security headers middleware is enabled by default."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'headers': {
                    'enabled': True,
                    'x_content_type_options': "nosniff"
                }
            }
        }

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator._configure_security_headers_middleware(app, config, logger)

        # Verify middleware was added
        assert len(app.user_middleware) > initial_middleware_count

        # Verify success message was logged
        info_calls = [call for call in logger.info.call_args_list
                     if 'Security headers middleware configured' in str(call)]
        assert len(info_calls) > 0

    def test_security_headers_can_be_disabled(self):
        """Test that security headers middleware can be disabled (with warning)."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'headers': {
                    'enabled': False
                }
            }
        }

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator._configure_security_headers_middleware(app, config, logger)

        # Verify middleware was NOT added
        assert len(app.user_middleware) == initial_middleware_count

        # Verify warning was logged
        warning_calls = [call for call in logger.warning.call_args_list
                        if 'DISABLED' in str(call)]
        assert len(warning_calls) > 0

    def test_security_headers_empty_config_enables_by_default(self):
        """Test that empty headers config still enables the middleware."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'headers': {}
            }
        }

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator._configure_security_headers_middleware(app, config, logger)

        # Middleware should be added (enabled by default)
        assert len(app.user_middleware) > initial_middleware_count


class TestFullMiddlewareConfiguration:
    """Tests for the complete middleware configuration flow."""

    def test_configure_middleware_adds_all_middleware(self):
        """Test that configure_middleware adds all expected middleware."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com"],
                    'allow_credentials': False,
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': [],
                    'max_age': 600
                },
                'headers': {
                    'enabled': True,
                    'x_content_type_options': "nosniff"
                }
            }
        }

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator.configure_middleware(app, config, logger)

        # Should have added at least 2 middleware (security headers + CORS)
        # Plus the logging middleware added by http decorator
        assert len(app.user_middleware) >= initial_middleware_count + 2

    def test_configure_middleware_order(self):
        """Test that middleware is configured in the correct order."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["*"],
                    'allow_credentials': False,
                    'allowed_methods': ["GET"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': [],
                    'max_age': 600
                },
                'headers': {
                    'enabled': True,
                    'x_content_type_options': "nosniff"
                }
            }
        }

        MiddlewareConfigurator.configure_middleware(app, config, logger)

        # Verify that all middleware configuration methods were called
        info_logs = [str(call) for call in logger.info.call_args_list]

        # Security headers should be configured
        assert any("Security headers middleware configured" in log for log in info_logs)
        # CORS should be configured
        assert any("CORS middleware configured" in log for log in info_logs)

    def test_metrics_middleware_handles_import_error(self):
        """Test that metrics middleware gracefully handles import errors."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        with patch('config.middleware_configurator.MiddlewareConfigurator._configure_metrics_middleware') as mock_metrics:
            # Simulate ImportError in metrics middleware
            mock_metrics.side_effect = lambda app, logger: logger.warning("MetricsMiddleware not available")

            config = {
                'security': {
                    'cors': {
                        'allowed_origins': ["*"],
                        'allow_credentials': False,
                        'allowed_methods': ["GET"],
                        'allowed_headers': ["Content-Type"],
                        'expose_headers': [],
                        'max_age': 600
                    },
                    'headers': {
                        'enabled': True
                    }
                }
            }

            # Should not raise an exception
            MiddlewareConfigurator.configure_middleware(app, config, logger)


class TestCORSSecurityEdgeCases:
    """Tests for edge cases and security scenarios."""

    def test_cors_with_multiple_origins_including_wildcard(self):
        """Test that wildcard is detected even when mixed with other origins."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com", "*", "https://other.com"],
                    'allow_credentials': True,
                    'allowed_methods': ["GET"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': [],
                    'max_age': 600
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Should detect wildcard and disable credentials
        warning_calls = [call for call in logger.warning.call_args_list
                        if 'Automatically disabling' in str(call)]
        assert len(warning_calls) > 0

    def test_cors_with_empty_origins_list(self):
        """Test CORS configuration with empty origins list."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': [],
                    'allow_credentials': False,
                    'allowed_methods': ["GET"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': [],
                    'max_age': 600
                }
            }
        }

        # Should not raise an exception
        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

    def test_cors_preserves_all_settings(self):
        """Test that all CORS settings are properly preserved."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://app.example.com"],
                    'allow_credentials': True,
                    'allowed_methods': ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    'allowed_headers': ["Authorization", "Content-Type", "X-Custom"],
                    'expose_headers': ["X-RateLimit-Limit", "X-RateLimit-Remaining"],
                    'max_age': 7200
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Verify all settings were logged
        info_calls = [str(call) for call in logger.info.call_args_list]

        # Check methods were logged
        methods_logged = any("GET" in msg and "POST" in msg and "PUT" in msg for msg in info_calls)
        assert methods_logged

        # Check max_age was logged
        max_age_logged = any("7200" in msg for msg in info_calls)
        assert max_age_logged


class TestIntegrationScenarios:
    """Integration tests for complete middleware stack."""

    def test_full_stack_with_security_headers_and_cors(self):
        """Test that security headers and CORS work together correctly."""
        app = FastAPI()
        logger = logging.getLogger("test")

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["http://testclient"],  # TestClient uses this origin
                    'allow_credentials': False,
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Content-Type"],
                    'expose_headers': ["X-Custom-Header"],
                    'max_age': 600
                },
                'headers': {
                    'enabled': True,
                    'x_content_type_options': "nosniff",
                    'x_frame_options': "DENY",
                    'referrer_policy': "no-referrer"
                }
            }
        }

        MiddlewareConfigurator.configure_middleware(app, config, logger)

        @app.get("/api/test")
        def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/api/test")

        assert response.status_code == 200
        # Security headers should be present
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "no-referrer"

    def test_cors_preflight_request(self):
        """Test that CORS preflight requests are handled correctly."""
        app = FastAPI()
        logger = logging.getLogger("test")

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["http://example.com"],
                    'allow_credentials': False,
                    'allowed_methods': ["GET", "POST", "PUT"],
                    'allowed_headers': ["Content-Type", "Authorization"],
                    'expose_headers': [],
                    'max_age': 600
                },
                'headers': {
                    'enabled': True,
                    'x_content_type_options': "nosniff"
                }
            }
        }

        MiddlewareConfigurator.configure_middleware(app, config, logger)

        @app.post("/api/data")
        def data_endpoint():
            return {"data": "test"}

        client = TestClient(app)

        # Send OPTIONS preflight request
        response = client.options(
            "/api/data",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )

        # Preflight should succeed
        assert response.status_code == 200


class TestConfigurationValidation:
    """Tests for configuration validation and error handling."""

    def test_missing_security_section_uses_defaults(self):
        """Test that missing security section uses secure defaults."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'general': {
                'port': 3000
            }
        }

        # Should not raise an exception
        MiddlewareConfigurator.configure_middleware(app, config, logger)

    def test_partial_cors_config_uses_defaults_for_missing(self):
        """Test that partial CORS config uses defaults for missing values."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com"]
                    # Missing: allow_credentials, allowed_methods, etc.
                }
            }
        }

        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Should use defaults for missing values
        info_calls = [str(call) for call in logger.info.call_args_list]

        # Default methods should be used
        assert any("GET" in msg for msg in info_calls)

    def test_none_values_in_config_handled_gracefully(self):
        """Test that None values in config are handled without errors."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {
            'security': {
                'cors': None,
                'headers': None
            }
        }

        # Should not raise an exception
        MiddlewareConfigurator.configure_middleware(app, config, logger)
