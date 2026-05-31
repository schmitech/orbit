"""
MCP Client Service

Manages connections to external MCP servers, discovers their tools, and
executes tool calls. Exposed as a module-level singleton so any pipeline
step can call get_mcp_client_manager(config) without threading the
instance through the full service-injection chain.

Tool names are namespaced as "<server_name>__<tool_name>" to avoid
collisions across servers.

Transport support:
  - stdio: spawns a local subprocess per call (simple, works everywhere)
  - sse:   connects to a remote SSE endpoint per call

Per-request connections are used for v1 simplicity. Tool schemas are
cached after the first successful list_tools call so repeated connections
to stdio servers are only needed for actual tool invocations.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_instance: Optional["MCPClientManager"] = None

# Minimal safe environment to pass to stdio subprocesses.
# We intentionally do NOT forward the full process environment to avoid
# leaking API keys, database credentials, and other secrets to MCP server
# subprocesses. Only PATH/HOME/USER/TMPDIR (needed by npx, uvx, etc.) plus
# any keys explicitly listed in the server's 'env:' config are forwarded.
_SAFE_ENV_KEYS = {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TEMP", "TMP",
                  "LANG", "LC_ALL", "LC_CTYPE", "SHELL", "TERM"}


def get_mcp_client_manager(config: Dict[str, Any]) -> Optional["MCPClientManager"]:
    """Return the singleton MCPClientManager, or None if MCP is not enabled."""
    global _instance
    if _instance is None:
        mcp_config = config.get("mcp_client", {})
        if mcp_config.get("enabled", False):
            _instance = MCPClientManager(mcp_config)
    return _instance


class MCPClientManager:
    """
    Connects to configured MCP servers, caches their tool schemas, and
    executes tool calls.
    """

    def __init__(self, mcp_config: Dict[str, Any]):
        servers_list = mcp_config.get("servers", [])
        self._server_configs: Dict[str, Dict[str, Any]] = {
            s["name"]: s for s in servers_list if s.get("enabled", True)
        }
        self._tool_timeout: int = int(mcp_config.get("tool_timeout", 30))
        self._max_tool_iterations: int = int(mcp_config.get("max_tool_iterations", 5))
        # Cap on tool result text injected into the model context (not just preview).
        # Prevents unbounded context growth and limits prompt-injection surface area.
        self._tool_result_max_chars: int = int(mcp_config.get("tool_result_max_chars", 8000))

        # cache: server_name -> list of OpenAI-format tool dicts
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_populated = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def max_tool_iterations(self) -> int:
        return self._max_tool_iterations

    async def get_all_tools(
        self, allowed_servers: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Return all cached tools as OpenAI-format tool dicts."""
        await self._ensure_cache_populated()
        tools = []
        for server_name, server_tools in self._tools_cache.items():
            if allowed_servers and server_name not in allowed_servers:
                continue
            tools.extend(server_tools)
        return tools

    async def call_tool(
        self, namespaced_name: str, arguments: Dict[str, Any]
    ) -> str:
        """
        Call a tool identified by '<server_name>__<tool_name>'.

        Validates required parameters against the cached schema before spawning
        a subprocess, so missing-argument errors are caught cheaply and the
        model receives a precise error message it can act on immediately.

        Returns the result as a string capped at tool_result_max_chars.
        """
        if "__" not in namespaced_name:
            raise ValueError(
                f"Invalid namespaced tool name '{namespaced_name}'. "
                "Expected '<server>__<tool>'."
            )
        server_name, tool_name = namespaced_name.split("__", 1)
        server_config = self._server_configs.get(server_name)
        if not server_config:
            raise ValueError(
                f"Unknown MCP server '{server_name}'. "
                f"Known: {list(self._server_configs.keys())}"
            )

        # Validate required arguments against the cached schema — avoids
        # spinning up a subprocess only to get a validation error back.
        validation_error = self._validate_arguments(namespaced_name, arguments)
        if validation_error:
            logger.warning("Pre-call validation failed for '%s': %s", namespaced_name, validation_error)
            return f"Tool error: {validation_error}"

        try:
            result = await asyncio.wait_for(
                self._call_tool_on_server(server_config, tool_name, arguments),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"MCP tool call '{namespaced_name}' timed out after {self._tool_timeout}s"
            )
        # Cap result size before it enters the model context.
        if len(result) > self._tool_result_max_chars:
            logger.warning(
                "MCP tool '%s' result truncated from %d to %d chars",
                namespaced_name, len(result), self._tool_result_max_chars,
            )
            result = result[:self._tool_result_max_chars] + "\n[...result truncated]"
        return result

    def _validate_arguments(
        self, namespaced_name: str, arguments: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check that all required parameters are present for the given tool.

        Returns an error string describing what is missing, or None if valid.
        The error is phrased to be actionable for the model on its next attempt.
        """
        server_name = namespaced_name.split("__", 1)[0]
        cached = self._tools_cache.get(server_name, [])
        tool_schema = next(
            (t for t in cached if t.get("function", {}).get("name") == namespaced_name),
            None,
        )
        if not tool_schema:
            return None  # Schema not cached yet — let the server validate

        params = tool_schema.get("function", {}).get("parameters", {})
        required = params.get("required", [])
        properties = params.get("properties", {})

        missing = [p for p in required if p not in arguments or arguments[p] is None]
        if not missing:
            return None

        # Build a helpful message: name each missing param and its expected type
        details = []
        for p in missing:
            prop = properties.get(p, {})
            ptype = prop.get("type", "string")
            desc = prop.get("description", "")
            details.append(f"'{p}' ({ptype}){': ' + desc if desc else ''}")

        return (
            f"Missing required parameter(s) for {namespaced_name}: "
            + ", ".join(details)
            + ". Please retry with all required arguments."
        )

    # ------------------------------------------------------------------
    # Tool cache
    # ------------------------------------------------------------------

    async def _ensure_cache_populated(self) -> None:
        async with self._cache_lock:
            if self._cache_populated:
                return
            for server_name, server_config in self._server_configs.items():
                try:
                    tools = await asyncio.wait_for(
                        self._list_tools_on_server(server_config),
                        timeout=self._tool_timeout,
                    )
                    self._tools_cache[server_name] = [
                        self._to_openai_tool(server_name, t) for t in tools
                    ]
                    logger.info(
                        "MCP server '%s': discovered %d tools", server_name, len(tools)
                    )
                except Exception as exc:
                    logger.warning(
                        "MCP server '%s': failed to list tools: %s", server_name, exc
                    )
                    self._tools_cache[server_name] = []
            self._cache_populated = True

    # ------------------------------------------------------------------
    # Low-level transport helpers
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _open_session(self, server_config: Dict[str, Any]):
        """Async context manager that yields an initialized ClientSession."""
        from mcp.client.session import ClientSession

        transport = server_config.get("transport", "stdio")
        if transport == "stdio":
            from mcp.client.stdio import stdio_client, StdioServerParameters

            # Start from a minimal safe environment (PATH, HOME, etc.) rather
            # than forwarding the full process env, which would expose all API
            # keys and credentials to the subprocess.
            env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
            for key, val in server_config.get("env", {}).items():
                # Expand ${VAR} references for explicitly configured keys only.
                env[key] = os.path.expandvars(str(val)) if isinstance(val, str) else str(val)

            params = StdioServerParameters(
                command=server_config["command"],
                args=server_config.get("args", []),
                env=env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

        elif transport in ("sse", "http"):
            from mcp.client.sse import sse_client

            url = server_config.get("url", "")
            headers = server_config.get("headers", {})
            # Expand ${VAR} references in header values
            expanded_headers = {}
            for k, v in headers.items():
                expanded_headers[k] = os.path.expandvars(str(v)) if isinstance(v, str) else str(v)

            async with sse_client(url, headers=expanded_headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        else:
            raise ValueError(
                f"Unsupported MCP transport '{transport}'. Use 'stdio' or 'sse'."
            )

    async def _list_tools_on_server(self, server_config: Dict[str, Any]) -> list:
        """Open a connection, list tools, close."""
        async with self._open_session(server_config) as session:
            result = await session.list_tools()
            return result.tools

    async def _call_tool_on_server(
        self, server_config: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]
    ) -> str:
        """Open a connection, call the tool, close."""
        async with self._open_session(server_config) as session:
            result = await session.call_tool(tool_name, arguments=arguments)

        if result.isError:
            # Return the server's own error message (safe — it came from the MCP
            # server itself, not from an internal exception). The model receives
            # this and can reason about it (e.g. retry with corrected arguments).
            content_text = self._extract_text_content(result.content)
            logger.warning("MCP tool '%s' returned isError=True: %s", tool_name, content_text[:200])
            return f"Tool error: {content_text}"

        return self._extract_text_content(result.content)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text_content(content_list) -> str:
        """Extract plain text from a list of MCP content items."""
        parts = []
        for item in content_list:
            if hasattr(item, "text") and item.text:
                parts.append(item.text)
            elif hasattr(item, "data") and item.data:
                # EmbeddedResource or BlobResource — try JSON
                try:
                    parts.append(json.dumps(item.data))
                except Exception:
                    parts.append(str(item.data))
        return "\n".join(parts) if parts else ""

    @staticmethod
    def _to_openai_tool(server_name: str, mcp_tool) -> Dict[str, Any]:
        """Convert an mcp.types.Tool to an OpenAI function-calling tool dict."""
        namespaced = f"{server_name}__{mcp_tool.name}"
        input_schema = mcp_tool.inputSchema if mcp_tool.inputSchema else {
            "type": "object",
            "properties": {},
        }
        return {
            "type": "function",
            "function": {
                "name": namespaced,
                "description": mcp_tool.description or "",
                "parameters": input_schema,
            },
        }
