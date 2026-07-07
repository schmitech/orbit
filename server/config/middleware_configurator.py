"""
Middleware configuration utilities for the inference server.

This module handles all middleware setup and configuration, including:
- CORS middleware configuration
- Security headers middleware
- Request logging middleware
- Custom middleware registration
- Middleware ordering and dependencies
"""

import time
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Any, List

_logger = logging.getLogger(__name__)


def _cache_provider_enabled(config: Dict[str, Any]) -> bool:
    """True if the master switch and the configured cache provider's own flag are both on."""
    from services.cache_backends import get_provider_config, is_cache_master_enabled
    from utils.config_utils import is_true_value

    if not is_cache_master_enabled(config):
        return False
    _, provider_config = get_provider_config(config)
    return is_true_value(provider_config.get('enabled', False))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    This middleware adds important security headers like:
    - Content-Security-Policy
    - Strict-Transport-Security
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    """

    def __init__(self, app, headers_config: Dict[str, Any], https_enabled: bool = False):
        super().__init__(app)
        self.headers_config = headers_config
        self.https_enabled = https_enabled

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if self.headers_config.get('content_security_policy'):
            response.headers['Content-Security-Policy'] = self.headers_config['content_security_policy']

        # HSTS is only meaningful (and safe) over HTTPS — suppress on plain HTTP per RFC 6797
        if self.https_enabled and self.headers_config.get('strict_transport_security'):
            response.headers['Strict-Transport-Security'] = self.headers_config['strict_transport_security']

        if self.headers_config.get('x_content_type_options'):
            response.headers['X-Content-Type-Options'] = self.headers_config['x_content_type_options']

        if self.headers_config.get('x_frame_options'):
            response.headers['X-Frame-Options'] = self.headers_config['x_frame_options']

        if self.headers_config.get('x_xss_protection'):
            response.headers['X-XSS-Protection'] = self.headers_config['x_xss_protection']

        if self.headers_config.get('referrer_policy'):
            response.headers['Referrer-Policy'] = self.headers_config['referrer_policy']

        if self.headers_config.get('permissions_policy'):
            response.headers['Permissions-Policy'] = self.headers_config['permissions_policy']

        return response


class MiddlewareConfigurator:
    """
    Handles all aspects of middleware configuration for the inference server.

    This class is responsible for:
    - Setting up CORS middleware for cross-origin requests
    - Configuring security headers middleware
    - Configuring request logging middleware for tracking
    - Managing middleware order and dependencies
    - Providing extensible middleware registration
    """

    @staticmethod
    def configure_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure all middleware for the FastAPI application.

        Middleware is added in reverse execution order — the last added runs first.
        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance used by the request-logging middleware at runtime
        """
        # Configure GZip compression middleware (added first, executed last)
        MiddlewareConfigurator._configure_compression_middleware(app, config)

        # Configure ETag caching middleware
        MiddlewareConfigurator._configure_etag_middleware(app, config)

        # Configure security headers middleware
        MiddlewareConfigurator._configure_security_headers_middleware(app, config)

        # Configure CORS middleware
        MiddlewareConfigurator._configure_cors_middleware(app, config)

        # Configure request logging middleware (logger captured in closure)
        MiddlewareConfigurator._configure_logging_middleware(app, logger)

        # Configure metrics middleware (if available)
        MiddlewareConfigurator._configure_metrics_middleware(app)

        # Configure rate limiting middleware (rejects requests over hard limits)
        MiddlewareConfigurator._configure_rate_limit_middleware(app, config)

        # Configure throttle middleware (added last, executed first — delays requests before rate limiting)
        MiddlewareConfigurator._configure_throttle_middleware(app, config)

        # Configure admin-audit middleware (outermost — sees all admin/auth mutations)
        MiddlewareConfigurator._configure_admin_audit_middleware(app, config)

    @staticmethod
    def _configure_admin_audit_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure admin/auth audit middleware.

        Only registered when internal_services.audit.admin_events.enabled is true.
        The middleware itself double-checks that the audit service is available
        and admin events are enabled at request time, so it is safe even if
        config changes.
        """
        audit_cfg = config.get('internal_services', {}).get('audit', {}) or {}
        admin_cfg = audit_cfg.get('admin_events', {}) or {}

        if not audit_cfg.get('enabled', False) or not admin_cfg.get('enabled', False):
            _logger.debug("Admin audit middleware is disabled in configuration")
            return

        try:
            from server.middleware.admin_audit_middleware import AdminAuditMiddleware
            app.add_middleware(AdminAuditMiddleware, config=config)
            _logger.debug("Admin audit middleware configured successfully")
        except ImportError as e:
            _logger.warning(f"AdminAuditMiddleware not available - admin audit disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure admin audit middleware: {e}")

    @staticmethod
    def _configure_security_headers_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """Configure security headers middleware for enhanced security."""
        security_config = config.get('security', {}) or {}
        headers_config = security_config.get('headers', {}) or {}
        https_cfg = (config.get('general', {}) or {}).get('https', {}) or {}
        https_enabled = bool(https_cfg.get('enabled', False))

        if headers_config.get('enabled', True):
            app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config, https_enabled=https_enabled)
            _logger.info("Security headers middleware configured successfully")
        else:
            _logger.warning("Security headers middleware is DISABLED - this is not recommended for production")

    @staticmethod
    def _configure_cors_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure CORS middleware for cross-origin requests with security validation.

        Enforces security best practices:
        - Warns when using wildcard origins
        - Automatically disables credentials when using wildcards
        """
        security_config = config.get('security', {}) or {}
        cors_config = security_config.get('cors', {}) or {}

        # Fall back to legacy cors config if security.cors is absent
        if not cors_config:
            cors_config = config.get('cors', {}) or {}

        allowed_origins: List[str] = cors_config.get('allowed_origins', ["*"])
        allow_credentials: bool = cors_config.get('allow_credentials', False)
        allowed_methods: List[str] = cors_config.get('allowed_methods', ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
        allowed_headers: List[str] = cors_config.get('allowed_headers', ["Authorization", "Content-Type", "X-API-Key", "X-Session-ID"])
        expose_headers: List[str] = cors_config.get('expose_headers', [])
        max_age: int = cors_config.get('max_age', 600)

        has_wildcard = "*" in allowed_origins

        if has_wildcard:
            _logger.warning(
                "SECURITY WARNING: CORS is configured with wildcard origin ('*'). "
                "This is acceptable for development but MUST be restricted to specific origins in production."
            )
            if allow_credentials:
                _logger.warning(
                    "SECURITY: Automatically disabling 'allow_credentials' because wildcard origins are configured. "
                    "Credentials cannot be used with wildcard origins per CORS specification."
                )
                allow_credentials = False

        if allow_credentials and not has_wildcard:
            _logger.info(f"CORS configured with credentials enabled for specific origins: {allowed_origins}")

        _logger.info("CORS Configuration:")
        _logger.info(f"  - Allowed Origins: {allowed_origins}")
        _logger.info(f"  - Allow Credentials: {allow_credentials}")
        _logger.info(f"  - Allowed Methods: {allowed_methods}")
        _logger.info(f"  - Allowed Headers: {allowed_headers}")
        _logger.info(f"  - Exposed Headers: {expose_headers}")
        _logger.info(f"  - Max Age: {max_age}s")

        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=allow_credentials,
            allow_methods=allowed_methods,
            allow_headers=allowed_headers,
            expose_headers=expose_headers,
            max_age=max_age,
        )

        _logger.info("CORS middleware configured successfully")

    @staticmethod
    def _configure_logging_middleware(app: FastAPI, logger: logging.Logger) -> None:
        """
        Configure request logging middleware.

        logger is captured in the log_requests closure and used at request
        handling time, so it cannot be replaced with the module-level _logger.
        """
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time

            client_ip = request.headers.get("X-Forwarded-For")
            if client_ip:
                client_ip = client_ip.split(',')[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown"

            logger.info(
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - "
                f"{client_ip} - {request.method} {request.url.path} - "
                f"{response.status_code} - {process_time:.3f}s"
            )

            return response

    @staticmethod
    def _configure_metrics_middleware(app: FastAPI) -> None:
        """Configure metrics middleware for monitoring requests."""
        try:
            from server.middleware.metrics_middleware import MetricsMiddleware
            app.add_middleware(MetricsMiddleware)
            _logger.debug("Metrics middleware configured successfully")
        except ImportError:
            _logger.warning("MetricsMiddleware not available - metrics collection disabled")
        except Exception as e:
            _logger.warning(f"Failed to configure metrics middleware: {e}")

    @staticmethod
    def _configure_rate_limit_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure rate limiting middleware for abuse prevention.

        Only active when security.rate_limiting.enabled is true and a cache
        provider is enabled (internal_services.cache).
        """
        security_config = config.get('security', {}) or {}
        rate_limit_config = security_config.get('rate_limiting', {}) or {}

        if not rate_limit_config.get('enabled', False):
            _logger.debug("Rate limiting middleware is disabled in configuration")
            return

        if not _cache_provider_enabled(config):
            _logger.warning(
                "Cache is disabled - please enable caching (internal_services.cache.enabled) to use "
                "rate limiting. Middleware will not be active."
            )
            return

        try:
            from server.middleware.rate_limit_middleware import RateLimitMiddleware
            app.add_middleware(RateLimitMiddleware, config=config)
            _logger.debug("Rate limiting middleware configured successfully")
        except ImportError as e:
            _logger.warning(f"RateLimitMiddleware not available - rate limiting disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure rate limit middleware: {e}")

    @staticmethod
    def _configure_throttle_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure throttle middleware for quota-based request delays.

        Executes before rate limiting. Only active when security.throttling.enabled
        is true and a cache provider is enabled (internal_services.cache).
        """
        security_config = config.get('security', {}) or {}
        throttle_config = security_config.get('throttling', {}) or {}

        if not throttle_config.get('enabled', False):
            _logger.debug("Throttle middleware is disabled in configuration")
            return

        if not _cache_provider_enabled(config):
            _logger.warning(
                "Cache is disabled - please enable caching (internal_services.cache.enabled) to use "
                "throttling. Middleware will not be active."
            )
            return

        try:
            from server.middleware.throttle_middleware import ThrottleMiddleware
            app.add_middleware(ThrottleMiddleware, config=config)
            _logger.debug("Throttle middleware configured successfully")
        except ImportError as e:
            _logger.warning(f"ThrottleMiddleware not available - throttling disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure throttle middleware: {e}")

    @staticmethod
    def _configure_compression_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure GZip compression middleware.

        Streaming endpoints (SSE, WebSocket, MCP) are excluded to preserve
        word-by-word streaming behaviour.
        """
        compression_config = config.get('performance', {}).get('compression', {})

        if not compression_config.get('enabled', True):
            _logger.debug("GZip compression middleware is disabled in configuration")
            return

        try:
            from server.middleware.compression_middleware import SelectiveGZipMiddleware

            minimum_size = compression_config.get('minimum_size', 2048)
            excluded_paths = compression_config.get('excluded_paths', [
                '/v1/chat',
                '/ws',
                '/mcp',
            ])

            app.add_middleware(
                SelectiveGZipMiddleware,
                minimum_size=minimum_size,
                excluded_paths=excluded_paths
            )
            _logger.debug(f"GZip compression middleware configured (min_size={minimum_size}, excluded: {excluded_paths})")
        except ImportError as e:
            _logger.warning(f"SelectiveGZipMiddleware not available - compression disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure compression middleware: {e}")

    @staticmethod
    def _configure_etag_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure ETag caching middleware for GET requests.

        Returns 304 Not Modified for unchanged responses, reducing bandwidth
        for read-heavy endpoints.
        """
        etag_config = config.get('performance', {}).get('etag_caching', {})

        if not etag_config.get('enabled', True):
            _logger.debug("ETag caching middleware is disabled in configuration")
            return

        try:
            from server.middleware.etag_middleware import ETagMiddleware
            excluded_paths = etag_config.get('excluded_paths', ['/v1/chat', '/ws', '/mcp'])
            app.add_middleware(ETagMiddleware, excluded_paths=excluded_paths)
            _logger.debug(f"ETag caching middleware configured (excluded: {excluded_paths})")
        except ImportError as e:
            _logger.warning(f"ETagMiddleware not available - ETag caching disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure ETag middleware: {e}")
