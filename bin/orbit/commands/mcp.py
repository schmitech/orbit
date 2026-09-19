"""
MCP OAuth login/status commands.

Unlike every other orbit command, these talk directly to the local
filesystem rather than the running server's HTTP API: they read
config/mcp_clients.yaml's `auth:` block and write to the same
~/.orbit/mcp_oauth/<server>.json file the server process reads via
services.mcp_oauth_token_storage.FileTokenStorage — there's no admin API
surface for "run a loopback OAuth flow from the CLI process," and building
one would mean proxying a browser redirect through the server for no
benefit in ORBIT's single-deployment model.
"""

import argparse
import asyncio
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml
from rich.console import Console
from rich.table import Table

from bin.orbit.commands import BaseCommand
from bin.orbit.utils.output import OutputFormatter

console = Console()

# server/ is added to sys.path so this can import the same services the
# running server uses — see the project_root insertion below.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SERVER_ROOT = _PROJECT_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))


def _load_server_config(config_path: str, server_name: str | None = None):
    path = Path(config_path)
    if not path.is_absolute():
        path = _PROJECT_ROOT / config_path
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    servers = ((data.get("mcp_clients") or {}).get("servers")) or []
    if server_name is None:
        return servers
    for entry in servers:
        if entry.get("name") == server_name:
            return entry
    return None


class _CallbackResult:
    code: str | None = None
    state: str | None = None
    iss: str | None = None
    error: str | None = None


