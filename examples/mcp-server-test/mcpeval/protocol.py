"""Dependency-light MCP client used for ground truth and protocol conformance.

Deliberately separate from the LangChain adapter path in agent.py. Two reasons:

1. Ground truth must be computed without an LLM and without the library under
   test, so a bug in the adapter can't quietly redefine what "correct" means.
2. The sample server is stateless — a new McpServer per POST, no session id —
   so a plain JSON-RPC POST is the whole protocol. Verified against the running
   server: tools/call succeeds with no preceding initialize.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Self

import httpx

from .config import MUTATING_TOOLS, Settings

PROTOCOL_VERSION = "2025-06-18"


@dataclass(frozen=True)
class ToolResult:
    name: str
    args: dict[str, Any]
    payload: dict[str, Any]
    is_error: bool
    raw_text: str


class RawMcpClient:
    """Synchronous JSON-RPC-over-HTTP client for the sample MCP server."""

    def __init__(self, settings: Settings, timeout: float = 30.0):
        self._url = settings.mcp_url
        self._health_url = settings.health_url
        self._headers = {
            **settings.auth_headers,
            "Content-Type": "application/json",
            # The server may answer either way; accept both.
            "Accept": "application/json, text/event-stream",
        }
        self._client = httpx.Client(timeout=timeout)
        self._id = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
            raise RuntimeError(f"SSE response with no data frame: {response.text[:300]}")
        return response.json()

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            body["params"] = params
        response = self._client.post(self._url, headers=self._headers, json=body)
        response.raise_for_status()
        message = self._parse(response)
        if "error" in message:
            raise RuntimeError(f"{method} failed: {message['error']}")
        return message["result"]

    def health(self) -> dict[str, Any]:
        return self._client.get(self._health_url).json()

    def initialize(self) -> dict[str, Any]:
        return self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "orbit-mcp-eval", "version": "0.1.0"},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return self.rpc("tools/list", {})["tools"]

    def tool_names(self) -> list[str]:
        return sorted(tool["name"] for tool in self.list_tools())

    def call_tool(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        args = args or {}
        result = self.rpc("tools/call", {"name": name, "arguments": args})
        text = result["content"][0]["text"]
        return ToolResult(
            name=name,
            args=args,
            payload=json.loads(text),
            is_error=bool(result.get("isError")),
            raw_text=text,
        )

    def call_readonly(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """call_tool, but refuses the mutating tools.

        Ground-truth resolution goes through here so a badly written resolver
        can never change the state it is supposed to be observing.
        """
        if name in MUTATING_TOOLS:
            raise ValueError(f"{name} mutates server state and cannot be used for ground truth")
        return self.call_tool(name, args)


def server_healthy(settings: Settings, timeout: float = 2.0) -> bool:
    try:
        response = httpx.get(settings.health_url, timeout=timeout)
        return response.status_code == 200 and response.json().get("ok") is True
    except Exception:  # noqa: BLE001 - any failure to reach the server means "not healthy"
        return False
