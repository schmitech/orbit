#!/usr/bin/env python3
"""Unit tests for FileTokenStorage (server/services/mcp_oauth_token_storage.py)."""

import os
import stat
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from services.mcp_oauth_token_storage import FileTokenStorage, build_static_client_info


@pytest.mark.asyncio
async def test_get_tokens_returns_none_when_no_file(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    assert await storage.get_tokens() is None
    assert await storage.get_client_info() is None


@pytest.mark.asyncio
async def test_set_and_get_tokens_round_trip(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    tokens = OAuthToken(access_token="abc", refresh_token="def", expires_in=3600)
    await storage.set_tokens(tokens)

    loaded = await storage.get_tokens()
    assert loaded.access_token == "abc"
    assert loaded.refresh_token == "def"
    assert loaded.expires_in == 3600


@pytest.mark.asyncio
async def test_set_and_get_client_info_round_trip(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    info = OAuthClientInformationFull(
        client_id="client-123",
        client_secret="secret",
        redirect_uris=["http://127.0.0.1:8765/callback"],
    )
    await storage.set_client_info(info)

    loaded = await storage.get_client_info()
    assert loaded.client_id == "client-123"
    assert loaded.client_secret == "secret"


@pytest.mark.asyncio
async def test_tokens_and_client_info_coexist_in_same_file(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    await storage.set_tokens(OAuthToken(access_token="a"))
    await storage.set_client_info(OAuthClientInformationFull(client_id="c", redirect_uris=[]))

    assert (await storage.get_tokens()).access_token == "a"
    assert (await storage.get_client_info()).client_id == "c"


@pytest.mark.asyncio
async def test_file_permissions_restricted(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    await storage.set_tokens(OAuthToken(access_token="a"))

    mode = stat.S_IMODE(os.stat(storage.path).st_mode)
    assert mode == 0o600


@pytest.mark.asyncio
async def test_separate_servers_use_separate_files(tmp_path):
    a = FileTokenStorage("server-a", state_dir=tmp_path)
    b = FileTokenStorage("server-b", state_dir=tmp_path)
    await a.set_tokens(OAuthToken(access_token="token-a"))

    assert (await a.get_tokens()).access_token == "token-a"
    assert await b.get_tokens() is None
    assert a.path != b.path


@pytest.mark.asyncio
async def test_get_oauth_metadata_returns_none_when_absent(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    assert await storage.get_oauth_metadata() is None


@pytest.mark.asyncio
async def test_set_and_get_oauth_metadata_round_trip(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    metadata = OAuthMetadata(
        issuer="https://accounts.google.com",
        authorization_endpoint="https://accounts.google.com/o/oauth2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        response_types_supported=["code"],
    )
    await storage.set_oauth_metadata(metadata)

    loaded = await storage.get_oauth_metadata()
    assert str(loaded.token_endpoint) == "https://oauth2.googleapis.com/token"


@pytest.mark.asyncio
async def test_oauth_metadata_coexists_with_tokens_and_client_info(tmp_path):
    storage = FileTokenStorage("srv", state_dir=tmp_path)
    await storage.set_tokens(OAuthToken(access_token="a"))
    await storage.set_client_info(OAuthClientInformationFull(client_id="c", redirect_uris=[]))
    await storage.set_oauth_metadata(
        OAuthMetadata(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
            response_types_supported=["code"],
        )
    )

    assert (await storage.get_tokens()).access_token == "a"
    assert (await storage.get_client_info()).client_id == "c"
    assert str((await storage.get_oauth_metadata()).token_endpoint) == "https://example.com/token"


class TestBuildStaticClientInfo:
    def test_with_secret_uses_client_secret_post(self):
        info = build_static_client_info("cid", "secret", ["http://127.0.0.1:8765/callback"], "a b")
        assert info.client_id == "cid"
        assert info.client_secret == "secret"
        assert info.token_endpoint_auth_method == "client_secret_post"
        assert info.scope == "a b"

    def test_without_secret_is_a_public_client(self):
        info = build_static_client_info("cid", None, ["http://127.0.0.1:8765/callback"], None)
        assert info.client_secret is None
        assert info.token_endpoint_auth_method is None
