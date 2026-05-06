"""
Tests for AdminAuditMiddleware.

Covers:
- _parse_trusted_networks: valid CIDRs, invalid entries, empty input
- _extract_ip: direct IP, proxy headers with trust disabled/enabled, empty trusted networks
- _read_and_replay_body: normal body, Content-Length guard, downstream readability
- AdminAuditMiddleware.__init__: proxy config parsing, defaults
- dispatch: skip non-audited methods/paths, pass through when audit service absent
"""

import ipaddress
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from middleware.admin_audit_middleware import (
    _MAX_BODY_BYTES,
    _CHANGED_KEYS,
    AdminAuditMiddleware,
    _build_request_summary,
    _extract_ip,
    _parse_trusted_networks,
    _read_and_replay_body,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_request(
    headers: Optional[dict] = None,
    client_host: Optional[str] = "127.0.0.1",
) -> Mock:
    req = Mock()
    req.headers = headers or {}
    req.client = Mock(host=client_host) if client_host else None
    return req


def _starlette_request(body: bytes, content_length: Optional[int] = None) -> Request:
    """Build a real Starlette Request with a capturable body."""
    raw_headers = []
    if content_length is not None:
        raw_headers.append((b"content-length", str(content_length).encode()))

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/admin/test",
        "query_string": b"",
        "headers": raw_headers,
    }
    return Request(scope, receive=receive)


# ---------------------------------------------------------------------------
# _parse_trusted_networks
# ---------------------------------------------------------------------------

class TestParseTrustedNetworks:
    def test_valid_cidr_ranges(self):
        nets = _parse_trusted_networks(["10.0.0.0/8", "192.168.1.0/24"])
        assert len(nets) == 2
        assert ipaddress.ip_address("10.1.2.3") in nets[0]
        assert ipaddress.ip_address("192.168.1.100") in nets[1]

    def test_single_host_address(self):
        nets = _parse_trusted_networks(["127.0.0.1"])
        assert len(nets) == 1
        assert ipaddress.ip_address("127.0.0.1") in nets[0]

    def test_invalid_entry_skipped(self):
        nets = _parse_trusted_networks(["not-an-ip", "10.0.0.0/8"])
        assert len(nets) == 1

    def test_empty_list(self):
        assert _parse_trusted_networks([]) == []


# ---------------------------------------------------------------------------
# _extract_ip
# ---------------------------------------------------------------------------

class TestExtractIP:
    def test_direct_ip_no_proxy_header(self):
        req = _make_mock_request(client_host="1.2.3.4")
        ip, meta = _extract_ip(req)
        assert ip == "1.2.3.4"
        assert meta["source"] == "direct"

    def test_proxy_header_ignored_when_trust_disabled(self):
        req = _make_mock_request(
            headers={"x-forwarded-for": "8.8.8.8"},
            client_host="1.2.3.4",
        )
        ip, meta = _extract_ip(req, trust_proxy=False)
        assert ip == "1.2.3.4"
        assert meta["source"] == "direct"

    def test_proxy_header_ignored_when_trusted_networks_empty(self):
        """Empty trusted_networks = deny all proxy headers (deny-by-default)."""
        req = _make_mock_request(
            headers={"x-forwarded-for": "8.8.8.8"},
            client_host="10.0.0.1",
        )
        ip, meta = _extract_ip(req, trust_proxy=True, trusted_networks=[])
        assert ip == "10.0.0.1"
        assert meta["source"] == "direct"

    def test_proxy_header_accepted_from_trusted_network(self):
        networks = _parse_trusted_networks(["10.0.0.0/8"])
        req = _make_mock_request(
            headers={"x-forwarded-for": "8.8.8.8, 10.0.0.1"},
            client_host="10.0.0.1",
        )
        ip, meta = _extract_ip(req, trust_proxy=True, trusted_networks=networks)
        assert ip == "8.8.8.8"
        assert meta["source"] == "proxy"

    def test_proxy_header_rejected_from_untrusted_network(self):
        networks = _parse_trusted_networks(["10.0.0.0/8"])
        req = _make_mock_request(
            headers={"x-forwarded-for": "8.8.8.8"},
            client_host="192.168.1.100",
        )
        ip, meta = _extract_ip(req, trust_proxy=True, trusted_networks=networks)
        assert ip == "192.168.1.100"
        assert meta["source"] == "direct"

    def test_localhost_normalized(self):
        req = _make_mock_request(client_host="127.0.0.1")
        ip, meta = _extract_ip(req)
        assert ip == "localhost"
        assert meta["isLocal"] is True

    def test_ipv6_localhost_normalized(self):
        req = _make_mock_request(client_host="::1")
        ip, meta = _extract_ip(req)
        assert ip == "localhost"
        assert meta["isLocal"] is True

    def test_no_client_returns_unknown(self):
        req = Mock()
        req.headers = {}
        req.client = None
        ip, meta = _extract_ip(req)
        assert ip == "unknown"

    def test_ipv4_mapped_ipv6_stripped(self):
        req = _make_mock_request(client_host="::ffff:1.2.3.4")
        ip, meta = _extract_ip(req)
        assert ip == "1.2.3.4"
        assert meta["type"] == "ipv4"


# ---------------------------------------------------------------------------
# _read_and_replay_body
# ---------------------------------------------------------------------------

