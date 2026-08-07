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
    _apply_summary_overrides,
    _build_request_summary,
    _extract_ip,
    _match_route,
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
# _match_route — adapter lifecycle
# ---------------------------------------------------------------------------

class TestAdapterLifecycleRoutes:
    """Adapter create/delete are mutations, so they must not fall through to
    admin.unknown with no resource id."""

    def test_delete_adapter_is_mapped_with_resource_id(self):
        matched = _match_route("DELETE", "/admin/adapters/my-fetch")
        assert matched is not None
        entry, params = matched
        assert entry[2] == "admin.adapter.delete"
        assert entry[3] == "DELETE"
        assert entry[5] == "path:adapter_name"
        assert params == {"adapter_name": "my-fetch"}

    def test_create_adapter_is_mapped(self):
        matched = _match_route("POST", "/admin/adapters")
        assert matched is not None
        assert matched[0][2] == "admin.adapter.create"

    def test_create_mapping_does_not_swallow_the_preview_route(self):
        """Preview renders YAML and changes nothing; it must not be logged as a create."""
        matched = _match_route("POST", "/admin/adapters/preview")
        assert matched is None or matched[0][2] != "admin.adapter.create"


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


# ---------------------------------------------------------------------------
# _match_route — user blacklist
# ---------------------------------------------------------------------------

class TestBlacklistRoutes:
    """Blacklist mutations deny or restore a user's access, so they must be
    named events rather than falling through to admin.unknown."""

    def test_create_is_mapped_without_a_request_derived_resource_id(self):
        matched = _match_route("POST", "/auth/blacklist")
        assert matched is not None
        entry, params = matched
        assert entry[2] == "auth.blacklist.create"
        assert entry[3] == "CREATE"
        assert entry[4] == "blacklist_rule"
        # The rule id doesn't exist until the insert, and the submitted pattern
        # is not canonical, so this route explicitly opts into the handler-
        # supplied "context" source rather than deriving a misleading id.
        assert entry[5] == "context"
        assert params == {}

    def test_update_is_mapped_with_rule_id(self):
        matched = _match_route("PUT", "/auth/blacklist/abc123")
        assert matched is not None
        entry, params = matched
        assert entry[2] == "auth.blacklist.update"
        assert entry[3] == "UPDATE"
        assert entry[5] == "path:rule_id"
        assert params == {"rule_id": "abc123"}

    def test_delete_is_mapped_with_rule_id(self):
        matched = _match_route("DELETE", "/auth/blacklist/abc123")
        assert matched is not None
        entry, params = matched
        assert entry[2] == "auth.blacklist.delete"
        assert entry[3] == "DELETE"
        assert entry[5] == "path:rule_id"
        assert params == {"rule_id": "abc123"}

    def test_read_only_list_is_not_audited(self):
        """GET is outside _AUDITED_METHODS; it must have no mapping either."""
        assert _match_route("GET", "/auth/blacklist") is None

    def test_summary_records_who_was_blocked(self):
        """The pattern is the audit-relevant detail, and reason gives the why."""
        entry, _ = _match_route("POST", "/auth/blacklist")
        allowed = entry[6]
        summary = _build_request_summary(
            {"pattern": "*@spam-domain.com", "entry_type": "email", "reason": "abuse"},
            allowed,
        )
        assert summary == {
            "pattern": "*@spam-domain.com",
            "entry_type": "email",
            "reason": "abuse",
        }

    def test_delete_records_no_body_fields(self):
        entry, _ = _match_route("DELETE", "/auth/blacklist/abc123")
        assert _build_request_summary({"pattern": "x"}, entry[6]) is None


# ---------------------------------------------------------------------------
# audit_context — handler-published canonical values
# ---------------------------------------------------------------------------

