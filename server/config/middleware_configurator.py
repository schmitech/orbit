"""
Middleware configuration utilities for the inference server.

This module handles all middleware setup and configuration, including:
- CORS middleware configuration
- Request logging middleware
- Custom middleware registration
- Middleware ordering and dependencies
"""

import time
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any


class MiddlewareConfigurator:
    """
    Handles all aspects of middleware configuration for the inference server.
    
    This class is responsible for:
    - Setting up CORS middleware for cross-origin requests
    - Configuring request logging middleware for tracking
    - Managing middleware order and dependencies
    - Providing extensible middleware registration
    """
    
    @staticmethod
    def configure_middleware(app: FastAPI, config: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Configure all middleware for the FastAPI application.
        
        This method sets up:
        - CORS middleware for cross-origin requests
        - Custom logging middleware for request/response tracking
        
        The CORS middleware is configured to allow all origins, methods, and headers
        for development. In production, this should be restricted to specific origins.
        
        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
            logger: Logger instance for middleware logging
        """
        # Configure CORS middleware
        MiddlewareConfigurator._configure_cors_middleware(app, config)
        
        # Configure request logging middleware
        MiddlewareConfigurator._configure_logging_middleware(app, logger)
    
    @staticmethod
    def _configure_cors_middleware(app: FastAPI, config: Dict[str, Any]) -> None:
        """
        Configure CORS middleware for cross-origin requests.
        
        Args:
            app: The FastAPI application instance
            config: The application configuration dictionary
        """
        # Get CORS configuration from config, with defaults for development
        cors_config = config.get('cors', {})
        
        # Use permissive defaults for development, should be restricted in production
        allowed_origins = cors_config.get('allowed_origins', ["*"])
        allow_credentials = cors_config.get('allow_credentials', True)
        allowed_methods = cors_config.get('allowed_methods', ["*"])  
        allowed_headers = cors_config.get('allowed_headers', ["*"])
        
        # Add CORS middleware with configuration
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,  # TODO: Restrict in production
            allow_credentials=allow_credentials,
            allow_methods=allowed_methods,
            allow_headers=allowed_headers,
        )
    
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