def _bind_loopback_listener(port: int) -> HTTPServer:
    """Bind 127.0.0.1:port for the OAuth redirect *before* the browser is
    opened, so an authorization server that redirects immediately (an
    existing browser session, instant SSO approval) never hits connection
    refused against a listener that hasn't started yet."""
    result = _CallbackResult()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # silence default stderr logging
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            result.code = (params.get("code") or [None])[0]
            result.state = (params.get("state") or [None])[0]
            # RFC 9207 issuer identification: required by authorization
            # servers advertising authorization_response_iss_parameter_supported;
            # the SDK rejects a missing iss for those servers.
            result.iss = (params.get("iss") or [None])[0]
            result.error = (params.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Login complete. You may close this tab.</body></html>")

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.result = result  # type: ignore[attr-defined]
    return server


def _wait_for_callback(server: HTTPServer, timeout: float = 300.0) -> _CallbackResult:
    """Block the calling thread for exactly one request on an already-bound
    listener, then close it and return the captured callback params."""
    server.timeout = timeout
    server.handle_request()
    server.server_close()
    return server.result  # type: ignore[attr-defined]


async def _prime_static_client(provider, storage, client_id: str, client_secret, redirect_uris: list, scope) -> None:
    """Preset a freshly built OAuthClientProvider with a preregistered
    client_id/client_secret, so it opts out of RFC 7591 dynamic client
    registration instead of attempting it on the first authorization
    request. Setting `provider.context.client_info` alone isn't enough: the
    SDK's own lazy `_initialize()` runs on the first request (since
    `provider._initialized` starts False) and unconditionally overwrites
    `context.client_info` with `await storage.get_client_info()` — usually
    None on a first login — which would clobber this and still trigger
    registration. Load `current_tokens` the same way `_initialize()` would
    (there may already be one from a prior login) and mark the provider
    pre-initialized so `_initialize()` never runs at all.
    """
    from services.mcp_oauth_token_storage import build_static_client_info

    provider.context.client_info = build_static_client_info(client_id, client_secret, redirect_uris, scope)
    provider.context.current_tokens = await storage.get_tokens()
    provider._initialized = True


class MCPLoginCommand(BaseCommand):
    """Run the browser OAuth login flow for one MCP server and store its token."""

    def __init__(self, formatter: OutputFormatter):
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "mcp login"

    @property
    def description(self) -> str:
        return "Log in to an OAuth-protected MCP server via the browser"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("server_name", help="Name of the server under mcp_clients.servers")
        parser.add_argument("--config", default="config/mcp_clients.yaml", help="Path to mcp_clients.yaml")
        parser.add_argument("--port", type=int, default=None, help="Override the server's auth.redirect_port")

    def execute(self, args: argparse.Namespace) -> int:
        server_config = _load_server_config(args.config, args.server_name)
        if server_config is None:
            self.formatter.error(f"Server '{args.server_name}' not found in {args.config}")
            return 1

        auth_cfg = server_config.get("auth") or {}
        if auth_cfg.get("type") != "oauth2":
            self.formatter.error(
                f"Server '{args.server_name}' has no auth: {{type: oauth2}} block configured — nothing to log in for"
            )
            return 1

        url = server_config.get("url", "")
        if not url:
            self.formatter.error(f"Server '{args.server_name}' has no url configured")
            return 1

        port = args.port or auth_cfg.get("redirect_port", 8765)
        scopes = auth_cfg.get("scopes") or []
        # ${VAR} references: _load_server_config is a raw yaml.safe_load with
        # no substitution pass, unlike MCPClientManager._expand_headers on
        # the server side — expand here explicitly, or a literal
        # "${GOOGLE_OAUTH_CLIENT_ID}" string reaches the provider as the
        # client_id. Matches _expand_headers's expandvars semantics: an
        # unset variable is left as the literal "${VAR}" text rather than
        # silently becoming an empty string.
        client_id = auth_cfg.get("client_id")
        if client_id:
            client_id = os.path.expandvars(str(client_id))
        client_secret = auth_cfg.get("client_secret")
        if client_secret:
            client_secret = os.path.expandvars(str(client_secret))

        try:
            asyncio.run(self._login(args.server_name, url, scopes, port, client_id, client_secret))
        except Exception as e:  # noqa: BLE001 - surfaced to the operator as a login failure
            self.formatter.error(f"Login failed: {e}")
            return 1

        self.formatter.success(
            f"Logged in to '{args.server_name}'. Token stored; ORBIT will refresh it automatically."
        )
        return 0

    async def _login(
        self,
        server_name: str,
        url: str,
        scopes: list,
        port: int,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared._httpx_utils import create_mcp_http_client
        from mcp.shared.auth import AuthorizationCodeResult, OAuthClientMetadata
        from services.mcp_oauth_token_storage import FileTokenStorage

        # Bind the loopback listener before the SDK calls redirect_handler
        # (which happens strictly before callback_handler — see
        # OAuthClientProvider._perform_authorization_code_grant). Binding
        # here, ahead of opening the browser, avoids a race where an
        # existing browser session or instant SSO approval redirects to
        # localhost before a listener bound only inside callback_handler
        # would exist yet, which would otherwise hang until timeout.
        listener = _bind_loopback_listener(port)

        async def redirect_handler(authorize_url: str) -> None:
            console.print(f"[blue]Opening browser for authorization:[/blue]\n  {authorize_url}")
            if not webbrowser.open(authorize_url):
                console.print("[yellow]Could not open a browser automatically — open the URL above manually.[/yellow]")

        async def callback_handler() -> AuthorizationCodeResult:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, _wait_for_callback, listener)
            if result.error or not result.code:
                raise RuntimeError(f"Authorization callback did not return a code (error={result.error})")
            return AuthorizationCodeResult(code=result.code, state=result.state, iss=result.iss)

        redirect_uris = [f"http://127.0.0.1:{port}/callback"]
        metadata = OAuthClientMetadata(
            redirect_uris=redirect_uris,
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=" ".join(scopes) or None,
            client_name="ORBIT",
        )
        storage = FileTokenStorage(server_name)
        provider = OAuthClientProvider(
            server_url=url,
            client_metadata=metadata,
            storage=storage,
            redirect_handler=redirect_handler,
            callback_handler=callback_handler,
        )
        if client_id:
            await _prime_static_client(provider, storage, client_id, client_secret, redirect_uris, metadata.scope)

        headers = {"Accept": "application/json, text/event-stream"}
        async with create_mcp_http_client(headers=headers, auth=provider) as http_client:
            async with streamable_http_client(url, http_client=http_client) as transport:
                read, write = transport[:2]
                async with ClientSession(read, write) as session:
                    await session.initialize()

        # The SDK only ever discovers authorization-server metadata (notably
        # token_endpoint) in-memory during this flow and never persists it —
        # save it now so a later refresh (possibly from a freshly started
        # server process, long after this CLI process has exited) knows the
        # right token endpoint instead of falling back to
        # OAuthClientProvider's default "<MCP resource origin>/token", which
        # is wrong whenever the token endpoint is on another origin.
        if provider.context.oauth_metadata is not None:
            await storage.set_oauth_metadata(provider.context.oauth_metadata)


class MCPStatusCommand(BaseCommand):
    """Show whether OAuth-configured MCP servers currently have a stored token."""

    def __init__(self, formatter: OutputFormatter):
        self.formatter = formatter

    @property
    def name(self) -> str:
        return "mcp status"

    @property
    def description(self) -> str:
        return "Show OAuth login status for MCP servers"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("server_name", nargs="?", help="Show only this server")
        parser.add_argument("--config", default="config/mcp_clients.yaml", help="Path to mcp_clients.yaml")

    def execute(self, args: argparse.Namespace) -> int:
        from services.mcp_oauth_token_storage import FileTokenStorage

        servers = _load_server_config(args.config)
        oauth_servers = [s for s in servers if (s.get("auth") or {}).get("type") == "oauth2"]
        if args.server_name:
            oauth_servers = [s for s in oauth_servers if s.get("name") == args.server_name]
            if not oauth_servers:
                self.formatter.error(
                    f"Server '{args.server_name}' not found or has no auth: {{type: oauth2}} block"
                )
                return 1

        if not oauth_servers:
            self.formatter.info("No OAuth-configured MCP servers found")
            return 0

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Server")
        table.add_column("Logged in")
        table.add_column("Expires")
        table.add_column("Client registered")

        for server in oauth_servers:
            name = server.get("name", "")
            storage = FileTokenStorage(name)
            tokens, client_info = asyncio.run(self._read_status(storage))
            if tokens is not None:
                expires_display = f"{tokens.expires_in}s from last refresh" if tokens.expires_in else "unknown"
                table.add_row(name, "[green]yes[/green]", expires_display, "yes" if client_info else "no")
            else:
                table.add_row(name, "[red]no[/red]", "-", "yes" if client_info else "no")

        console.print(table)
        return 0

    @staticmethod
    async def _read_status(storage):
        return await storage.get_tokens(), await storage.get_client_info()
