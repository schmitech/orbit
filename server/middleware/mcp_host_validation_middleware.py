import ipaddress
from typing import Iterable, Optional
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

_LOCALHOST_NAMES = {"localhost", "127.0.0.1", "::1"}


def _host_is_allowed(value: str, extra_hosts: set) -> bool:
    if not value:
        return False
    host = value.split(":", 1)[0].strip("[]")
    if host in _LOCALHOST_NAMES:
        return True
    try:
        if ipaddress.ip_address(host).is_loopback:
            return True
    except ValueError:
        pass
    return host in extra_hosts


class MCPHostValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates the Host/Origin headers on requests to the /mcp mount.

    The /mcp mount bypasses ORBIT's normal API-key auth, so without this check
    a malicious webpage could use DNS rebinding (pointing a public hostname at
    127.0.0.1) to drive a user's locally-running ORBIT instance through their
    browser. See: https://github.com/modelcontextprotocol/typescript-sdk/security/advisories/GHSA-w48q-cv73-mx4w
    """

    def __init__(self, app, allowed_hosts: Optional[Iterable[str]] = None):
        super().__init__(app)
        self._extra_hosts = {h.split(":", 1)[0] for h in (allowed_hosts or []) if h and h != "*"}

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        if not _host_is_allowed(request.headers.get("host", ""), self._extra_hosts):
            return PlainTextResponse("Invalid Host header", status_code=400)

        origin = request.headers.get("origin")
        if origin:
            origin_host = urlparse(origin).hostname or ""
            if not _host_is_allowed(origin_host, self._extra_hosts):
                return PlainTextResponse("Invalid Origin header", status_code=400)

        return await call_next(request)
