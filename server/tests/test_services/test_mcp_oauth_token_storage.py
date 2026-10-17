#!/usr/bin/env python3
"""Unit tests for FileTokenStorage (server/services/mcp_oauth_token_storage.py)."""

import os
import stat
import sys

import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from mcp.shared.auth import OAuthClientInformationFull, OAuthMetadata, OAuthToken
from services.mcp_oauth_token_storage import FileTokenStorage, build_static_client_info, compute_fingerprint


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


class TestComputeFingerprint:
    def test_deterministic_for_same_inputs(self):
        a = compute_fingerprint("https://x.example/mcp", "cid", ["a", "b"], 8765)
        b = compute_fingerprint("https://x.example/mcp", "cid", ["a", "b"], 8765)
        assert a == b

    def test_scope_order_does_not_matter(self):
        a = compute_fingerprint("https://x.example/mcp", "cid", ["a", "b"], 8765)
        b = compute_fingerprint("https://x.example/mcp", "cid", ["b", "a"], 8765)
        assert a == b

    def test_none_and_empty_client_id_are_equivalent(self):
        a = compute_fingerprint("https://x.example/mcp", None, [], 8765)
        b = compute_fingerprint("https://x.example/mcp", "", [], 8765)
        assert a == b

    @pytest.mark.parametrize(
        "other_kwargs",
        [
            {"url": "https://y.example/mcp"},
            {"client_id": "other-cid"},
            {"scopes": ["a"]},
            {"redirect_port": 9999},
        ],
    )
    def test_changing_any_field_changes_the_fingerprint(self, other_kwargs):
        base = {"url": "https://x.example/mcp", "client_id": "cid", "scopes": ["a", "b"], "redirect_port": 8765}
        changed = {**base, **other_kwargs}
        assert compute_fingerprint(**base) != compute_fingerprint(**changed)


class TestCheckAndApplyFingerprint:
    @pytest.mark.asyncio
    async def test_no_fingerprint_configured_is_a_noop(self, tmp_path):
        storage = FileTokenStorage("srv", state_dir=tmp_path)
        await storage.set_tokens(OAuthToken(access_token="a"))
        await storage.check_and_apply_fingerprint()
        assert (await storage.get_tokens()).access_token == "a"
        assert await storage.get_last_error() is None

    @pytest.mark.asyncio
    async def test_matching_fingerprint_preserves_credentials(self, tmp_path):
        fp = compute_fingerprint("https://x.example/mcp", None, [], 8765)
        storage = FileTokenStorage("srv", state_dir=tmp_path, fingerprint=fp)
        await storage.set_tokens(OAuthToken(access_token="a"))

        await storage.check_and_apply_fingerprint()

        assert (await storage.get_tokens()).access_token == "a"
        assert await storage.get_last_error() is None

    @pytest.mark.asyncio
    async def test_mismatched_fingerprint_clears_credentials_and_records_error(self, tmp_path):
        old_fp = compute_fingerprint("https://x.example/mcp", None, [], 8765)
        storage = FileTokenStorage("srv", state_dir=tmp_path, fingerprint=old_fp)
        await storage.set_tokens(OAuthToken(access_token="a"))
        await storage.set_client_info(OAuthClientInformationFull(client_id="c", redirect_uris=[]))

        new_fp = compute_fingerprint("https://x.example/mcp", "new-client", [], 8765)
        reloaded = FileTokenStorage("srv", state_dir=tmp_path, fingerprint=new_fp)
        await reloaded.check_and_apply_fingerprint()

        assert await reloaded.get_tokens() is None
        assert await reloaded.get_client_info() is None
        last_error = await reloaded.get_last_error()
        assert last_error["code"] == "fingerprint_mismatch"
        # File is kept, not deleted, per "Token lifecycle" in the roadmap doc.
        assert storage.path.exists()

    @pytest.mark.asyncio
    async def test_legacy_file_with_no_fingerprint_is_treated_as_mismatch(self, tmp_path):
        # A token file written before this fingerprint mechanism existed.
        legacy = FileTokenStorage("srv", state_dir=tmp_path)
        await legacy.set_tokens(OAuthToken(access_token="a"))

        fp = compute_fingerprint("https://x.example/mcp", None, [], 8765)
        reloaded = FileTokenStorage("srv", state_dir=tmp_path, fingerprint=fp)
        await reloaded.check_and_apply_fingerprint()

        assert await reloaded.get_tokens() is None
        assert (await reloaded.get_last_error())["code"] == "fingerprint_mismatch"