class TestAuditContextOverrides:
    """A handler can publish what was actually persisted. Without this, the
    ledger records the raw request, which may not match the stored row — e.g. a
    blacklist pattern the service trims and lowercases before writing."""

    def _run(self, audit_context, body, path="/auth/blacklist", method="POST"):
        """Drive the middleware end-to-end and return the emitted record."""
        captured = {}

        audit_service = Mock()
        audit_service.admin_events_enabled = True

        async def log_admin_event(record):
            captured["record"] = record

        audit_service.log_admin_event = AsyncMock(side_effect=log_admin_event)

        app = FastAPI()
        app.add_middleware(AdminAuditMiddleware, config={})
        app.state.audit_service = audit_service

        @app.post("/auth/blacklist")
        async def create(request: Request):
            if audit_context is not None:
                request.state.audit_context = audit_context
            return {"ok": True}

        @app.put("/auth/blacklist/{rule_id}")
        async def update(rule_id: str, request: Request):
            if audit_context is not None:
                request.state.audit_context = audit_context
            return {"ok": True}

        with TestClient(app) as client:
            client.request(method, path, json=body)

        return captured.get("record")

    def test_resource_id_and_summary_use_canonical_values(self):
        record = self._run(
            {"resource_id": "rule-1", "summary": {"pattern": "abuser@example.com"}},
            {"pattern": "  ABUSER@Example.COM  ", "entry_type": "email"},
        )
        assert record is not None
        # The stored rule id, not the submitted pattern.
        assert record.resource_id == "rule-1"
        # The normalized pattern, not the raw one an auditor can't search for.
        assert record.request_summary["pattern"] == "abuser@example.com"
        # Non-overridden allowlisted fields still come through.
        assert record.request_summary["entry_type"] == "email"

    def test_without_context_create_has_no_resource_id(self):
        """A failed create has no rule to point at; the raw pattern must not
        stand in for one."""
        record = self._run(None, {"pattern": "  ABUSER@Example.COM  ", "entry_type": "email"})
        assert record is not None
        assert record.resource_id is None
        # What was attempted is still recorded, verbatim as submitted.
        assert record.request_summary["pattern"] == "  ABUSER@Example.COM  "

    def test_context_cannot_displace_a_path_derived_resource_id(self):
        """PUT derives its id from the path, so it does not use the "context"
        source. A handler must not be able to overwrite that id — it is
        long-lived audit data, and the route's own source is the trusted one."""
        record = self._run(
            {"resource_id": "orbit_live_smuggled_secret", "summary": {}},
            {"pattern": "x@example.com", "entry_type": "email"},
            path="/auth/blacklist/raw-id",
            method="PUT",
        )
        assert record is not None
        assert record.resource_id == "raw-id"

    def test_route_without_context_source_ignores_a_published_id(self):
        """A route that declares no resource id must stay without one. Accepting
        a handler-published id globally would let any audited route write
        arbitrary values into long-lived audit storage."""
        captured = {}

        audit_service = Mock()
        audit_service.admin_events_enabled = True

        async def log_admin_event(record):
            captured["record"] = record

        audit_service.log_admin_event = AsyncMock(side_effect=log_admin_event)

        app = FastAPI()
        app.add_middleware(AdminAuditMiddleware, config={})
        app.state.audit_service = audit_service

        # /admin/reload-adapters declares source None and an empty allowlist.
        @app.post("/admin/reload-adapters")
        async def reload_adapters(request: Request):
            request.state.audit_context = {
                "resource_id": "orbit_live_smuggled_secret",
                "summary": {"password": "hunter2"},
            }
            return {"ok": True}

        with TestClient(app) as client:
            client.post("/admin/reload-adapters", json={})

        record = captured["record"]
        assert record.event_type == "admin.adapter.reload"
        assert record.resource_id is None
        assert record.request_summary is None

    def test_handler_cannot_smuggle_a_secret_into_the_ledger(self):
        """End-to-end proof that dispatch routes overrides through the allowlist.

        Unit-testing _apply_summary_overrides is not enough: dispatch must
        actually call it, or a handler publishing a credential writes it to the
        admin ledger despite the route excluding that field.
        """
        record = self._run(
            {
                "resource_id": "rule-1",
                "summary": {
                    "pattern": "abuser@example.com",
                    "password": "hunter2",
                    "api_key": "orbit_live_secret",
                },
            },
            {"pattern": "abuser@example.com", "entry_type": "email"},
        )
        assert record is not None
        assert record.request_summary["pattern"] == "abuser@example.com"
        assert "password" not in record.request_summary
        assert "api_key" not in record.request_summary

    def test_malformed_context_is_ignored(self):
        """A handler publishing garbage must not break the audit write."""
        record = self._run(
            "not-a-dict",
            {"pattern": "x@example.com", "entry_type": "email"},
        )
        assert record is not None
        assert record.request_summary["pattern"] == "x@example.com"


# ---------------------------------------------------------------------------
# _apply_summary_overrides — the redaction contract holds for handlers too
# ---------------------------------------------------------------------------

class TestSummaryOverrideAllowlist:
    """The per-route allowlist is what keeps secrets out of the ledger. It must
    constrain handler-published values exactly as it constrains request bodies,
    or request.state.audit_context becomes a way around it."""

    def test_field_outside_allowlist_is_dropped(self):
        merged = _apply_summary_overrides(
            {"username": "alice"},
            {"username": "alice", "password": "hunter2", "api_key": "orbit_live_abc"},
            ("username", "role"),
        )
        assert merged == {"username": "alice"}
        assert "password" not in merged
        assert "api_key" not in merged

    def test_allowlisted_field_is_applied(self):
        merged = _apply_summary_overrides(
            {"pattern": "  RAW@Example.COM  "},
            {"pattern": "raw@example.com"},
            ("pattern", "entry_type", "reason"),
        )
        assert merged == {"pattern": "raw@example.com"}

    def test_none_override_clears_the_field(self):
        """A reason submitted as whitespace normalizes to None on write; the
        ledger should not keep showing the raw spaces."""
        merged = _apply_summary_overrides(
            {"pattern": "x@example.com", "reason": "   "},
            {"pattern": "x@example.com", "reason": None},
            ("pattern", "reason"),
        )
        assert merged == {"pattern": "x@example.com"}

    def test_empty_allowlist_accepts_no_overrides(self):
        """A route recording nothing must keep recording nothing."""
        assert _apply_summary_overrides(None, {"pattern": "x"}, ()) is None

    def test_changed_keys_routes_accept_no_overrides(self):
        summary = {"changed_keys": ["a", "b"]}
        merged = _apply_summary_overrides(summary, {"value": "secret"}, _CHANGED_KEYS)
        assert merged == {"changed_keys": ["a", "b"]}

    def test_non_dict_override_is_ignored(self):
        summary = {"username": "alice"}
        assert _apply_summary_overrides(summary, "nope", ("username",)) == summary
        assert _apply_summary_overrides(summary, None, ("username",)) == summary

    def test_clearing_every_field_yields_none(self):
        assert _apply_summary_overrides({"reason": "x"}, {"reason": None}, ("reason",)) is None
