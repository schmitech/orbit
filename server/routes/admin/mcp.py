"""
MCP client server management: listing, CRUD, validation, and hot reload.

Servers live in config/mcp_clients.yaml, a heavily commented file whose
commented-out entries are the catalogue of servers an admin can turn on.
Writes therefore patch individual scalar lines in place (via the shared
_yaml_config helpers, whose _find_adapter_block matches any "- name:" block)
rather than round-tripping through yaml.dump, which would erase every comment.
"""

import logging
import json
import os
import re
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit
from fastapi import APIRouter, Request, HTTPException, Body

from config.config_manager import reload_adapters_config

from routes.admin._shared import (
    config_auth,
)
from routes.admin._yaml_config import (
    _find_adapter_block, _write_adapter_config,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_mcp_config_path(request: Request) -> Path:
    """Resolve config/mcp_clients.yaml from app state."""
    config_path = Path(getattr(request.app.state, 'config_path', 'config/config.yaml'))
    return config_path.parent / "mcp_clients.yaml"


def _mcp_overridable() -> Dict[str, Any]:
    """The settings a server may override, read from the runtime's own table so
    the panel can never drift from what MCPClientManager actually honors."""
    from services.mcp_client_service import MCPClientManager
    return MCPClientManager._OVERRIDABLE


# Accepted range per numeric setting. Served to the admin panel so the inputs
# and this validation cannot disagree, and enforced here because the panel is
# not the only thing that can call these endpoints.
_MCP_SETTING_BOUNDS: Dict[str, tuple] = {
    "tool_timeout": (1, 600),
    "discovery_timeout": (1, 120),
    "discovery_retry_interval": (0, 3600),
    "max_tool_iterations": (1, 50),
    "tool_result_max_chars": (100, 200000),
    "pool_size": (0, 20),
    "pool_idle_timeout": (0, 3600),
}


def _validate_mcp_settings(settings: Any, overridable: Dict[str, Any]) -> None:
    """Reject unknown keys, wrong types, and out-of-range values.

    A null value is allowed: it deletes a per-server override so the server
    inherits the mcp_clients-level default again.
    """
    if not settings:
        return
    if not isinstance(settings, dict):
        raise HTTPException(status_code=422, detail="'settings' must be an object")

    unknown = sorted(set(settings) - set(overridable))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown MCP setting(s): {', '.join(unknown)}")

    for key, value in settings.items():
        if value is None:
            continue
        _coerce, fallback = overridable[key]
        if isinstance(fallback, bool):
            if not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"'{key}' must be true or false")
            continue
        # bool is a subclass of int, so screen it out before the int check.
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=422, detail=f"'{key}' must be a whole number")
        low, high = _MCP_SETTING_BOUNDS.get(key, (0, 2_147_483_647))
        if not (low <= value <= high):
            raise HTTPException(
                status_code=422,
                detail=f"'{key}' must be between {low} and {high} (got {value})",
            )


