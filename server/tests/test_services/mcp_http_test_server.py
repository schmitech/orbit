#!/usr/bin/env python3
"""
Minimal HTTP MCP test server for smoke-testing the 'http' transport.

Run this server, then point an ORBIT mcp_client.yaml entry at it:

  servers:
    - name: "test-server"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "test-secret"          # optional: enables Bearer-token check
      enabled: true

Usage
-----
  # Start the server (blocks):
  python server/tests/test_services/mcp_http_test_server.py [--port 9999] [--token test-secret]

  # In another terminal, run the built-in smoke-test client:
  python server/tests/test_services/mcp_http_test_server.py --smoke-test [--port 9999] [--token test-secret]

Tools exposed
-------------
  echo          Returns the 'message' argument unchanged.
  add           Returns the sum of 'a' and 'b' (integers).
  fail_always   Always returns an MCP error (for error-path testing).
"""

import argparse
import asyncio
import sys
import os

# Allow running from repo root without installing the package.
_server_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.normpath(_server_dir))


def _build_app(required_token: str | None = None):
    from fastmcp import FastMCP

    mcp = FastMCP("orbit-test-server")

    @mcp.tool()
    def echo(message: str) -> str:
        """Return the message unchanged."""
        return message

    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Return a + b."""
        return a + b

    @mcp.tool()
    def fail_always() -> str:
        """Always returns a tool-level error string (for error-path testing)."""
        from fastmcp import exceptions
        raise exceptions.ToolError("intentional test failure")

    if required_token:
        # Wrap the ASGI app to reject requests with a wrong/missing Bearer token.
        inner_app = mcp.http_app(path="/mcp")

        async def auth_middleware(scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                auth = headers.get(b"authorization", b"").decode()
                expected = f"Bearer {required_token}"
                if auth != expected:
                    body = b'{"error": "Unauthorized"}'
                    await send({
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"application/json")],
                    })
                    await send({"type": "http.response.body", "body": body})
                    return
            await inner_app(scope, receive, send)

        return auth_middleware, mcp
    else:
        return mcp.http_app(path="/mcp"), mcp


def run_server(port: int, token: str | None):
    import uvicorn
    app, _ = _build_app(token)
    print(f"[test-server] Listening on http://127.0.0.1:{port}/mcp")
    if token:
        print(f"[test-server] Requiring Authorization: Bearer {token}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


async def smoke_test(port: int, token: str | None):
    """Connect via MCPClientManager and exercise the test tools."""
    # Add server/ to path so the service module resolves correctly.
    server_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    sys.path.insert(0, os.path.normpath(server_dir))

    from services.mcp_client_service import MCPClientManager

    config = {
        "servers": [
            {
                "name": "test-server",
                "transport": "http",
                "url": f"http://127.0.0.1:{port}/mcp",
                "enabled": True,
            }
        ],
        "tool_timeout": 10,
    }
    if token:
        config["servers"][0]["token"] = token

    mgr = MCPClientManager(config)

    print("Discovering tools …")
    tools = await mgr.get_all_tools()
    tool_names = [t["function"]["name"] for t in tools]
    print(f"  Found: {tool_names}")
    assert "test-server__echo" in tool_names, "echo tool missing"
    assert "test-server__add" in tool_names, "add tool missing"

    print("Calling echo …")
    result = await mgr.call_tool("test-server__echo", {"message": "hello MCP"})
    print(f"  Result: {result!r}")
    assert result == "hello MCP", f"unexpected echo result: {result!r}"

    print("Calling add …")
    result = await mgr.call_tool("test-server__add", {"a": 3, "b": 7})
    print(f"  Result: {result!r}")
    assert "10" in result, f"unexpected add result: {result!r}"

    print("Calling fail_always (expect Tool error) …")
    result = await mgr.call_tool("test-server__fail_always", {})
    print(f"  Result: {result!r}")
    assert "error" in result.lower() or "fail" in result.lower(), \
        f"expected error marker in result: {result!r}"

    print("\nAll smoke tests passed.")


def main():
    parser = argparse.ArgumentParser(description="MCP HTTP test server / smoke-test client")
    parser.add_argument("--port", type=int, default=9999, help="TCP port (default 9999)")
    parser.add_argument("--token", default=None, help="Required Bearer token (optional)")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run as smoke-test client instead of server",
    )
    args = parser.parse_args()

    if args.smoke_test:
        asyncio.run(smoke_test(args.port, args.token))
    else:
        run_server(args.port, args.token)


if __name__ == "__main__":
    main()
