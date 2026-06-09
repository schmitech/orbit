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

_CONFIGURATOR_LOGGER = "config.middleware_configurator"


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

        app.add_middleware(
            SecurityHeadersMiddleware,
            headers_config=headers_config,
            https_enabled=True,
        )

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
        assert response.headers.get("Content-Security-Policy") is None
        assert response.headers.get("Strict-Transport-Security") is None

    def test_empty_headers_config(self):
        """Test that middleware handles empty config gracefully."""
        app = FastAPI()

        app.add_middleware(SecurityHeadersMiddleware, headers_config={})

        @app.get("/test")
        def test_endpoint():
            return {"message": "test"}

        client = TestClient(app)
        response = client.get("/test")

        assert response.status_code == 200
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
            return Response(content=str(exc), status_code=422, media_type="text/plain")

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

    def test_cors_with_wildcard_origins_disables_credentials(self, caplog):
        """Test that credentials are automatically disabled when wildcard origins are used."""
        app = FastAPI()

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["*"],
                    'allow_credentials': True,
                    'allowed_methods': ["GET", "POST"],
                    'allowed_headers': ["Authorization"],
                    'expose_headers': [],
                    'max_age': 600
                }
            }
        }

        with caplog.at_level(logging.WARNING, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        assert any("Automatically disabling" in r.message for r in caplog.records)
        assert any("wildcard origin" in r.message for r in caplog.records)

    def test_cors_with_specific_origins_allows_credentials(self, caplog):
        """Test that credentials can be enabled with specific origins."""
        app = FastAPI()

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

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        assert any("credentials enabled for specific origins" in r.message for r in caplog.records)
        assert not any("Automatically disabling" in r.message for r in caplog.records)

    def test_cors_configuration_logging(self, caplog):
        """Test that CORS configuration details are logged."""
        app = FastAPI()

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

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        messages = [r.message for r in caplog.records]
        assert any("CORS Configuration" in m for m in messages)
        assert any("Allowed Origins" in m for m in messages)
        assert any("Allow Credentials" in m for m in messages)
        assert any("Allowed Methods" in m for m in messages)
        assert any("Max Age" in m for m in messages)

    def test_cors_with_legacy_config_fallback(self, caplog):
        """Test that legacy cors config is used when security.cors is not present."""
        app = FastAPI()

        config = {
            'cors': {
                'allowed_origins': ["https://legacy.example.com"],
                'allow_credentials': False,
                'allowed_methods': ["GET"],
                'allowed_headers': ["Authorization"]
            }
        }

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        assert any(r.levelno == logging.INFO for r in caplog.records)

    def test_cors_with_empty_config_uses_defaults(self, caplog):
        """Test that secure defaults are used when no config is provided."""
        app = FastAPI()

        with caplog.at_level(logging.WARNING, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, {})

        assert any("wildcard origin" in r.message for r in caplog.records)

    def test_cors_middleware_added_to_app(self):
        """Test that CORS middleware is actually added to the FastAPI app."""
        app = FastAPI()

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
        MiddlewareConfigurator._configure_cors_middleware(app, config)

        assert len(app.user_middleware) > initial_middleware_count


class TestSecurityHeadersConfiguration:
    """Tests for security headers middleware configuration."""

    def test_security_headers_enabled_by_default(self, caplog):
        """Test that security headers middleware is enabled by default."""
        app = FastAPI()

        config = {'security': {'headers': {'enabled': True, 'x_content_type_options': "nosniff"}}}

        initial_middleware_count = len(app.user_middleware)

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_security_headers_middleware(app, config)

        assert len(app.user_middleware) > initial_middleware_count
        assert any("Security headers middleware configured" in r.message for r in caplog.records)

    def test_security_headers_can_be_disabled(self, caplog):
        """Test that security headers middleware can be disabled (with warning)."""
        app = FastAPI()

        config = {'security': {'headers': {'enabled': False}}}

        initial_middleware_count = len(app.user_middleware)

        with caplog.at_level(logging.WARNING, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_security_headers_middleware(app, config)

        assert len(app.user_middleware) == initial_middleware_count
        assert any("DISABLED" in r.message for r in caplog.records)

    def test_security_headers_empty_config_enables_by_default(self):
        """Test that empty headers config still enables the middleware."""
        app = FastAPI()

        config = {'security': {'headers': {}}}

        initial_middleware_count = len(app.user_middleware)
        MiddlewareConfigurator._configure_security_headers_middleware(app, config)

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

        assert len(app.user_middleware) >= initial_middleware_count + 2

    def test_configure_middleware_order(self, caplog):
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

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator.configure_middleware(app, config, logger)

        messages = [r.message for r in caplog.records]
        assert any("Security headers middleware configured" in m for m in messages)
        assert any("CORS middleware configured" in m for m in messages)

    def test_metrics_middleware_handles_import_error(self):
        """Test that metrics middleware gracefully handles import errors."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        with patch('config.middleware_configurator.MiddlewareConfigurator._configure_metrics_middleware') as mock_metrics:
            mock_metrics.side_effect = lambda app: None

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
                    'headers': {'enabled': True}
                }
            }

            MiddlewareConfigurator.configure_middleware(app, config, logger)


class TestCORSSecurityEdgeCases:
    """Tests for edge cases and security scenarios."""

    def test_cors_with_multiple_origins_including_wildcard(self, caplog):
        """Test that wildcard is detected even when mixed with other origins."""
        app = FastAPI()

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

        with caplog.at_level(logging.WARNING, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        assert any("Automatically disabling" in r.message for r in caplog.records)

    def test_cors_with_empty_origins_list(self):
        """Test CORS configuration with empty origins list."""
        app = FastAPI()

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

        MiddlewareConfigurator._configure_cors_middleware(app, config)

    def test_cors_preserves_all_settings(self, caplog):
        """Test that all CORS settings are properly logged."""
        app = FastAPI()

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

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        messages = [r.message for r in caplog.records]
        assert any("GET" in m and "POST" in m and "PUT" in m for m in messages)
        assert any("7200" in m for m in messages)


class TestIntegrationScenarios:
    """Integration tests for complete middleware stack."""

    def test_full_stack_with_security_headers_and_cors(self):
        """Test that security headers and CORS work together correctly."""
        app = FastAPI()
        logger = logging.getLogger("test")

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["http://testclient"],
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

        response = client.options(
            "/api/data",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )

        assert response.status_code == 200


class TestConfigurationValidation:
    """Tests for configuration validation and error handling."""

    def test_missing_security_section_uses_defaults(self):
        """Test that missing security section uses secure defaults."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        MiddlewareConfigurator.configure_middleware(app, {'general': {'port': 3000}}, logger)

    def test_partial_cors_config_uses_defaults_for_missing(self, caplog):
        """Test that partial CORS config uses defaults for missing values."""
        app = FastAPI()

        config = {
            'security': {
                'cors': {
                    'allowed_origins': ["https://example.com"]
                }
            }
        }

        with caplog.at_level(logging.INFO, logger=_CONFIGURATOR_LOGGER):
            MiddlewareConfigurator._configure_cors_middleware(app, config)

        messages = [r.message for r in caplog.records]
        assert any("GET" in m for m in messages)

    def test_none_values_in_config_handled_gracefully(self):
        """Test that None values in config are handled without errors."""
        app = FastAPI()
        logger = Mock(spec=logging.Logger)

        config = {'security': {'cors': None, 'headers': None}}

        MiddlewareConfigurator.configure_middleware(app, config, logger)