# Transport-identity fields editable from the panel. url is scalar
# lines patched by _patch_yaml_scalars; command is also scalar. args is a
# single-line list patched by _patch_yaml_list. env/headers are nested maps
# patched by _patch_yaml_map.
#
# headers is http-only: MCPClientManager._open_session only reads
# server_config["headers"] in its http branch (via _expand_headers) —
# the stdio branch builds a subprocess from command/args/env alone and never
# looks at headers. Editing it for a stdio server would silently persist a
# value the runtime never consumes.
_HTTP_CONNECTION_KEYS = {"url", "headers"}
_STDIO_CONNECTION_KEYS = {"command", "args", "env"}
_MCP_CONNECTION_URL_MAX_LENGTH = 2048
_MCP_CONNECTION_COMMAND_MAX_LENGTH = 512
_MCP_CONNECTION_ARG_MAX_LENGTH = 2048
_MCP_CONNECTION_ARGS_MAX_COUNT = 64
_MCP_CONNECTION_ENV_MAX_ENTRIES = 64
_MCP_CONNECTION_ENV_KEY_MAX_LENGTH = 256
_MCP_CONNECTION_ENV_VALUE_MAX_LENGTH = 8192
_MCP_CONNECTION_HEADER_MAX_ENTRIES = 32
_MCP_CONNECTION_HEADER_KEY_MAX_LENGTH = 256
_MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH = 8192
_MCP_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MCP_SERVER_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
# Map keys are written unquoted into mcp_clients.yaml (only values are
# json.dumps-quoted — see _patch_yaml_map), and the key is always the first
# non-whitespace character on the line. YAML treats a leading indicator
# character (#, !, *, `, |, ", ', :, etc.) or an embedded " #" as structural,
# not literal — e.g. a key of "X #evil" silently truncates the line into a
# comment, turning `headers:` into a bare scalar on reparse instead of a map.
# Restricting to alphanumerics, hyphen, and underscore (e.g. X-Api-Key,
# Authorization, CMIT_MCP_TOKEN) sidesteps the entire class of issues rather
# than trying to enumerate which indicator characters are unsafe where.
_MCP_HEADER_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_mcp_endpoint_url(url: str) -> None:
    """Require a bounded absolute HTTP(S) endpoint URL.

    MCP's remote transports only support HTTP and SSE over HTTP(S).  Rejecting
    control characters and fragments also prevents ambiguous request targets
    from being written through the admin panel.
    """
    if not url or not url.strip():
        raise HTTPException(status_code=422, detail="'url' must be a non-empty string")
    if len(url) > _MCP_CONNECTION_URL_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"'url' must be at most {_MCP_CONNECTION_URL_MAX_LENGTH} characters",
        )
    if url != url.strip() or any(ord(char) < 32 or char.isspace() for char in url):
        raise HTTPException(status_code=422, detail="'url' must not contain whitespace or control characters")
    try:
        parsed = urlsplit(url)
        # Accessing port validates it (for example, rejects :99999).
        _ = parsed.port
    except ValueError:
        raise HTTPException(status_code=422, detail="'url' must be a valid HTTP(S) URL")
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname or parsed.fragment:
        raise HTTPException(status_code=422, detail="'url' must be an absolute HTTP(S) URL without a fragment")


def _validate_mcp_command(command: Any) -> None:
    if not isinstance(command, str) or not command.strip():
        raise HTTPException(status_code=422, detail="'command' must be a non-empty string")
    if len(command) > _MCP_CONNECTION_COMMAND_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"'command' must be at most {_MCP_CONNECTION_COMMAND_MAX_LENGTH} characters",
        )
    if command != command.strip() or any(ord(ch) < 32 for ch in command):
        raise HTTPException(status_code=422, detail="'command' must not contain control characters")


def _validate_mcp_args(args: Any) -> None:
    if args is None:
        return
    if not isinstance(args, list):
        raise HTTPException(status_code=422, detail="'args' must be a list of strings")
    if len(args) > _MCP_CONNECTION_ARGS_MAX_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"'args' must contain at most {_MCP_CONNECTION_ARGS_MAX_COUNT} entries",
        )
    for arg in args:
        if not isinstance(arg, str):
            raise HTTPException(status_code=422, detail="'args' entries must be strings")
        if len(arg) > _MCP_CONNECTION_ARG_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'args' entries must be at most {_MCP_CONNECTION_ARG_MAX_LENGTH} characters",
            )
        if any(ord(ch) < 32 for ch in arg):
            raise HTTPException(status_code=422, detail="'args' entries must not contain control characters")


def _validate_mcp_env(env: Any) -> None:
    if env is None:
        return
    if not isinstance(env, dict):
        raise HTTPException(status_code=422, detail="'env' must be an object")
    if len(env) > _MCP_CONNECTION_ENV_MAX_ENTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"'env' must contain at most {_MCP_CONNECTION_ENV_MAX_ENTRIES} entries",
        )
    for key, value in env.items():
        if not isinstance(key, str) or not _MCP_ENV_KEY_RE.match(key) or len(key) > _MCP_CONNECTION_ENV_KEY_MAX_LENGTH:
            raise HTTPException(status_code=422, detail=f"'env' key '{key}' is not a valid environment variable name")
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"'env.{key}' must be a string")
        if len(value) > _MCP_CONNECTION_ENV_VALUE_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'env.{key}' must be at most {_MCP_CONNECTION_ENV_VALUE_MAX_LENGTH} characters",
            )


def _validate_mcp_headers(headers: Any) -> None:
    if headers is None:
        return
    if not isinstance(headers, dict):
        raise HTTPException(status_code=422, detail="'headers' must be an object")
    if len(headers) > _MCP_CONNECTION_HEADER_MAX_ENTRIES:
        raise HTTPException(
            status_code=422,
            detail=f"'headers' must contain at most {_MCP_CONNECTION_HEADER_MAX_ENTRIES} entries",
        )
    for key, value in headers.items():
        if (
            not isinstance(key, str)
            or not _MCP_HEADER_KEY_RE.match(key)
            or len(key) > _MCP_CONNECTION_HEADER_KEY_MAX_LENGTH
        ):
            raise HTTPException(status_code=422, detail=f"'headers' key '{key}' is not a valid header name")
        if not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"'headers.{key}' must be a string")
        if len(value) > _MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"'headers.{key}' must be at most {_MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH} characters",
            )


