#!/usr/bin/env python3
"""Unit tests for the CLI's OAuth login helpers (bin/orbit/commands/mcp.py).

Exercises the exact gap flagged in review: presetting
OAuthClientProvider.context.client_info from a preregistered client_id is
not enough by itself — the SDK's own lazy _initialize() (run on the first
authenticated request) unconditionally overwrites it from storage unless the
provider is also marked pre-initialized. These tests drive a provider
through its first request via async_auth_flow to prove the static
client_info survives that guard, and that _load_server_config expands
${VAR} references in auth.client_id/client_secret the same way
MCPClientManager._expand_headers does for headers.
"""

import os
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)
repo_root = os.path.dirname(server_dir)
sys.path.append(repo_root)

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientMetadata
from services.mcp_oauth_token_storage import FileTokenStorage

import bin.orbit.commands.mcp as mcp_cli


def _make_provider(tmp_path, server_name="google-drive", url="https://drivemcp.googleapis.com/mcp/v1"):
    metadata = OAuthClientMetadata(
        redirect_uris=["http://127.0.0.1:8765/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="ORBIT",
    )
    storage = FileTokenStorage(server_name, state_dir=tmp_path)
    provider = OAuthClientProvider(
        server_url=url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=None,
        callback_handler=None,
    )
    return provider, storage


class TestPrimeStaticClient:
    @pytest.mark.asyncio
    async def test_sets_client_info_and_marks_initialized(self, tmp_path):
        provider, storage = _make_provider(tmp_path)

        await mcp_cli._prime_static_client(
            provider, storage, "preregistered-id", "shh",
            ["http://127.0.0.1:8765/callback"], None,
        )

        assert provider.context.client_info.client_id == "preregistered-id"
        assert provider.context.client_info.client_secret == "shh"
        assert provider._initialized is True

    @pytest.mark.asyncio
    async def test_client_info_survives_sdks_lazy_initialize_on_first_request(self, tmp_path):
        # The regression this guards against: without provider._initialized
        # being set, async_auth_flow's own `if not self._initialized: await
        # self._initialize()` guard fires on the first request and
        # overwrites context.client_info with `await
        # storage.get_client_info()` — None here, since nothing was ever
        # dynamically registered — which would silently discard the static
        # client_id and send the flow toward dynamic registration instead.
        provider, storage = _make_provider(tmp_path)
        assert await storage.get_client_info() is None  # nothing stored yet

        await mcp_cli._prime_static_client(
            provider, storage, "preregistered-id", None,
            ["http://127.0.0.1:8765/callback"], None,
        )

        import httpx2

        request = httpx2.Request("GET", provider.context.server_url)
        flow = provider.async_auth_flow(request)
        sent_request = await flow.__anext__()  # drive the flow to its first yielded request

        assert provider.context.client_info.client_id == "preregistered-id"
        assert provider._initialized is True
        # The first yielded request must be the caller's own GET, not a
        # dynamic client registration POST — proof _initialize() (and thus
        # registration) never ran.
        assert sent_request.method == "GET"

        await flow.aclose()

    @pytest.mark.asyncio
    async def test_loads_existing_tokens_alongside_static_client_info(self, tmp_path):
        from mcp.shared.auth import OAuthToken

        provider, storage = _make_provider(tmp_path)
        await storage.set_tokens(OAuthToken(access_token="a", refresh_token="r", expires_in=3600))

        await mcp_cli._prime_static_client(
            provider, storage, "preregistered-id", None,
            ["http://127.0.0.1:8765/callback"], None,
        )

        assert provider.context.current_tokens.access_token == "a"


class TestLoginChecksFingerprintBeforeLoadingCredentials:
    """If the server's url/client_id/scopes/redirect_port changed since the
    last login, `mcp login` must invalidate the old token file before the
    SDK (or _prime_static_client) can read it — otherwise a bearer token
    minted for the previous configuration could be sent to the new endpoint
    instead of starting a fresh authorization flow."""

    @pytest.mark.asyncio
    async def test_mismatched_token_is_cleared_before_the_session_is_built(self, tmp_path, monkeypatch):
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, MagicMock, patch

        from mcp.shared.auth import OAuthToken

        from services.mcp_oauth_token_storage import compute_fingerprint

        server_name = "google-drive"
        url = "https://drivemcp.googleapis.com/mcp/v1"
        old_fingerprint = compute_fingerprint(url, None, [], 8765)
        with patch("services.mcp_oauth_token_storage.DEFAULT_STATE_DIR", tmp_path):
            await FileTokenStorage(server_name, fingerprint=old_fingerprint).set_tokens(
                OAuthToken(access_token="stale", refresh_token="stale-r", expires_in=3600)
            )

            captured = {}

            @asynccontextmanager
            async def fake_create_mcp_http_client(headers=None, auth=None, **kwargs):
                # The provider's context must already have no stale token by
                # the time the HTTP client (and thus any real request) is
                # built — this is the earliest point the SDK could leak it.
                captured["current_tokens"] = auth.context.current_tokens
                yield MagicMock()

            @asynccontextmanager
            async def fake_streamable_http_client(url, http_client=None):
                yield MagicMock(), MagicMock()

            @asynccontextmanager
            async def fake_client_session(read, write):
                session = MagicMock()
                session.initialize = AsyncMock()
                session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
                yield session

            cmd = mcp_cli.MCPLoginCommand(__import__(
                "bin.orbit.utils.output", fromlist=["OutputFormatter"]
            ).OutputFormatter())

            with patch("mcp.shared._httpx_utils.create_mcp_http_client", fake_create_mcp_http_client), \
                 patch("mcp.client.streamable_http.streamable_http_client", fake_streamable_http_client), \
                 patch("mcp.client.session.ClientSession", fake_client_session), \
                 pytest.raises(RuntimeError, match="No token was issued"):
                # A different client_id than old_fingerprint used — simulates
                # the config having changed since the stale token was stored.
                await cmd._login(server_name, url, [], 8765, client_id="new-client-id", client_secret=None)

        assert captured["current_tokens"] is None


class TestLoadServerConfigExpandsAuthEnvVars:
    def _write_config(self, tmp_path):
        config_path = tmp_path / "mcp_clients.yaml"
        config_path.write_text(
            """mcp_clients:
  enabled: true
  servers:
    - name: "google-drive"
      transport: "http"
      url: "https://drivemcp.googleapis.com/mcp/v1"
      auth:
        type: "oauth2"
        client_id: "${TEST_ORBIT_OAUTH_CLIENT_ID}"
        client_secret: "${TEST_ORBIT_OAUTH_CLIENT_SECRET}"
      enabled: false
""",
            encoding="utf-8",
        )
        return config_path

    def test_execute_expands_client_id_and_secret_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_ORBIT_OAUTH_CLIENT_ID", "real-client-id")
        monkeypatch.setenv("TEST_ORBIT_OAUTH_CLIENT_SECRET", "real-client-secret")
        config_path = self._write_config(tmp_path)

        captured = {}

        async def fake_login(self, server_name, url, scopes, port, client_id=None, client_secret=None, listener=None):
            captured["client_id"] = client_id
            captured["client_secret"] = client_secret

        monkeypatch.setattr(mcp_cli.MCPLoginCommand, "_login", fake_login)

        from bin.orbit.utils.output import OutputFormatter

        cmd = mcp_cli.MCPLoginCommand(OutputFormatter())
        args = type("Args", (), {"server_name": "google-drive", "config": str(config_path), "port": None})()
        result = cmd.execute(args)

        assert result == 0
        assert captured["client_id"] == "real-client-id"
        assert captured["client_secret"] == "real-client-secret"

    def test_execute_leaves_unset_var_as_literal_text(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TEST_ORBIT_OAUTH_CLIENT_ID", raising=False)
        monkeypatch.delenv("TEST_ORBIT_OAUTH_CLIENT_SECRET", raising=False)
        config_path = self._write_config(tmp_path)

        captured = {}

        async def fake_login(self, server_name, url, scopes, port, client_id=None, client_secret=None, listener=None):
            captured["client_id"] = client_id

        monkeypatch.setattr(mcp_cli.MCPLoginCommand, "_login", fake_login)

        from bin.orbit.utils.output import OutputFormatter

        cmd = mcp_cli.MCPLoginCommand(OutputFormatter())
        args = type("Args", (), {"server_name": "google-drive", "config": str(config_path), "port": None})()
        cmd.execute(args)

        # os.path.expandvars leaves an unset ${VAR} as the literal text
        # rather than silently substituting an empty string — matching
        # MCPClientManager._expand_headers's semantics.
        assert captured["client_id"] == "${TEST_ORBIT_OAUTH_CLIENT_ID}"
