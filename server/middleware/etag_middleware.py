"""
ETag Middleware for HTTP Caching

Implements ETag-based caching for GET requests with JSON responses.
Returns 304 Not Modified when the response content hasn't changed,
reducing bandwidth usage and improving response times.

Key Features:
- Uses blake2b hash for fast, compact ETag generation
- Excludes streaming endpoints (SSE, WebSocket, MCP)
- Only processes GET requests with JSON content types
- Supports If-None-Match header for conditional requests
"""

import hashlib
import logging
from typing import List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)


class ETagMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds ETag headers to GET responses and handles
    conditional requests with If-None-Match headers.

    When a client sends a request with an If-None-Match header matching
    the current ETag, a 304 Not Modified response is returned instead
    of the full response body, saving bandwidth and processing time.
    """

    def __init__(self, app, excluded_paths: Optional[List[str]] = None):
        """
        Initialize the ETag middleware.

        Args:
            app: The ASGI application
            excluded_paths: List of path prefixes to exclude from ETag processing.
                          Defaults to ['/v1/chat', '/ws', '/mcp'] for streaming endpoints.
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or ['/v1/chat', '/ws', '/mcp']

    def _should_process(self, request: Request) -> bool:
        """
        Determine if the request should be processed for ETag caching.

        Only GET requests to non-excluded paths are processed.

        Args:
            request: The incoming HTTP request

        Returns:
            True if the request should be processed, False otherwise
        """
        # Only process GET requests
        if request.method != 'GET':
            return False

        # Check if path is excluded
        path = request.url.path
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return False

        return True

    def _generate_etag(self, content: bytes) -> str:
        """
        Generate an ETag from response content using blake2b hash.

        Uses blake2b with 8-byte digest for a fast, compact hash.

        Args:
            content: The response body bytes

        Returns:
            A quoted ETag string (e.g., '"abc123"')
        """
        # Use blake2b with 8-byte digest for speed and compactness
        hash_digest = hashlib.blake2b(content, digest_size=8).hexdigest()
        return f'"{hash_digest}"'

    def _is_json_response(self, response: Response) -> bool:
        """
        Check if the response content type is JSON.

        Args:
            response: The HTTP response

        Returns:
            True if the response is JSON, False otherwise
        """
        content_type = response.headers.get('content-type', '')
        return 'application/json' in content_type

    async def dispatch(self, request: Request, call_next):
        """
        Process the request and add ETag headers if applicable.

        For GET requests:
        1. Process the request normally
        2. If response is JSON, generate ETag from content
        3. If client's If-None-Match matches, return 304
        4. Otherwise, return response with ETag header

        Args:
            request: The incoming HTTP request
            call_next: The next middleware/handler in the chain

        Returns:
            The HTTP response, potentially a 304 Not Modified
        """
        # Skip if not applicable
        if not self._should_process(request):
            return await call_next(request)

        # Get the If-None-Match header from client
        if_none_match = request.headers.get('if-none-match')

        # Process the request
        response = await call_next(request)

        # Don't process streaming responses
        if isinstance(response, StreamingResponse):
            return response

        # Only process successful JSON responses
        if response.status_code != 200 or not self._is_json_response(response):
            return response

        # Get response body
        body = b''
        async for chunk in response.body_iterator:
            body += chunk

        # Generate ETag
        etag = self._generate_etag(body)

        # Check if client has matching ETag
        if if_none_match and if_none_match == etag:
            # Return 304 Not Modified
            return Response(
                status_code=304,
                headers={'ETag': etag}
            )

        # Return response with ETag header
        # Create a new response with the body and ETag
        headers = dict(response.headers)
        headers['ETag'] = etag
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type
        )