class TestReadAndReplayBody:
    @pytest.mark.asyncio
    async def test_small_body_captured(self):
        body = b'{"key": "value"}'
        req = _starlette_request(body)
        result = await _read_and_replay_body(req)
        assert result == body

    @pytest.mark.asyncio
    async def test_oversized_content_length_returns_empty_without_reading(self):
        """Content-Length above cap → skip read entirely; return b''."""
        oversized = _MAX_BODY_BYTES + 1
        req = _starlette_request(b"x" * 10, content_length=oversized)
        result = await _read_and_replay_body(req)
        assert result == b""

    @pytest.mark.asyncio
    async def test_body_still_readable_downstream_after_capture(self):
        """Starlette caches body in _body; downstream request.body() still works."""
        body = b'{"action": "create"}'
        req = _starlette_request(body)
        captured = await _read_and_replay_body(req)
        downstream = await req.body()
        assert captured == body
        assert downstream == body

    @pytest.mark.asyncio
    async def test_empty_body_captured(self):
        req = _starlette_request(b"")
        result = await _read_and_replay_body(req)
        assert result == b""


# ---------------------------------------------------------------------------
# _build_request_summary
# ---------------------------------------------------------------------------

class TestBuildRequestSummary:
    def test_none_body_returns_none(self):
        assert _build_request_summary(None, ("key",)) is None

    def test_changed_keys_sentinel(self):
        body = {"a": 1, "b": 2, "password": "secret"}
        summary = _build_request_summary(body, _CHANGED_KEYS)
        assert summary == {"changed_keys": ["a", "b", "password"]}

    def test_allowlist_filters_fields(self):
        body = {"username": "alice", "password": "secret", "role": "admin"}
        summary = _build_request_summary(body, ("username", "role"))
        assert summary == {"username": "alice", "role": "admin"}
        assert "password" not in summary

    def test_empty_allowlist_returns_none(self):
        body = {"username": "alice"}
        assert _build_request_summary(body, ()) is None

    def test_none_values_excluded(self):
        body = {"username": "alice", "notes": None}
        summary = _build_request_summary(body, ("username", "notes"))
        assert summary == {"username": "alice"}
        assert "notes" not in summary


# ---------------------------------------------------------------------------
# AdminAuditMiddleware.__init__
# ---------------------------------------------------------------------------

class TestAdminAuditMiddlewareInit:
    def test_defaults_when_no_config(self):
        app = FastAPI()
        m = AdminAuditMiddleware(app, config=None)
        assert m._trust_proxy is False
        assert m._trusted_networks == []

    def test_proxy_trust_config_parsed(self):
        app = FastAPI()
        config = {
            "security": {
                "rate_limiting": {
                    "trust_proxy_headers": True,
                    "trusted_proxies": ["10.0.0.0/8", "172.16.0.0/12"],
                }
            }
        }
        m = AdminAuditMiddleware(app, config=config)
        assert m._trust_proxy is True
        assert len(m._trusted_networks) == 2

    def test_empty_trusted_proxies_with_trust_enabled(self):
        """trust_proxy=True + empty list → deny-by-default in _extract_ip."""
        app = FastAPI()
        config = {
            "security": {
                "rate_limiting": {
                    "trust_proxy_headers": True,
                    "trusted_proxies": [],
                }
            }
        }
        m = AdminAuditMiddleware(app, config=config)
        assert m._trust_proxy is True
        assert m._trusted_networks == []


# ---------------------------------------------------------------------------
# AdminAuditMiddleware.dispatch
# ---------------------------------------------------------------------------

class TestAdminAuditMiddlewareDispatch:
    def _build_app(self, config=None):
        app = FastAPI()
        app.add_middleware(AdminAuditMiddleware, config=config or {})

        @app.get("/admin/api-keys")
        def list_keys():
            return []

        @app.post("/admin/api-keys")
        def create_key():
            return {"key": "new"}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        return app

    def test_get_request_not_audited(self):
        """GET requests on admin paths are never audited."""
        app = self._build_app()
        mock_audit = Mock()
        mock_audit.admin_events_enabled = True
        mock_audit.log_admin_event = AsyncMock()
        app.state.audit_service = mock_audit

        client = TestClient(app)
        response = client.get("/admin/api-keys")
        assert response.status_code == 200
        mock_audit.log_admin_event.assert_not_called()

    def test_post_to_non_admin_path_not_audited(self):
        """POST to a non-admin/non-auth path is not audited."""
        app = FastAPI()
        app.add_middleware(AdminAuditMiddleware, config={})

        @app.post("/v1/chat")
        def chat():
            return {}

        mock_audit = Mock()
        mock_audit.admin_events_enabled = True
        mock_audit.log_admin_event = AsyncMock()
        app.state.audit_service = mock_audit

        client = TestClient(app)
        client.post("/v1/chat", json={"message": "hi"})
        mock_audit.log_admin_event.assert_not_called()

    def test_pass_through_when_no_audit_service(self):
        """No audit service → request proceeds normally, no error."""
        app = self._build_app()
        client = TestClient(app)
        response = client.post("/admin/api-keys")
        assert response.status_code == 200

    def test_pass_through_when_audit_service_disabled(self):
        """Audit service present but admin_events_enabled=False → no audit."""
        app = self._build_app()
        mock_audit = Mock()
        mock_audit.admin_events_enabled = False
        mock_audit.log_admin_event = AsyncMock()
        app.state.audit_service = mock_audit

        client = TestClient(app)
        client.post("/admin/api-keys")
        mock_audit.log_admin_event.assert_not_called()
