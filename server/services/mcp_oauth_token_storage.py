"""File-backed OAuth token storage for outbound MCP servers.

Satisfies the ``mcp.client.auth.oauth2.TokenStorage`` protocol. One JSON
file per server under ``~/.orbit/mcp_oauth/<server_name>.json``, holding
both the issued tokens and any dynamically-registered client info, so a
single ``FileTokenStorage(server_name)`` instance is the shared contract
between the CLI's ``mcp login`` command (which writes the file) and the
running server's connection pool (which reads it) — see
docs: `bin/orbit/commands/mcp.py`, `services/mcp_client_service.py`.
"""

import json
import os
import time
from pathlib import Path

import mcp.client.auth.oauth2 as _oauth2
from mcp.client.auth.oauth2 import TokenStorage as _TokenStorageProtocol  # noqa: F401
from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken

DEFAULT_STATE_DIR = Path.home() / ".orbit" / "mcp_oauth"

# Google's real-world discovery document issues a bare-origin issuer
# ("https://accounts.google.com", no trailing slash), but the SDK derives
# the *expected* issuer from the protected-resource-metadata's
# authorization_servers[0] entry, which round-trips through pydantic's
# AnyUrl and gets a trailing slash appended. The SDK's RFC 8414 issuer
# check (mcp.client.auth.oauth2.validate_metadata_issuer) is a strict
# string comparison, so this false mismatch makes every Google OAuth login
# fail with "Authorization server metadata issuer mismatch" even though the
# two URLs are the same origin. There's no public hook to override this, so
# patch it narrowly: only tolerate a trailing-slash difference, otherwise
# defer to the SDK's own (still-strict) check.
_original_validate_metadata_issuer = _oauth2.validate_metadata_issuer


def _validate_metadata_issuer_tolerant(oauth_metadata, expected_issuer):
    issuer = str(oauth_metadata.issuer)
    # Tolerate exactly one side having a single extra trailing slash (the
    # bare-origin normalization case above) — not a generic rstrip, which
    # would also accept distinct path-based issuers that merely differ by
    # multiple trailing slashes (e.g. ".../tenant//" vs ".../tenant").
    if issuer == expected_issuer or issuer + "/" == expected_issuer or expected_issuer + "/" == issuer:
        return
    _original_validate_metadata_issuer(oauth_metadata, expected_issuer)


_oauth2.validate_metadata_issuer = _validate_metadata_issuer_tolerant

# When a dynamically-registered (or preregistered) client uses
# "client_secret_basic", OAuthContext.prepare_token_auth correctly moves the
# credentials into an HTTP Basic Authorization header — but it only strips
# `client_secret` from the request body, not `client_id`, so the token
# request ends up authenticating via *both* the Basic header and a body
# parameter in the same request. RFC 6749 section 2.3.1 says a client must
# not use more than one authentication method per request, and Cloudflare's
# MCP token endpoint enforces that strictly, rejecting the exchange with
# "Client must not use multiple authentication methods". There's no public
# hook to override this, so wrap the method: call the SDK's own
# implementation, then also drop `client_id` from the body for this one auth
# method (client_secret_post and the public "none"/absent cases already only
# put client_id in the body, with no competing header, and are unaffected).
_original_prepare_token_auth = _oauth2.OAuthContext.prepare_token_auth


def _prepare_token_auth_no_duplicate_client_id(self, data, headers=None):
    data, headers = _original_prepare_token_auth(self, data, headers)
    if (
        self.client_info
        and self.client_info.token_endpoint_auth_method == "client_secret_basic"
        and "Authorization" in headers
    ):
        data = {k: v for k, v in data.items() if k != "client_id"}
    return data, headers


_oauth2.OAuthContext.prepare_token_auth = _prepare_token_auth_no_duplicate_client_id


class FileTokenStorage:
    """Persists OAuth tokens and client registration info for one MCP server."""

    def __init__(self, server_name: str, state_dir: Path | None = None):
        self._server_name = server_name
        self._state_dir = state_dir or DEFAULT_STATE_DIR
        self._path = self._state_dir / f"{server_name}.json"

    @property
    def path(self) -> Path:
        return self._path

    def _read(self) -> dict:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict) -> None:
        self._state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, self._path)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def get_token_expiry(self) -> float | None:
        """Absolute Unix timestamp the stored access token expires at, or
        None if unknown/no-expiry — computed once at `set_tokens` time from
        `expires_in`, since `expires_in` itself is relative-to-issuance and
        meaningless once reloaded after a process restart. Not part of the
        SDK's TokenStorage protocol; used by
        MCPClientManager._build_oauth_provider to pre-warm a freshly built
        OAuthClientProvider's expiry state, since the SDK's own lazy
        `_initialize()` loads `current_tokens` but never calls
        `update_token_expiry()` — without this, a loaded token is treated as
        permanently valid until the first 401, which then fails because this
        process has no redirect/callback handler for a full re-auth.
        """
        return self._read().get("expires_at")

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        data["expires_at"] = time.time() + tokens.expires_in if tokens.expires_in is not None else None
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._write(data)

    async def get_oauth_metadata(self) -> OAuthMetadata | None:
        """The discovered authorization-server metadata (RFC 8414), notably
        `token_endpoint`. Not part of the SDK's TokenStorage protocol — the
        SDK only ever discovers this in-memory, during a live authorization
        flow, and never persists it. Without restoring it here, a refresh
        after a process restart falls back to OAuthClientProvider's default
        `<MCP resource origin>/token`, which is wrong for any provider whose
        token endpoint lives on a different origin (e.g. Google Drive), and
        the refresh request goes to the wrong URL. Written by the CLI's
        `mcp login` right after a successful login (the only place a full
        discovery + authorization flow actually runs); restored by
        MCPClientManager._build_oauth_provider before any refresh can occur.
        """
        raw = self._read().get("oauth_metadata")
        return OAuthMetadata.model_validate(raw) if raw else None

    async def set_oauth_metadata(self, metadata: OAuthMetadata) -> None:
        data = self._read()
        data["oauth_metadata"] = metadata.model_dump(mode="json")
        self._write(data)


def build_static_client_info(
    client_id: str,
    client_secret: str | None,
    redirect_uris: list,
    scope: str | None,
) -> OAuthClientInformationFull:
    """Build an OAuthClientInformationFull from a pre-registered client_id
    (and optional client_secret) configured in `auth:`, so
    OAuthClientProvider uses it directly instead of attempting RFC 7591
    dynamic client registration — the SDK only registers dynamically when
    `context.client_info` is still unset (see
    OAuthClientProvider._perform_authorization_code_grant's "Register client
    or use URL-based client ID" step), so setting this ahead of time is
    sufficient to opt out.
    """
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uris=redirect_uris,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope=scope,
        # A client_secret means a confidential client — authenticate token
        # requests with it. No secret means a public client (PKCE only);
        # leaving token_endpoint_auth_method unset matches that default.
        token_endpoint_auth_method="client_secret_post" if client_secret else None,
    )