class TestLastError:
    @pytest.mark.asyncio
    async def test_absent_by_default(self, tmp_path):
        storage = FileTokenStorage("srv", state_dir=tmp_path)
        assert await storage.get_last_error() is None

    @pytest.mark.asyncio
    async def test_set_and_clear_round_trip(self, tmp_path):
        storage = FileTokenStorage("srv", state_dir=tmp_path)
        await storage.set_last_error("refresh_rejected")
        last_error = await storage.get_last_error()
        assert last_error["code"] == "refresh_rejected"
        assert "at" in last_error

        await storage.clear_last_error()
        assert await storage.get_last_error() is None

    @pytest.mark.asyncio
    async def test_clear_is_a_noop_when_already_absent(self, tmp_path):
        storage = FileTokenStorage("srv", state_dir=tmp_path)
        await storage.clear_last_error()
        assert await storage.get_last_error() is None


class TestClearCredentials:
    @pytest.mark.asyncio
    async def test_removes_tokens_and_client_info_but_keeps_file(self, tmp_path):
        storage = FileTokenStorage("srv", state_dir=tmp_path)
        await storage.set_tokens(OAuthToken(access_token="a", expires_in=3600))
        await storage.set_client_info(OAuthClientInformationFull(client_id="c", redirect_uris=[]))
        await storage.set_oauth_metadata(
            OAuthMetadata(
                issuer="https://example.com",
                authorization_endpoint="https://example.com/authorize",
                token_endpoint="https://example.com/token",
                response_types_supported=["code"],
            )
        )

        await storage.clear_credentials()

        assert await storage.get_tokens() is None
        assert await storage.get_client_info() is None
        assert await storage.get_token_expiry() is None
        # Non-credential fields untouched by this call.
        assert (await storage.get_oauth_metadata()) is not None
        assert storage.path.exists()


class TestValidateMetadataIssuerTolerantPatch:
    """Importing this module patches mcp.client.auth.oauth2's strict RFC 8414
    issuer check to tolerate a trailing-slash-only difference (Google's real
    discovery document issues a bare-origin issuer that otherwise never
    matches the SDK's AnyUrl-normalized expected issuer)."""

    def test_tolerates_trailing_slash_only_difference(self):
        import mcp.client.auth.oauth2 as oauth2

        meta = OAuthMetadata(
            issuer="https://accounts.google.com",
            authorization_endpoint="https://accounts.google.com/o/oauth2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            response_types_supported=["code"],
        )
        oauth2.validate_metadata_issuer(meta, "https://accounts.google.com/")

    def test_still_rejects_a_real_mismatch(self):
        import mcp.client.auth.oauth2 as oauth2
        from mcp.client.auth.exceptions import OAuthFlowError

        meta = OAuthMetadata(
            issuer="https://accounts.google.com",
            authorization_endpoint="https://accounts.google.com/o/oauth2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            response_types_supported=["code"],
        )
        with pytest.raises(OAuthFlowError):
            oauth2.validate_metadata_issuer(meta, "https://evil.example.com/")

    def test_rejects_distinct_path_based_issuers_differing_by_multiple_slashes(self):
        """A generic rstrip("/") would wrongly accept this; only a single
        added trailing slash on a bare-origin issuer should be tolerated."""
        import mcp.client.auth.oauth2 as oauth2
        from mcp.client.auth.exceptions import OAuthFlowError

        meta = OAuthMetadata(
            issuer="https://issuer.example/tenant",
            authorization_endpoint="https://issuer.example/tenant/authorize",
            token_endpoint="https://issuer.example/tenant/token",
            response_types_supported=["code"],
        )
        with pytest.raises(OAuthFlowError):
            oauth2.validate_metadata_issuer(meta, "https://issuer.example/tenant//")


class TestPrepareTokenAuthNoDuplicateClientIdPatch:
    """Importing this module patches OAuthContext.prepare_token_auth so
    client_secret_basic clients don't also send client_id in the request
    body — some authorization servers (Cloudflare's MCP token endpoint)
    reject a request that authenticates via both the Basic header and a body
    parameter in the same request."""

    def _context_with(self, auth_method):
        import mcp.client.auth.oauth2 as oauth2

        ctx = oauth2.OAuthContext.__new__(oauth2.OAuthContext)
        ctx.client_info = OAuthClientInformationFull(
            client_id="cid",
            client_secret="secret",
            redirect_uris=["http://127.0.0.1:8765/callback"],
            token_endpoint_auth_method=auth_method,
        )
        return ctx

    def test_client_secret_basic_drops_client_id_from_body(self):
        ctx = self._context_with("client_secret_basic")
        data = {"grant_type": "authorization_code", "code": "x", "client_id": "cid"}

        new_data, headers = ctx.prepare_token_auth(data, {})

        assert "client_id" not in new_data
        assert "client_secret" not in new_data
        assert headers["Authorization"].startswith("Basic ")

    def test_client_secret_post_keeps_client_id_in_body(self):
        ctx = self._context_with("client_secret_post")
        data = {"grant_type": "authorization_code", "code": "x", "client_id": "cid"}

        new_data, headers = ctx.prepare_token_auth(data, {})

        assert new_data["client_id"] == "cid"
        assert new_data["client_secret"] == "secret"
        assert "Authorization" not in headers


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
