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

# Get module-level logger that will inherit root logger configuration
_logger = logging.getLogger(__name__)


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

    def __init__(self, app, headers_config: Dict[str, Any]):
        super().__init__(app)
        self.headers_config = headers_config

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Add security headers from configuration
        if self.headers_config.get('content_security_policy'):
            response.headers['Content-Security-Policy'] = self.headers_config['content_security_policy']

        if self.headers_config.get('strict_transport_security'):
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

        This method sets up:
        - GZip compression middleware (added first, executed last)
        - ETag caching middleware
        - Security headers middleware
        - CORS middleware for cross-origin requests
        - Custom logging middleware for request/response tracking
        - Metrics middleware for monitoring
        - Rate limiting middleware for abuse prevention

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for middleware logging
        """
        # Configure GZip compression middleware (added first, executed last)
        MiddlewareConfigurator._configure_compression_middleware(app, config, logger)

        # Configure ETag caching middleware
        MiddlewareConfigurator._configure_etag_middleware(app, config, logger)

        # Configure security headers middleware
        MiddlewareConfigurator._configure_security_headers_middleware(app, config, logger)

        # Configure CORS middleware
        MiddlewareConfigurator._configure_cors_middleware(app, config, logger)

        # Configure request logging middleware
        MiddlewareConfigurator._configure_logging_middleware(app, logger)

        # Configure metrics middleware (if available)
        MiddlewareConfigurator._configure_metrics_middleware(app, logger)
        
        # Configure rate limiting middleware (rejects requests over hard limits)
        MiddlewareConfigurator._configure_rate_limit_middleware(app, config, logger)

        # Configure throttle middleware (added last, executed first - delays requests before rate limiting)
        MiddlewareConfigurator._configure_throttle_middleware(app, config, logger)

    @staticmethod
    def _configure_security_headers_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure security headers middleware for enhanced security.

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for middleware logging
        """
        security_config = config.get('security', {}) or {}
        headers_config = security_config.get('headers', {}) or {}

        if headers_config.get('enabled', True):
            app.add_middleware(SecurityHeadersMiddleware, headers_config=headers_config)
            _logger.info("Security headers middleware configured successfully")
            logger.info("Security headers middleware configured successfully")
        else:
            _logger.warning("Security headers middleware is DISABLED - this is not recommended for production")
            logger.warning("Security headers middleware is DISABLED - this is not recommended for production")

    @staticmethod
    def _configure_cors_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure CORS middleware for cross-origin requests with security validation.

        This method enforces security best practices:
        - Warns when using wildcard origins
        - Automatically disables credentials when using wildcards
        - Restricts methods and headers to specific allowed values

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for CORS configuration logging
        """
        # Get security CORS configuration from new security section
        security_config = config.get('security', {}) or {}
        cors_config = security_config.get('cors', {}) or {}

        # If no security.cors config, fall back to legacy cors config with secure defaults
        if not cors_config:
            cors_config = config.get('cors', {}) or {}

        # Get CORS settings with secure defaults
        allowed_origins: List[str] = cors_config.get('allowed_origins', ["*"])
        allow_credentials: bool = cors_config.get('allow_credentials', False)
        allowed_methods: List[str] = cors_config.get('allowed_methods', ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
        allowed_headers: List[str] = cors_config.get('allowed_headers', ["Authorization", "Content-Type", "X-API-Key", "X-Session-ID"])
        expose_headers: List[str] = cors_config.get('expose_headers', [])
        max_age: int = cors_config.get('max_age', 600)

        # Security validation: Check for wildcard origins
        has_wildcard = "*" in allowed_origins

        if has_wildcard:
            warning_msg = (
                "SECURITY WARNING: CORS is configured with wildcard origin ('*'). "
                "This is acceptable for development but MUST be restricted to specific origins in production."
            )
            _logger.warning(warning_msg)
            logger.warning(warning_msg)

            # Force disable credentials when using wildcard origins
            # This is a security requirement - browsers don't allow credentials with wildcard
            if allow_credentials:
                credentials_msg = (
                    "SECURITY: Automatically disabling 'allow_credentials' because wildcard origins are configured. "
                    "Credentials cannot be used with wildcard origins per CORS specification."
                )
                _logger.warning(credentials_msg)
                logger.warning(credentials_msg)
                allow_credentials = False

        # Validate that credentials are only enabled with specific origins
        if allow_credentials and not has_wildcard:
            creds_info = f"CORS configured with credentials enabled for specific origins: {allowed_origins}"
            _logger.info(creds_info)
            logger.info(creds_info)

        # Log CORS configuration for transparency
        _logger.info("CORS Configuration:")
        _logger.info(f"  - Allowed Origins: {allowed_origins}")
        _logger.info(f"  - Allow Credentials: {allow_credentials}")
        _logger.info(f"  - Allowed Methods: {allowed_methods}")
        _logger.info(f"  - Allowed Headers: {allowed_headers}")
        _logger.info(f"  - Exposed Headers: {expose_headers}")
        _logger.info(f"  - Max Age: {max_age}s")

        logger.info("CORS Configuration:")
        logger.info(f"  - Allowed Origins: {allowed_origins}")
        logger.info(f"  - Allow Credentials: {allow_credentials}")
        logger.info(f"  - Allowed Methods: {allowed_methods}")
        logger.info(f"  - Allowed Headers: {allowed_headers}")
        logger.info(f"  - Exposed Headers: {expose_headers}")
        logger.info(f"  - Max Age: {max_age}s")

        # Add CORS middleware with validated configuration
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
        logger.info("CORS middleware configured successfully")
    
    @staticmethod
    def _configure_logging_middleware(app: FastAPI, logger: logging.Logger) -> None:
        """
        Configure request logging middleware for tracking requests and responses.
        
        Args:
            app: The FastAPI application instance
            logger: Logger instance for request logging
        """
        # Add request logging middleware
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            """
            Log incoming requests and their processing time.
            
            This middleware logs:
            - Client IP address
            - HTTP method and path
            - Response status code
            - Processing time in seconds
            - Timestamp with millisecond precision
            
            Args:
                request: The incoming HTTP request
                call_next: The next middleware/handler in the chain
                
            Returns:
                The response from the next handler
            """
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Get client IP, handling potential proxy headers
            client_ip = request.headers.get("X-Forwarded-For")
            if client_ip:
                # Take the first IP if there are multiple (comma-separated)
                client_ip = client_ip.split(',')[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown"
            
            # Log request with detailed information
            logger.info(
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - "
                f"{client_ip} - {request.method} {request.url.path} - "
                f"{response.status_code} - {process_time:.3f}s"
            )
            
            return response
    
    @staticmethod
    def _configure_metrics_middleware(app: FastAPI, logger: logging.Logger) -> None:
        """
        Configure metrics middleware for monitoring requests.
        
        Args:
            app: The FastAPI application instance
            logger: Logger instance for metrics logging
        """
        try:
            # Use explicit package import to avoid module resolution issues
            from server.middleware.metrics_middleware import MetricsMiddleware
            app.add_middleware(MetricsMiddleware)
            logger.info("Metrics middleware configured successfully")
        except ImportError:
            logger.warning("MetricsMiddleware not available - metrics collection disabled")
        except Exception as e:
            logger.warning(f"Failed to configure metrics middleware: {e}")
    
    @staticmethod
    def _configure_rate_limit_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure rate limiting middleware for abuse prevention.
        
        Rate limiting is only enabled when:
        1. security.rate_limiting.enabled is true in config
        2. Redis service is enabled (required for distributed rate limiting)
        
        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for rate limit logging
        """
        # Check if rate limiting is enabled in config
        security_config = config.get('security', {}) or {}
        rate_limit_config = security_config.get('rate_limiting', {}) or {}
        
        if not rate_limit_config.get('enabled', False):
            _logger.info("Rate limiting middleware is disabled in configuration")
            logger.info("Rate limiting middleware is disabled in configuration")
            return
        
        # Check if Redis is enabled (required for rate limiting)
        redis_config = config.get('internal_services', {}).get('redis', {}) or {}
        if not redis_config.get('enabled', False):
            _logger.warning(
                "Rate limiting is enabled but Redis is disabled. "
                "Rate limiting requires Redis - middleware will not be active."
            )
            logger.warning(
                "Rate limiting is enabled but Redis is disabled. "
                "Rate limiting requires Redis - middleware will not be active."
            )
            return
        
        try:
            from server.middleware.rate_limit_middleware import RateLimitMiddleware
            app.add_middleware(RateLimitMiddleware, config=config)
            _logger.info("Rate limiting middleware configured successfully")
            logger.info("Rate limiting middleware configured successfully")
        except ImportError as e:
            _logger.warning(f"RateLimitMiddleware not available - rate limiting disabled: {e}")
            logger.warning(f"RateLimitMiddleware not available - rate limiting disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure rate limit middleware: {e}")
            logger.warning(f"Failed to configure rate limit middleware: {e}")

    @staticmethod
    def _configure_throttle_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure throttle middleware for quota-based request delays.

        Throttle middleware delays requests progressively as quota usage increases,
        providing smoother traffic control than hard rejection. Executes BEFORE
        rate limiting middleware.

        Throttling is only enabled when:
        1. security.throttling.enabled is true in config
        2. Redis service is enabled (required for quota tracking)

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for throttle logging
        """
        # Check if throttling is enabled in config
        security_config = config.get('security', {}) or {}
        throttle_config = security_config.get('throttling', {}) or {}

        if not throttle_config.get('enabled', False):
            _logger.info("Throttle middleware is disabled in configuration")
            logger.info("Throttle middleware is disabled in configuration")
            return

        # Check if Redis is enabled (required for throttling)
        redis_config = config.get('internal_services', {}).get('redis', {}) or {}
        if not redis_config.get('enabled', False):
            _logger.warning(
                "Throttling is enabled but Redis is disabled. "
                "Throttling requires Redis - middleware will not be active."
            )
            logger.warning(
                "Throttling is enabled but Redis is disabled. "
                "Throttling requires Redis - middleware will not be active."
            )
            return

        try:
            from server.middleware.throttle_middleware import ThrottleMiddleware
            app.add_middleware(ThrottleMiddleware, config=config)
            _logger.info("Throttle middleware configured successfully")
            logger.info("Throttle middleware configured successfully")
        except ImportError as e:
            _logger.warning(f"ThrottleMiddleware not available - throttling disabled: {e}")
            logger.warning(f"ThrottleMiddleware not available - throttling disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure throttle middleware: {e}")
            logger.warning(f"Failed to configure throttle middleware: {e}")

    @staticmethod
    def _configure_compression_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure GZip compression middleware for response compression.

        Compresses responses larger than the minimum size threshold to reduce
        bandwidth usage. Typically provides 30-60% smaller responses for JSON.

        IMPORTANT: Streaming endpoints (SSE, WebSocket) are excluded to preserve
        the word-by-word streaming effect.

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for compression logging
        """
        compression_config = config.get('performance', {}).get('compression', {})

        if not compression_config.get('enabled', True):
            _logger.info("GZip compression middleware is disabled in configuration")
            logger.info("GZip compression middleware is disabled in configuration")
            return

        try:
            from server.middleware.compression_middleware import SelectiveGZipMiddleware

            minimum_size = compression_config.get('minimum_size', 2048)
            # Exclude streaming endpoints from compression to preserve word-by-word streaming
            excluded_paths = compression_config.get('excluded_paths', [
                '/v1/chat',  # SSE streaming endpoint
                '/ws',       # WebSocket endpoints
                '/mcp',      # MCP protocol endpoints
            ])

            app.add_middleware(
                SelectiveGZipMiddleware,
                minimum_size=minimum_size,
                excluded_paths=excluded_paths
            )
            _logger.info(f"GZip compression middleware configured (min_size={minimum_size}, excluded: {excluded_paths})")
            logger.info(f"GZip compression middleware configured (min_size={minimum_size}, excluded: {excluded_paths})")
        except ImportError as e:
            _logger.warning(f"SelectiveGZipMiddleware not available - compression disabled: {e}")
            logger.warning(f"SelectiveGZipMiddleware not available - compression disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure compression middleware: {e}")
            logger.warning(f"Failed to configure compression middleware: {e}")

    @staticmethod
    def _configure_etag_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure ETag caching middleware for GET requests.

        Returns 304 Not Modified for unchanged responses, reducing bandwidth
        and improving response times for read-heavy endpoints.

        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for ETag logging
        """
        etag_config = config.get('performance', {}).get('etag_caching', {})

        if not etag_config.get('enabled', True):
            _logger.info("ETag caching middleware is disabled in configuration")
            logger.info("ETag caching middleware is disabled in configuration")
            return

        try:
            from server.middleware.etag_middleware import ETagMiddleware
            excluded_paths = etag_config.get('excluded_paths', ['/v1/chat', '/ws', '/mcp'])
            app.add_middleware(ETagMiddleware, excluded_paths=excluded_paths)
            _logger.info(f"ETag caching middleware configured (excluded: {excluded_paths})")
            logger.info(f"ETag caching middleware configured (excluded: {excluded_paths})")
        except ImportError as e:
            _logger.warning(f"ETagMiddleware not available - ETag caching disabled: {e}")
            logger.warning(f"ETagMiddleware not available - ETag caching disabled: {e}")
        except Exception as e:
            _logger.warning(f"Failed to configure ETag middleware: {e}")
            logger.warning(f"Failed to configure ETag middleware: {e}")
