"""
Selective GZip Compression Middleware

Provides GZip compression with path exclusion support to avoid
buffering streaming responses (SSE, WebSocket).
"""

import logging
from typing import List, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class SelectiveGZipMiddleware:
    """
    GZip middleware that excludes specific paths from compression.

    This is critical for streaming endpoints (SSE, WebSocket) where
    GZip buffering would break the real-time, word-by-word streaming effect.

    Usage:
        app.add_middleware(
            SelectiveGZipMiddleware,
            minimum_size=2048,
            excluded_paths=["/v1/chat", "/ws", "/mcp"]
        )
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 2048,
        excluded_paths: Optional[List[str]] = None,
        compresslevel: int = 9
    ):
        """
        Initialize the selective GZip middleware.

        Args:
            app: The ASGI application
            minimum_size: Minimum response size in bytes to compress
            excluded_paths: List of path prefixes to exclude from compression.
                          Defaults to streaming endpoints.
            compresslevel: GZip compression level (1-9, default 9)
        """
        self.app = app
        self.minimum_size = minimum_size
        self.compresslevel = compresslevel
        self.excluded_paths = excluded_paths or [
            "/v1/chat",  # SSE streaming endpoint
            "/ws",       # WebSocket endpoints
            "/mcp",      # MCP protocol endpoints
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Process the request, applying GZip only to non-excluded paths.

        Args:
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope["type"] != "http":
            # Pass through non-HTTP requests (WebSocket, lifespan)
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Check if path should be excluded from compression
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                # Skip compression for streaming endpoints
                await self.app(scope, receive, send)
                return

        # Check Accept-Encoding header for gzip support
        headers = dict(scope.get("headers", []))
        accept_encoding = headers.get(b"accept-encoding", b"").decode("latin-1")

        if "gzip" not in accept_encoding.lower():
            # Client doesn't support gzip
            await self.app(scope, receive, send)
            return

        # Apply GZip compression via GZipResponder
        responder = GZipResponder(
            self.app,
            self.minimum_size,
            compresslevel=self.compresslevel
        )
        await responder(scope, receive, send)