def _validate_new_mcp_server(body: Any, block: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the payload accepted by POST /mcp/servers."""
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Request body must be an object")
    unknown = sorted(set(body) - {"name", "transport", "connection"})
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field(s): {', '.join(unknown)}")

    name = body.get("name")
    if not isinstance(name, str) or not _MCP_SERVER_NAME_RE.match(name):
        raise HTTPException(
            status_code=422,
            detail="'name' must be a 1–64 character lowercase slug (letters, digits, hyphens)",
        )
    if any(isinstance(server, dict) and server.get("name") == name for server in (block.get("servers") or [])):
        raise HTTPException(status_code=409, detail=f"MCP server '{name}' already exists")

    transport = body.get("transport")
    if transport not in ("http", "stdio"):
        raise HTTPException(status_code=422, detail="'transport' must be 'http' or 'stdio'")
    connection = body.get("connection")
    if not isinstance(connection, dict):
        raise HTTPException(status_code=422, detail="'connection' must be an object")
    entry = {"name": name, "transport": transport, "enabled": True}
    _validate_mcp_connection(entry, connection)

    required = "url" if transport == "http" else "command"
    if required not in connection:
        raise HTTPException(status_code=422, detail=f"'{required}' is required for {transport} servers")
    entry.update(connection)
    return entry


def _validate_mcp_connection(entry: Dict[str, Any], connection: Any) -> None:
    """Reject connection edits for transports/fields that don't support them.

    url may not be cleared, since a server with no endpoint can never be
    dialed. env/headers are full-replace maps: the
    submitted value is the complete desired map, not a diff.
    """
    if not connection:
        return
    if not isinstance(connection, dict):
        raise HTTPException(status_code=422, detail="'connection' must be an object")

    transport = entry.get("transport", "stdio")
    if transport == "stdio":
        allowed = _STDIO_CONNECTION_KEYS
    elif transport == "http":
        allowed = _HTTP_CONNECTION_KEYS
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Connection fields are only editable for stdio/http servers, not '{transport}'.",
        )

    unknown = sorted(set(connection) - allowed)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown connection field(s): {', '.join(unknown)}")

    if "url" in connection:
        url = connection["url"]
        if not isinstance(url, str):
            raise HTTPException(status_code=422, detail="'url' must be a string")
        _validate_mcp_endpoint_url(url)

    if "command" in connection:
        _validate_mcp_command(connection["command"])
    if "args" in connection:
        _validate_mcp_args(connection["args"])
    if "env" in connection:
        _validate_mcp_env(connection["env"])
    if "headers" in connection:
        _validate_mcp_headers(connection["headers"])


def _mcp_endpoint_label(server: Dict[str, Any]) -> str:
    """One-line human description of where a server lives."""
    transport = server.get("transport", "stdio")
    if transport == "stdio":
        parts = [str(server.get("command", ""))] + [str(a) for a in (server.get("args") or [])]
        return " ".join(p for p in parts if p)
    return str(server.get("url", ""))


def _serialize_mcp_tools(tools: list) -> list:
    """Convert the manager's OpenAI-format cached schemas to the compact
    admin-panel shape. Both the server-list and explicit discovery endpoints
    use this so a cached server can show its tools/playbooks without a second
    round trip or a needless re-dial."""
    serialized = []
    for tool in tools:
        fn = tool.get("function", {})
        params = fn.get("parameters", {}) or {}
        required = params.get("required", []) or []
        serialized.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "parameters": [
                {
                    "name": pname,
                    "type": (pspec or {}).get("type", "string"),
                    "required": pname in required,
                    "description": (pspec or {}).get("description", ""),
                }
                for pname, pspec in (params.get("properties") or {}).items()
            ],
        })
    return serialized


def _read_mcp_config(request: Request) -> tuple[Path, str, Dict[str, Any]]:
    """Return (path, raw_text, parsed mcp_clients block)."""
    path = _get_mcp_config_path(request)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"MCP config not found at {path}")
    content = path.read_text(encoding="utf-8")
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML in mcp_clients.yaml: {exc}")
    block = parsed.get("mcp_clients")
    if not isinstance(block, dict):
        raise HTTPException(status_code=404, detail="mcp_clients.yaml has no 'mcp_clients' section")
    return path, content, block


@router.get("/mcp/servers", dependencies=[config_auth])
async def list_mcp_servers(request: Request):
    """Configured MCP servers with their effective settings and provenance."""
    import services.mcp_client_service as mcp_client_service

    path, _, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    # Read-only: never constructs or dials a manager. One is normally already
    # live by the time the admin panel loads, via the startup warm-up task
    # (see inference_server.py), so the panel can show real status on first
    # paint instead of a blank "Not checked" until someone clicks Ping.
    manager = mcp_client_service.get_current_mcp_client_manager()

    defaults = {}
    for key, (_coerce, fallback) in overridable.items():
        defaults[key] = block[key] if key in block else fallback

    servers = []
    for entry in block.get("servers") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        name = entry["name"]
        overrides = {k: entry[k] for k in overridable if k in entry}
        effective = dict(defaults)
        effective.update(overrides)
        transport = entry.get("transport", "stdio")
        connection = None
        if transport == "http":
            connection = {
                "url": entry.get("url", ""),
                "headers": entry.get("headers") or {},
            }
        elif transport == "stdio":
            connection = {
                "command": entry.get("command", ""),
                "args": entry.get("args") or [],
                "env": entry.get("env") or {},
            }
        # Only report a status once the server has actually been discovered
        # at least once — is_reachable() defaults an undiscovered server to
        # "reachable", which would otherwise flash green before the startup
        # warm-up (or first ping) has actually dialed it.
        status = None
        if manager is not None and name in manager._tools_cache:
            status = {
                "reachable": manager.is_reachable(name),
                "tool_count": len(manager._tools_cache[name]),
                # This is the manager's already-discovered cache: returning
                # it is read-only and never dials a server. The panel uses it
                # to resolve Playbooks immediately on first view.
                "tools": _serialize_mcp_tools(manager._tools_cache[name]),
            }
        servers.append({
            "name": name,
            "transport": transport,
            "enabled": entry.get("enabled", True),
            "endpoint": _mcp_endpoint_label(entry),
            "overrides": overrides,
            "effective": effective,
            "connection": connection,
            "status": status,
        })

    return {
        "enabled": block.get("enabled", False),
        "path": path.name,
        "settings": [
            {
                "key": key,
                "default": defaults[key],
                "type": "boolean" if isinstance(fallback, bool) else "number",
                "min": _MCP_SETTING_BOUNDS.get(key, (0, 0))[0],
                "max": _MCP_SETTING_BOUNDS.get(key, (0, 0))[1],
            }
            for key, (_c, fallback) in overridable.items()
        ],
        "defaults": defaults,
        "servers": servers,
    }


async def _reload_mcp_clients(request: Request, server_name: Optional[str] = None) -> Dict[str, Any]:
    """Re-read config from disk and apply the change.

    Reuses reload_adapters_config so mcp_clients.yaml's ${VAR} references
    expand exactly as they do at startup, then splices only the mcp_clients
    key into the live app-state config in place (it is the same dict object
    registered as 'config' in the pipeline DI container, so pipeline steps
    see the update without any other live service being touched).

    When `server_name` is given and a manager already exists and stays
    enabled, only that server's entry is rebuilt and re-dialed — every other
    configured server keeps its live tool cache untouched, so editing one
    server never forces an unrelated one to redial. Any other case (MCP newly
    enabled, MCP disabled, or a defaults-level change) rebuilds the whole
    manager, since defaults feed every server's effective settings.
    """
    import services.mcp_client_service as mcp_client_service

    config_path = getattr(request.app.state, "config_path", None)
    if not config_path:
        raise RuntimeError("Server config path is not available")

    new_config = reload_adapters_config(config_path)
    app_config = getattr(request.app.state, "config", None)
    if app_config is None:
        app_config = {}
        request.app.state.config = app_config
    new_mcp_config = new_config.get("mcp_clients", {})
    app_config["mcp_clients"] = new_mcp_config

    existing_manager = mcp_client_service.get_current_mcp_client_manager()
    scoped = (
        server_name is not None
        and existing_manager is not None
        and new_mcp_config.get("enabled", False)
    )

    if scoped:
        manager = existing_manager
        entry = next(
            (
                s for s in (new_mcp_config.get("servers") or [])
                if isinstance(s, dict) and s.get("name") == server_name
            ),
            None,
        )
        await manager.update_server(server_name, entry)
        try:
            await manager.refresh_tool_cache([server_name])
        except Exception as exc:
            logger.warning("MCP tool discovery failed after reload: %s", exc)
    else:
        manager = await mcp_client_service.reload_mcp_client_manager(app_config)
        if manager is not None:
            try:
                await manager.refresh_tool_cache()
            except Exception as exc:
                logger.warning("MCP tool discovery failed after reload: %s", exc)

    servers: Dict[str, Any] = {}
    if manager is not None:
        for name in manager._server_configs:
            servers[name] = {
                "reachable": manager.is_reachable(name),
                "tool_count": len(manager._tools_cache.get(name, [])),
            }

    # In multi-worker mode the manager singleton lives independently in every
    # worker. The serving worker already applied the efficient scoped update
    # above; siblings receive a generation signal and perform a full reload so
    # coalesced or concurrent saves can never leave an older server stale.
    if os.environ.get("ORBIT_SUPERVISOR_PID"):
        from services import adapter_reload_state

        new_generation = await adapter_reload_state.bump_generation(
            request.app.state, "mcp_config"
        )
        if new_generation is not None:
            last_seen = getattr(request.app.state, "_adapter_reload_last_seen", None)
            if last_seen is not None:
                last_seen["mcp_config"] = new_generation
        else:
            logger.warning("Failed to propagate MCP reload to other workers")

    return {"enabled": manager is not None, "servers": servers}


@router.post("/mcp/reload", dependencies=[config_auth])
async def reload_mcp_clients(request: Request):
    """Manually re-apply mcp_clients.yaml without restarting the server."""
    return await _reload_mcp_clients(request)


@router.get("/mcp/tools", dependencies=[config_auth])
async def discover_mcp_tools(request: Request, server: Optional[str] = None):
    """Re-dial MCP server(s) and report reachability plus their tools.

    Uses the live MCPClientManager as-is — the PATCH endpoints already apply
    config changes to it immediately, so this only needs to force a fresh
    re-dial for current reachability, not reload config from disk (which
    would rebuild the manager and re-dial every server on every click). Use
    POST /mcp/reload to pick up out-of-band edits to mcp_clients.yaml.

    With `server` omitted, every enabled server is re-dialed and reported.
    With `server` set, only that one is re-dialed and the response's
    `servers` map contains just that entry — letting the UI ping a single
    server without disturbing the reachability/tools already known for
    every other one.
    """
    from services.mcp_client_service import get_mcp_client_manager

    manager = get_mcp_client_manager(getattr(request.app.state, "config", {}) or {})
    if manager is None:
        return {
            "available": False,
            "reason": "MCP is disabled. Set mcp_clients.enabled: true.",
            "servers": {},
        }

    if server is not None and server not in manager._server_configs:
        raise HTTPException(status_code=404, detail=f"Unknown MCP server: {server}")

    try:
        await manager.refresh_tool_cache([server] if server is not None else None)
    except Exception as exc:
        logger.warning("MCP tool discovery failed: %s", exc)

    servers: Dict[str, Any] = {}
    names = [server] if server is not None else list(manager._server_configs)
    for name in names:
        servers[name] = {
            "reachable": manager.is_reachable(name),
            "tools": _serialize_mcp_tools(manager._tools_cache.get(name, [])),
        }

    return {"available": True, "servers": servers}


def _last_key_line(lines: list, start: int, end: int, indent: str) -> int:
    """Index after the block's last real `key:` line at `indent`.

    A block's end can sit far past its last setting — the final server entry
    in mcp_clients.yaml runs to EOF, past ~240 lines of commented-out server
    templates. Appending at `end` would drop a new setting into the middle of
    that catalogue: still valid YAML, but orphaned from the server it
    configures. Insert against the last real key instead.
    """
    insert_at = start + 1
    for i in range(start + 1, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith("#") or stripped.startswith("- "):
            continue
        if len(lines[i]) - len(stripped) != len(indent):
            continue
        insert_at = i + 1
    return insert_at


def _patch_yaml_scalars(lines: list, start: int, end: int, values: Dict[str, Any], indent: str) -> list:
    """Set or insert `key: value` scalar lines within lines[start:end].

    Keys mapped to None are removed, which is how an override reverts to
    inheriting the mcp_clients-level default.
    """
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, (int, float)):
            rendered = str(value)
        else:
            # Strings are quoted so ${VAR} references, colons, and
            # other YAML-significant characters can never be misparsed — json's
            # double-quote escaping is a valid subset of YAML's.
            rendered = json.dumps(str(value))

        found = -1
        for i in range(start, min(end, len(lines))):
            stripped = lines[i].lstrip()
            if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
                found = i
                break

        if value is None:
            if found >= 0:
                del lines[found]
                end -= 1
            continue

        if found >= 0:
            lines[found] = f"{indent}{key}: {rendered}"
        else:
            lines.insert(_last_key_line(lines, start, end, indent), f"{indent}{key}: {rendered}")
            end += 1
    return lines


def _find_block_header(lines: list, start: int, end: int, key: str, indent: str) -> tuple[int, int]:
    """Find a nested `key:` block within lines[start:end] at `indent`.

    Returns (header_index, body_end) where lines[header_index+1:body_end] is
    the block's body (deeper-indented subkey lines). (-1, -1) if not found.
    """
    header = -1
    for i in range(start, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
            header = i
            break
    if header < 0:
        return -1, -1

    body_end = min(end, len(lines))
    for i in range(header + 1, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if not stripped:
            # A blank line ends the map body — these config files use blank
            # lines as separators between entries, never inside one.
            body_end = i
            break
        if stripped.startswith("#"):
            continue
        if len(lines[i]) - len(stripped) <= len(indent):
            body_end = i
            break
    return header, body_end


def _patch_yaml_map(lines: list, start: int, end: int, key: str, target_map: Dict[str, str], indent: str) -> list:
    """Replace a nested `key:` block (env/headers) with `target_map` in full.

    `target_map` is the complete desired map, not a diff: any subkey
    currently in the block but absent from `target_map` is deleted, every
    entry in `target_map` is set. An empty `target_map` removes the block
    (including its header line) entirely.
    """
    sub_indent = indent + "  "
    header, body_end = _find_block_header(lines, start, end, key, indent)

    if header < 0:
        if not target_map:
            return lines
        insert_at = _last_key_line(lines, start, end, indent)
        new_lines = [f"{indent}{key}:"]
        for subkey, value in target_map.items():
            new_lines.append(f"{sub_indent}{subkey}: {json.dumps(str(value))}")
        lines[insert_at:insert_at] = new_lines
        return lines

    remaining = dict(target_map)
    i = header + 1
    while i < body_end:
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        matched_key = None
        for subkey in list(remaining):
            if stripped.startswith(subkey + ":") and len(lines[i]) - len(stripped) == len(sub_indent):
                matched_key = subkey
                break
        if matched_key is not None:
            lines[i] = f"{sub_indent}{matched_key}: {json.dumps(str(remaining.pop(matched_key)))}"
            i += 1
            continue
        # Subkey not present in target_map: drop the line.
        del lines[i]
        body_end -= 1

    for subkey, value in remaining.items():
        lines.insert(body_end, f"{sub_indent}{subkey}: {json.dumps(str(value))}")
        body_end += 1

    if body_end == header + 1:
        # Body is now empty: drop the header line too.
        del lines[header]

    return lines


def _patch_yaml_list(lines: list, start: int, end: int, key: str, values: Any, indent: str) -> list:
    """Rewrite a flow- or block-style YAML list as one flow-style line.

    `values` of None deletes the line entirely; an explicit empty list is
    still written since it differs in meaning from "field untouched".
    """
    found = -1
    body_end = -1
    for i in range(start, min(end, len(lines))):
        stripped = lines[i].lstrip()
        if stripped.startswith(key + ":") and len(lines[i]) - len(stripped) == len(indent):
            found = i
            break

    if found >= 0:
        body_end = found + 1
        for i in range(found + 1, min(end, len(lines))):
            stripped = lines[i].lstrip()
            if not stripped:
                break
            if stripped.startswith("#"):
                continue
            if len(lines[i]) - len(stripped) <= len(indent):
                break
            body_end = i + 1

    if values is None:
        if found >= 0:
            del lines[found:body_end]
        return lines

    rendered = f"{indent}{key}: {json.dumps(list(values))}"
    if found >= 0:
        lines[found:body_end] = [rendered]
    else:
        lines.insert(_last_key_line(lines, start, end, indent), rendered)
    return lines


def _insert_mcp_server(lines: list, entry: Dict[str, Any]) -> list:
    """Insert a newly validated server before the commented example catalogue."""
    servers_line = next((i for i, line in enumerate(lines) if line.lstrip().startswith("servers:")), -1)
    if servers_line < 0:
        raise HTTPException(status_code=422, detail="mcp_clients.yaml has no 'servers:' list")
    servers_indent = len(lines[servers_line]) - len(lines[servers_line].lstrip())
    entry_indent = " " * (servers_indent + 2)
    field_indent = entry_indent + "  "

    starts = [
        i for i in range(servers_line + 1, len(lines))
        if lines[i].lstrip().startswith("- name:")
        and len(lines[i]) - len(lines[i].lstrip()) == len(entry_indent)
    ]
    insert_at = servers_line + 1
    if starts:
        start = starts[-1]
        # This is the last active entry. Its block may run past a long
        # commented catalogue, and _last_key_line deliberately skips that.
        insert_at = _last_key_line(lines, start, len(lines), field_indent)

    rendered = [
        f"{entry_indent}- name: {json.dumps(entry['name'])}",
        f"{field_indent}transport: {json.dumps(entry['transport'])}",
    ]
    if entry["transport"] == "http":
        rendered.append(f"{field_indent}url: {json.dumps(entry['url'])}")
        if entry.get("headers"):
            rendered.append(f"{field_indent}headers:")
            rendered.extend(f"{field_indent}  {key}: {json.dumps(str(value))}" for key, value in entry["headers"].items())
    else:
        rendered.append(f"{field_indent}command: {json.dumps(entry['command'])}")
        if "args" in entry:
            rendered.append(f"{field_indent}args: {json.dumps(entry['args'])}")
        if entry.get("env"):
            rendered.append(f"{field_indent}env:")
            rendered.extend(f"{field_indent}  {key}: {json.dumps(str(value))}" for key, value in entry["env"].items())
    rendered.append(f"{field_indent}enabled: true")
    prefix = [""] if starts else []
    lines[insert_at:insert_at] = prefix + rendered
    return lines


def _remove_mcp_server(lines: list, server_name: str) -> list:
    """Remove one active MCP server entry without consuming surrounding docs.

    mcp_clients.yaml doubles as a commented server catalogue.  The shared
    _find_adapter_block deliberately includes those comments in an entry's
    range so editing can find the next active peer, but deletion must retain
    them.  Remove only the YAML-bearing lines for the matched list item and
    its nested fields; blank lines and comments remain in place.
    """
    start, end = _find_adapter_block(lines, server_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    remove_indices = [start]
    for i in range(start + 1, end):
        stripped = lines[i].lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        # _find_adapter_block has already bounded this range at the next
        # active peer or parent section. Remove every YAML-bearing line in
        # it, rather than relying on a field being indented more deeply than
        # the `- name:` marker. That keeps no orphaned scalar behind if a
        # hand-edited config uses unconventional indentation.
        remove_indices.append(i)

    for i in reversed(remove_indices):
        del lines[i]
    return lines


@router.post("/mcp/servers", dependencies=[config_auth])
async def create_mcp_server(request: Request, body: dict = Body(...)):
    """Create an enabled HTTP or stdio MCP server and apply it immediately."""
    path, content, block = _read_mcp_config(request)
    entry = _validate_new_mcp_server(body, block)
    lines = _insert_mcp_server(content.split("\n"), entry)
    new_content = "\n".join(lines)
    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Create produced invalid YAML: {exc}")
    servers = ((reparsed.get("mcp_clients") or {}).get("servers") or [])
    if not any(isinstance(server, dict) and server.get("name") == entry["name"] for server in servers):
        raise HTTPException(status_code=422, detail="Create would not add the requested MCP server")

    _write_adapter_config(path, new_content)
    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request, server_name=entry["name"])
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config saved but reload failed: %s", exc)
    message = (
        f"'{entry['name']}' created and applied." if reload_error is None
        else f"'{entry['name']}' created, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "server": entry, "reload_summary": reload_summary, "reload_error": reload_error}


@router.delete("/mcp/servers/{server_name}", dependencies=[config_auth])
async def delete_mcp_server(server_name: str, request: Request):
    """Delete one MCP server configuration and remove it from the live manager."""
    path, content, block = _read_mcp_config(request)
    if not any(
        isinstance(server, dict) and server.get("name") == server_name
        for server in (block.get("servers") or [])
    ):
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    lines = _remove_mcp_server(content.split("\n"), server_name)
    new_content = "\n".join(lines)
    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Delete produced invalid YAML: {exc}")
    servers = ((reparsed.get("mcp_clients") or {}).get("servers") or [])
    if any(isinstance(server, dict) and server.get("name") == server_name for server in servers):
        raise HTTPException(status_code=422, detail="Delete would not remove the requested MCP server")

    _write_adapter_config(path, new_content)
    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request, server_name=server_name)
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config deleted but reload failed: %s", exc)

    message = (
        f"'{server_name}' removed and applied." if reload_error is None
        else f"'{server_name}' removed, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "reload_summary": reload_summary, "reload_error": reload_error}


@router.patch("/mcp/servers/{server_name}", dependencies=[config_auth])
async def update_mcp_server(server_name: str, request: Request, body: dict = Body(...)):
    """Update one server's enabled flag, setting overrides, and transport-
    specific connection fields.

    `settings` values of null delete the override so the server inherits the
    mcp_clients-level default again. `connection.url` may not be null.
    """
    path, content, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    entry = next(
        (
            s for s in (block.get("servers") or [])
            if isinstance(s, dict) and s.get("name") == server_name
        ),
        None,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    settings = body.get("settings") or {}
    _validate_mcp_settings(settings, overridable)

    connection = body.get("connection") or {}
    _validate_mcp_connection(entry, connection)

    lines = content.split("\n")
    start, end = _find_adapter_block(lines, server_name)
    if start < 0:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_name}' not found")

    name_line = lines[start]
    indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)

    map_fields = {k: connection[k] for k in ("env", "headers") if k in connection}
    list_fields = {k: connection[k] for k in ("args",) if k in connection}
    scalar_connection = {k: v for k, v in connection.items() if k not in map_fields and k not in list_fields}

    values: Dict[str, Any] = dict(settings)
    values.update(scalar_connection)
    if "enabled" in body:
        values["enabled"] = bool(body["enabled"])

    lines = _patch_yaml_scalars(lines, start, end, values, indent)

    for map_key, target_map in map_fields.items():
        start, end = _find_adapter_block(lines, server_name)
        name_line = lines[start]
        indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)
        lines = _patch_yaml_map(lines, start, end, map_key, target_map or {}, indent)

    for list_key, list_values in list_fields.items():
        start, end = _find_adapter_block(lines, server_name)
        name_line = lines[start]
        indent = " " * (len(name_line) - len(name_line.lstrip()) + 2)
        lines = _patch_yaml_list(lines, start, end, list_key, list_values, indent)

    new_content = "\n".join(lines)

    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Edit produced invalid YAML: {exc}")
    if not isinstance(reparsed.get("mcp_clients"), dict):
        raise HTTPException(status_code=422, detail="Edit would remove the mcp_clients section")

    _write_adapter_config(path, new_content)

    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request, server_name=server_name)
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config saved but reload failed: %s", exc)

    message = (
        f"'{server_name}' saved and applied." if reload_error is None
        else f"'{server_name}' saved, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "reload_summary": reload_summary, "reload_error": reload_error}


@router.patch("/mcp/defaults", dependencies=[config_auth])
async def update_mcp_defaults(request: Request, body: dict = Body(...)):
    """Update the mcp_clients-level defaults and the global enabled gate."""
    path, content, block = _read_mcp_config(request)
    overridable = _mcp_overridable()

    settings = body.get("settings") or {}
    _validate_mcp_settings(settings, overridable)

    lines = content.split("\n")
    start = -1
    for i, line in enumerate(lines):
        if line.startswith("mcp_clients:"):
            start = i
            break
    if start < 0:
        raise HTTPException(status_code=404, detail="mcp_clients.yaml has no 'mcp_clients' section")

    # Defaults are the scalars between "mcp_clients:" and the "servers:" list.
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("servers:"):
            end = i
            break

    values: Dict[str, Any] = dict(settings)
    if "enabled" in body:
        values["enabled"] = bool(body["enabled"])

    lines = _patch_yaml_scalars(lines, start + 1, end, values, "  ")
    new_content = "\n".join(lines)

    try:
        reparsed = yaml.safe_load(new_content) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Edit produced invalid YAML: {exc}")
    if not isinstance(reparsed.get("mcp_clients"), dict):
        raise HTTPException(status_code=422, detail="Edit would remove the mcp_clients section")

    _write_adapter_config(path, new_content)

    reload_summary, reload_error = None, None
    try:
        reload_summary = await _reload_mcp_clients(request)
    except Exception as exc:
        reload_error = str(exc)
        logger.error("MCP config saved but reload failed: %s", exc)

    message = (
        "Defaults saved and applied." if reload_error is None
        else f"Defaults saved, but reload failed ({reload_error}). Restart to apply."
    )
    return {"message": message, "reload_summary": reload_summary, "reload_error": reload_error}
