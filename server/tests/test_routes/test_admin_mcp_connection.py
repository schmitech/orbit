"""
Unit tests for editable http/sse connection fields (url/token) on MCP servers
in admin_routes.py: _validate_mcp_connection, quoted string patching in
_patch_yaml_scalars, and the update_mcp_server endpoint end-to-end against a
real mcp_clients.yaml on disk.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastapi import HTTPException

import routes.admin_routes as admin_routes
import services.mcp_client_service as mcp_client_service


@pytest.fixture(autouse=True)
def _reset_mcp_singleton():
    mcp_client_service._instance = None
    yield
    mcp_client_service._instance = None


MCP_YAML = """mcp_clients:
  enabled: true
  tool_timeout: 30

  servers:
    - name: "http-server"
      transport: "http"
      url: "http://127.0.0.1:9999/mcp"
      token: "${MCP_TOKEN}"
      enabled: true

    - name: "headers-server"
      transport: "sse"
      url: "https://example.com/sse"
      headers:
        Authorization: "Bearer ${OTHER_TOKEN}"
      enabled: true

    - name: "unrelated-headers-server"
      transport: "http"
      url: "https://example.com/mcp"
      token: "${SOME_TOKEN}"
      headers:
        X-API-Key: "${SOME_API_KEY}"
        X-Tenant: "acme"
      enabled: true

    - name: "stdio-server"
      transport: "stdio"
      command: "npx"
      args: ["-y", "some-package"]
      enabled: true
