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
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_instance: Optional["MCPClientManager"] = None

# Sentinel for "caller passed no fallback" — distinct from any real config value.
_UNSET = object()

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
        mcp_config = config.get("mcp_clients", {})
        if mcp_config.get("enabled", False):
            _instance = MCPClientManager(mcp_config)
    return _instance


def reload_mcp_client_manager(config: Dict[str, Any]) -> Optional["MCPClientManager"]:
    """Rebuild the singleton from `config`, returning the new manager (or None
    if MCP is now disabled).

    Safe to call while requests are in flight: consumers re-fetch the manager
    per request and only hold a local reference for the duration of one tool
    loop, and the manager holds no persistent connections — an in-flight loop
    simply finishes against the old snapshot.
    """
    global _instance
    mcp_config = config.get("mcp_clients", {})
    _instance = MCPClientManager(mcp_config) if mcp_config.get("enabled", False) else None
    return _instance


def get_current_mcp_client_manager() -> Optional["MCPClientManager"]:
    """Return the singleton if one already exists, without creating one.

    Unlike get_mcp_client_manager, never constructs a manager from config —
    callers that need to distinguish "no manager yet" from "manager exists"
    (e.g. to decide whether an update can be scoped to one server) use this.
    """
    return _instance


class MCPClientManager:
    """
    Connects to configured MCP servers, caches their tool schemas, and
    executes tool calls.
    """

    # Settings that may appear at the mcp_clients level (as defaults) and be
    # overridden per server entry: key -> (coercion, hardcoded default).
    _OVERRIDABLE: Dict[str, Any] = {
        "tool_timeout": (int, 30),
        # Servers that are unavailable during startup remain retryable.  A
        # retry is triggered by the next request after this interval, so a
        # temporary remote MCP outage does not require restarting ORBIT.
        "discovery_retry_interval": (lambda v: max(0, int(v)), 30),
        # Discovery is only initialize + tools/list, so it gets a much tighter
        # budget than tool_timeout (which is sized for real tool work).  This
        # bounds how long a request can stall on an unreachable server.
        "discovery_timeout": (int, 5),
        "max_tool_iterations": (int, 5),
        # Cap on tool result text injected into the model context (not just
        # preview). Prevents unbounded context growth and limits
        # prompt-injection surface area.
        "tool_result_max_chars": (int, 8000),
        # Defense-in-depth gate for opportunistic (non-skill) tool calling.
        # Does not affect the explicit "mcp-agent" skill, which is governed
        # only by the global `enabled` flag.
        "allow_opportunistic": (bool, False),
    }

    # Per-server keys that are not settings (transport/identity/lifecycle).
    _SERVER_KEYS = {
        "name", "enabled", "transport", "command", "args", "env",
        "url", "headers",
    }

    def __init__(self, mcp_config: Dict[str, Any]):
        servers_list = mcp_config.get("servers", [])
        self._server_configs: Dict[str, Dict[str, Any]] = {
            s["name"]: s for s in servers_list if s.get("enabled", True)
        }
        # mcp_clients-level values act as defaults for every server; each
        # server entry may override any of them.
        self._defaults: Dict[str, Any] = {
            key: self._coerce(key, mcp_config[key])
            for key in self._OVERRIDABLE
            if key in mcp_config
        }
        self._warn_unknown_server_keys()

        # cache: server_name -> list of OpenAI-format tool dicts
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_lock = asyncio.Lock()
        self._cache_populated = False
        self._failed_discovery_servers: set[str] = set()
        # server_name -> monotonic deadline before which discovery is not retried
        self._next_discovery_retry_at: Dict[str, float] = {}

    def _coerce(self, key: str, value: Any, fallback: Any = _UNSET) -> Any:
        """Coerce a configured value, falling back one level down the
        precedence chain (server → mcp_clients default → hardcoded) if it is
        unusable, rather than skipping straight to the hardcoded default."""
        coerce, default = self._OVERRIDABLE[key]
        if fallback is _UNSET:
            fallback = default
        try:
            return coerce(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid value %r for MCP setting '%s'; using %r instead",
                value, key, fallback,
            )
            return fallback

    def _warn_unknown_server_keys(self) -> None:
        """Flag per-server keys that are neither transport config nor a known
        overridable setting — a typo there would otherwise fail silently."""
        known = self._SERVER_KEYS | set(self._OVERRIDABLE)
        for name, cfg in self._server_configs.items():
            unknown = sorted(set(cfg) - known)
            if unknown:
                logger.warning(
                    "MCP server '%s': unrecognized config key(s) %s — ignored",
                    name, ", ".join(unknown),
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setting(self, server_name: str, key: str) -> Any:
        """Per-server value for `key` if present, else the mcp_clients-level
        default, else the hardcoded default."""
        server_config = self._server_configs.get(server_name) or {}
        default = self._defaults.get(key, self._OVERRIDABLE[key][1])
        if key in server_config:
            # An unusable per-server override falls back to the admin's
            # mcp_clients-level value, not past it to the hardcoded default.
            return self._coerce(key, server_config[key], fallback=default)
        return default

    def opportunistic_servers(
        self, allowed_servers: Optional[List[str]] = None
    ) -> List[str]:
        """Enabled servers that opted into opportunistic (non-skill) tool
        calling, intersected with the adapter's mcp_servers allowlist."""
        return [
            name for name in self._server_configs
            if (not allowed_servers or name in allowed_servers)
            and self.setting(name, "allow_opportunistic")
        ]

    def max_tool_iterations_for(self, server_names) -> int:
        """Iteration budget for a request touching `server_names`: the most
        permissive participating server wins. Falls back to the configured
        default when no server is known."""
        budgets = [
            self.setting(name, "max_tool_iterations")
            for name in server_names
            if name in self._server_configs
        ]
        if budgets:
            return max(budgets)
        return self._defaults.get(
            "max_tool_iterations", self._OVERRIDABLE["max_tool_iterations"][1]
        )

    @staticmethod
    def servers_in_tools(tools: List[Dict[str, Any]]) -> set:
        """Server names participating in a tool list, from the '<server>__<tool>'
        namespacing — lets callers resolve per-server settings from tools alone."""
        names = set()
        for tool in tools:
            fn_name = tool.get("function", {}).get("name", "")
            if "__" in fn_name:
                names.add(fn_name.split("__", 1)[0])
        return names

    async def get_all_tools(
        self,
        allowed_servers: Optional[List[str]] = None,
        opportunistic_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return all cached tools as OpenAI-format tool dicts."""
        await self._ensure_cache_populated()
        tools = []
        for server_name, server_tools in self._tools_cache.items():
            if allowed_servers and server_name not in allowed_servers:
                continue
            if opportunistic_only and not self.setting(server_name, "allow_opportunistic"):
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

        tool_timeout = self.setting(server_name, "tool_timeout")
        try:
            result = await asyncio.wait_for(
                self._call_tool_on_server(server_config, tool_name, arguments),
                timeout=tool_timeout,
            )
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"MCP tool call '{namespaced_name}' timed out after {tool_timeout}s"
            )
        # Cap result size before it enters the model context.
        max_chars = self.setting(server_name, "tool_result_max_chars")
        if len(result) > max_chars:
            logger.warning(
                "MCP tool '%s' result truncated from %d to %d chars",
                namespaced_name, len(result), max_chars,
            )
            result = result[:max_chars] + "\n[...result truncated]"
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

    async def update_server(self, name: str, entry: Optional[Dict[str, Any]]) -> None:
        """Add, replace, or remove one server's config on this live instance.

        `entry=None` (or a disabled entry) removes the server: subsequent
        calls to it fail via call_tool's "Unknown MCP server" check, exactly
        as if it had never been configured. Any cached tools/failure state for
        the server are dropped so it cannot linger in get_all_tools() after
        removal. Callers should follow with refresh_tool_cache([name]) to
        re-dial when the server is still enabled.
        """
        async with self._cache_lock:
            self._tools_cache.pop(name, None)
            self._failed_discovery_servers.discard(name)
            self._next_discovery_retry_at.pop(name, None)
            if entry is None or not entry.get("enabled", True):
                self._server_configs.pop(name, None)
            else:
                self._server_configs[name] = entry
        self._warn_unknown_server_keys()

    async def refresh_tool_cache(self, server_names: Optional[List[str]] = None) -> None:
        """Discard cached schemas and re-dial servers.

        With server_names omitted, re-dials every enabled server. With a
        specific list, only those servers' caches are touched — other
        configured servers keep their live tool cache and failure state,
        so an edit to one server never forces an unrelated one to redial.
        """
        if server_names is None:
            async with self._cache_lock:
                self._tools_cache = {}
                self._failed_discovery_servers = set()
                self._next_discovery_retry_at = {}
                self._cache_populated = False
            await self._ensure_cache_populated()
            return

        names = [n for n in server_names if n in self._server_configs]
        if not names:
            return
        async with self._cache_lock:
            for name in names:
                self._tools_cache.pop(name, None)
                self._failed_discovery_servers.discard(name)
                self._next_discovery_retry_at.pop(name, None)
            await asyncio.gather(*(self._discover_server(n) for n in names))
            now = time.monotonic()
            for name in names:
                if name in self._failed_discovery_servers:
                    self._next_discovery_retry_at[name] = now + self.setting(name, "discovery_retry_interval")
            self._cache_populated = True

    async def _ensure_cache_populated(self) -> None:
        async with self._cache_lock:
            if self._cache_populated and not self._failed_discovery_servers:
                return

            # On first discovery, try every enabled server. After that, only
            # retry servers whose prior discovery failed and whose per-server
            # retry deadline has passed; healthy tool caches remain usable
            # while another server recovers.
            if not self._cache_populated:
                server_names = list(self._server_configs.keys())
            else:
                now = time.monotonic()
                server_names = [
                    name for name in sorted(self._failed_discovery_servers)
                    if now >= self._next_discovery_retry_at.get(name, 0.0)
                ]
                if not server_names:
                    return

            # Dial concurrently so the worst case is one discovery_timeout
            # rather than one per unreachable server.
            await asyncio.gather(*(self._discover_server(n) for n in server_names))
            self._cache_populated = True
            # Measure the interval from the end of the dial loop: a server
            # that black-holes connections burns the whole discovery_timeout,
            # which would otherwise leave the deadline already in the past.
            now = time.monotonic()
            for name in server_names:
                if name in self._failed_discovery_servers:
                    self._next_discovery_retry_at[name] = (
                        now + self.setting(name, "discovery_retry_interval")
                    )
                else:
                    self._next_discovery_retry_at.pop(name, None)

    async def _discover_server(self, server_name: str) -> None:
        """List tools on one server, recording it as failed on any error."""
        try:
            tools = await asyncio.wait_for(
                self._list_tools_on_server(self._server_configs[server_name]),
                timeout=self.setting(server_name, "discovery_timeout"),
            )
            self._tools_cache[server_name] = [
                self._to_openai_tool(server_name, t) for t in tools
            ]
            logger.info("MCP server '%s': discovered %d tools", server_name, len(tools))
            self._failed_discovery_servers.discard(server_name)
        except Exception as exc:
            logger.warning("MCP server '%s': failed to list tools: %s", server_name, exc)
            self._tools_cache[server_name] = []
            self._failed_discovery_servers.add(server_name)

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

        elif transport == "sse":
            from mcp.client.sse import sse_client

            url = server_config.get("url", "")
            headers = self._expand_headers(server_config)
            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

        elif transport == "http":
            from mcp.client.streamable_http import streamable_http_client
            from mcp.shared._httpx_utils import create_mcp_http_client

            url = server_config.get("url", "")
            headers = self._expand_headers(server_config)
            # MCP Streamable HTTP requires both JSON and SSE content types.
            headers.setdefault("Accept", "application/json, text/event-stream")
            # Use create_mcp_http_client so the client inherits MCP defaults:
            # follow_redirects=True, 30s general timeout, 300s SSE read timeout.
            async with create_mcp_http_client(headers=headers) as http_client:
                async with streamable_http_client(url, http_client=http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session

        else:
            raise ValueError(
                f"Unsupported MCP transport '{transport}'. Use 'stdio', 'sse', or 'http'."
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
    def _expand_headers(server_config: Dict[str, Any]) -> Dict[str, str]:
        """Build request headers from server config, expanding ${VAR} references.

        Authentication is configured as a normal ``Authorization`` header.
        """
        result: Dict[str, str] = {}
        for k, v in server_config.get("headers", {}).items():
            result[k] = os.path.expandvars(str(v)) if isinstance(v, str) else str(v)
        return result

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