"""


def _write_temp_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("import:\n  - mcp_clients.yaml\n", encoding="utf-8")
    (tmp_path / "mcp_clients.yaml").write_text(MCP_YAML, encoding="utf-8")
    return config_path


def _fake_request(config_path: Path, config=None):
    state = SimpleNamespace(config=config if config is not None else {}, config_path=str(config_path))
    return SimpleNamespace(app=SimpleNamespace(state=state))


class TestValidateMcpConnection:
    def test_empty_connection_is_a_noop(self):
        admin_routes._validate_mcp_connection({"transport": "stdio"}, {})

    def test_rejects_stdio(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"url": "http://x"})
        assert exc.value.status_code == 422
        assert "stdio" in exc.value.detail

    def test_rejects_unknown_field(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "http"}, {"command": "npx"})
        assert exc.value.status_code == 422
        assert "command" in exc.value.detail

    def test_rejects_empty_url(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"url": "   "})

    @pytest.mark.parametrize(
        "url",
        [
            "example.com/mcp",
            "ftp://example.com/mcp",
            "file:///etc/passwd",
            "https://",
            "https://example.com/mcp#fragment",
            "https://example.com/mcp path",
            "https://example.com:99999/mcp",
        ],
    )
    def test_rejects_malformed_or_unsupported_urls(self, url):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "http"}, {"url": url})
        assert exc.value.status_code == 422

    def test_rejects_url_over_maximum_length(self):
        url = "https://example.com/" + "x" * admin_routes._MCP_CONNECTION_URL_MAX_LENGTH
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "http"}, {"url": url})
        assert exc.value.status_code == 422
        assert "2048" in exc.value.detail

    def test_rejects_non_string_token(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"token": 123})

    def test_rejects_token_over_maximum_length(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection(
                {"transport": "http"}, {"token": "x" * (admin_routes._MCP_CONNECTION_TOKEN_MAX_LENGTH + 1)}
            )
        assert exc.value.status_code == 422
        assert "8192" in exc.value.detail

    def test_null_token_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "http"}, {"token": None})

    def test_rejects_token_when_authorization_header_present(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection(
                {"transport": "sse", "headers": {"Authorization": "Bearer x"}},
                {"token": "new-token"},
            )
        assert "Authorization" in exc.value.detail

    def test_rejects_token_when_authorization_header_present_lowercase_key(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection(
                {"transport": "sse", "headers": {"authorization": "Bearer x"}},
                {"token": "new-token"},
            )

    def test_accepts_token_when_headers_are_unrelated(self):
        # Only an explicit Authorization header overrides the token shorthand
        # (see _expand_headers) — X-API-Key/X-Tenant do not conflict with it.
        admin_routes._validate_mcp_connection(
            {"transport": "http", "headers": {"X-API-Key": "x", "X-Tenant": "acme"}},
            {"token": "new-token"},
        )

    def test_accepts_valid_url_and_token(self):
        admin_routes._validate_mcp_connection(
            {"transport": "http"}, {"url": "http://localhost:8080/mcp", "token": "abc"}
        )

    def test_rejects_non_dict_connection(self):
        for bad in ("url", 1, ["url"], True):
            with pytest.raises(HTTPException) as exc:
                admin_routes._validate_mcp_connection({"transport": "http"}, bad)
            assert exc.value.status_code == 422

    def test_falsy_non_dict_connection_is_a_noop(self):
        # Falsy values (None, {}, "", 0) short-circuit before the type check —
        # only a truthy non-dict is a client error.
        admin_routes._validate_mcp_connection({"transport": "stdio"}, None)
        admin_routes._validate_mcp_connection({"transport": "stdio"}, "")
        admin_routes._validate_mcp_connection({"transport": "stdio"}, 0)


class TestValidateMcpSettings:
    def test_rejects_non_dict_settings(self):
        overridable = admin_routes._mcp_overridable()
        for bad in ("tool_timeout", 1, ["tool_timeout"], True):
            with pytest.raises(HTTPException) as exc:
                admin_routes._validate_mcp_settings(bad, overridable)
            assert exc.value.status_code == 422

    def test_falsy_non_dict_settings_is_a_noop(self):
        overridable = admin_routes._mcp_overridable()
        admin_routes._validate_mcp_settings(None, overridable)
        admin_routes._validate_mcp_settings("", overridable)
        admin_routes._validate_mcp_settings(0, overridable)


class TestPatchYamlScalarsQuoting:
    def test_string_value_is_quoted(self):
        lines = ["    url: \"http://old/mcp\""]
        result = admin_routes._patch_yaml_scalars(lines, 0, 1, {"url": "http://new:9999/mcp"}, "    ")
        assert result == ['    url: "http://new:9999/mcp"']

    def test_int_value_is_not_quoted(self):
        lines = ["    tool_timeout: 30"]
        result = admin_routes._patch_yaml_scalars(lines, 0, 1, {"tool_timeout": 60}, "    ")
        assert result == ["    tool_timeout: 60"]

    def test_none_deletes_string_line(self):
        lines = ["    token: \"abc\"", "    other: 1"]
        result = admin_routes._patch_yaml_scalars(lines, 0, 2, {"token": None}, "    ")
        assert result == ["    other: 1"]


class TestListMcpServersConnectionField:
    @pytest.mark.asyncio
    async def test_http_server_exposes_connection(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        result = await admin_routes.list_mcp_servers(request)

        by_name = {s["name"]: s for s in result["servers"]}
        assert by_name["http-server"]["connection"] == {
            "url": "http://127.0.0.1:9999/mcp",
            "token": "${MCP_TOKEN}",
            "uses_custom_headers": False,
        }
        assert by_name["headers-server"]["connection"]["uses_custom_headers"] is True
        assert by_name["unrelated-headers-server"]["connection"]["uses_custom_headers"] is False
        assert by_name["stdio-server"]["connection"] is None


class TestUpdateMcpServerConnection:
    @pytest.mark.asyncio
    async def test_updates_url_and_token_on_disk(self, tmp_path):
        # The real config loader requires a fully valid config.yaml (auth
        # secrets, etc.) that isn't the point of this test — stub the reload
        # step to just re-parse mcp_clients.yaml from disk, so the assertion
        # focuses on what update_mcp_server actually wrote.
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}

        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=_fake_reload):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.update_mcp_server(
                    "http-server",
                    request,
                    {"connection": {"url": "http://localhost:8080/mcp", "token": "${NEW_TOKEN}"}},
                )

        assert result["reload_error"] is None
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        entry = next(s for s in written["mcp_clients"]["servers"] if s["name"] == "http-server")
        assert entry["url"] == "http://localhost:8080/mcp"
        assert entry["token"] == "${NEW_TOKEN}"

    @pytest.mark.asyncio
    async def test_rejects_connection_edit_for_stdio_server(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server(
                "stdio-server", request, {"connection": {"url": "http://x"}}
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_token_edit_for_headers_server(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server(
                "headers-server", request, {"connection": {"token": "should-fail"}}
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_unknown_server_returns_404(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server(
                "does-not-exist", request, {"connection": {"url": "http://x"}}
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_allows_token_edit_when_headers_are_unrelated(self, tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}

        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=_fake_reload):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.update_mcp_server(
                    "unrelated-headers-server",
                    request,
                    {"connection": {"token": "${NEW_TOKEN}"}},
                )

        assert result["reload_error"] is None
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        entry = next(
            s for s in written["mcp_clients"]["servers"] if s["name"] == "unrelated-headers-server"
        )
        assert entry["token"] == "${NEW_TOKEN}"
        # The unrelated headers are untouched.
        assert entry["headers"]["X-API-Key"] == "${SOME_API_KEY}"

    @pytest.mark.asyncio
    async def test_non_dict_connection_body_returns_422_not_500(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server("http-server", request, {"connection": "http://x"})
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_non_dict_settings_body_returns_422_not_500(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server("http-server", request, {"settings": "tool_timeout"})
        assert exc.value.status_code == 422
