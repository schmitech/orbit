"""
Unit tests for editable connection fields on MCP servers in routes/admin/mcp.py:
_validate_mcp_connection (url/headers for http; command/args/env for stdio),
the _patch_yaml_scalars/_patch_yaml_map/
_patch_yaml_list line-patchers, and the update_mcp_server endpoint end-to-end
against a real mcp_clients.yaml on disk.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from fastapi import HTTPException

import routes.admin.mcp as admin_routes
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
      headers:
        Authorization: "Bearer ${MCP_TOKEN}"
      enabled: true

    - name: "headers-server"
      transport: "http"
      url: "https://example.com/headers-mcp"
      headers:
        Authorization: "Bearer ${OTHER_TOKEN}"
      enabled: true

    - name: "unrelated-headers-server"
      transport: "http"
      url: "https://example.com/mcp"
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

    def test_rejects_url_field_for_stdio(self):
        # url/headers are http-only; stdio has its own command/args/env keys.
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"url": "http://x"})
        assert exc.value.status_code == 422
        assert "url" in exc.value.detail

    def test_rejects_unknown_transport(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "grpc"}, {"url": "http://x"})
        assert exc.value.status_code == 422
        assert "grpc" in exc.value.detail

    def test_rejects_command_field_for_http(self):
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

    def test_rejects_legacy_token_field(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"token": "abc"})

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


class TestValidateMcpConnectionStdio:
    def test_accepts_command_args_env(self):
        admin_routes._validate_mcp_connection(
            {"transport": "stdio"},
            {"command": "uvx", "args": ["mcp-atlassian"], "env": {"JIRA_URL": "https://x"}},
        )

    def test_rejects_empty_command(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"command": "   "})
        assert exc.value.status_code == 422

    def test_rejects_non_string_command(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"command": 123})

    def test_rejects_command_over_maximum_length(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection(
                {"transport": "stdio"}, {"command": "x" * (admin_routes._MCP_CONNECTION_COMMAND_MAX_LENGTH + 1)}
            )
        assert exc.value.status_code == 422

    def test_rejects_command_with_control_characters(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"command": "npx\n-y"})

    def test_null_args_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "stdio"}, {"args": None})

    def test_empty_args_list_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "stdio"}, {"args": []})

    def test_rejects_non_list_args(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"args": "not-a-list"})

    def test_rejects_non_string_args_entry(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"args": ["-y", 5]})

    def test_rejects_too_many_args(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection(
                {"transport": "stdio"}, {"args": ["x"] * (admin_routes._MCP_CONNECTION_ARGS_MAX_COUNT + 1)}
            )

    def test_rejects_arg_over_maximum_length(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection(
                {"transport": "stdio"}, {"args": ["x" * (admin_routes._MCP_CONNECTION_ARG_MAX_LENGTH + 1)]}
            )

    def test_null_env_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": None})

    def test_empty_env_map_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": {}})

    def test_rejects_non_dict_env(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": ["FOO=bar"]})

    @pytest.mark.parametrize("bad_key", ["", "1FOO", "FOO-BAR", "FOO BAR", "foo.bar"])
    def test_rejects_invalid_env_key(self, bad_key):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": {bad_key: "x"}})
        assert exc.value.status_code == 422

    def test_rejects_non_string_env_value(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": {"FOO": 1}})

    def test_rejects_too_many_env_entries(self):
        env = {f"VAR_{i}": "x" for i in range(admin_routes._MCP_CONNECTION_ENV_MAX_ENTRIES + 1)}
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"env": env})


class TestValidateMcpConnectionHeaders:
    def test_rejects_headers_for_stdio(self):
        # MCPClientManager._open_session never reads headers in its stdio
        # branch (only http via _expand_headers) — persisting a header
        # edit for a stdio server would be a silent no-op, so it's rejected.
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "stdio"}, {"headers": {"X-Trace": "abc"}})
        assert exc.value.status_code == 422

    def test_accepts_headers_for_http(self):
        admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": {"X-Trace": "abc"}})

    def test_null_headers_is_allowed(self):
        admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": None})

    def test_rejects_non_dict_headers(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": "Authorization: x"})

    def test_rejects_non_string_header_value(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": {"X-Trace": 1}})

    def test_rejects_header_key_with_colon(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": {"X-Trace:": "abc"}})

    @pytest.mark.parametrize(
        "bad_key",
        [
            "X #evil",  # unquoted " #" mid-key turns the rest of the line into a YAML comment
            "#evil",  # a leading '#' after only whitespace makes the whole line a comment
            "X\"evil",  # an unescaped quote unbalances the line
            "X Y",  # header names never contain whitespace
            "",
        ],
    )
    def test_rejects_yaml_unsafe_or_malformed_header_key(self, bad_key):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": {bad_key: "value"}})
        assert exc.value.status_code == 422

    def test_rejects_header_key_over_maximum_length(self):
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection(
                {"transport": "http"},
                {"headers": {"X" * (admin_routes._MCP_CONNECTION_HEADER_KEY_MAX_LENGTH + 1): "value"}},
            )

    def test_accepts_header_key_with_underscore(self):
        admin_routes._validate_mcp_connection(
            {"transport": "http"}, {"headers": {"CMIT_MCP_TOKEN": "value"}}
        )

    def test_rejects_header_value_over_maximum_length(self):
        with pytest.raises(HTTPException) as exc:
            admin_routes._validate_mcp_connection(
                {"transport": "http"},
                {"headers": {"X-Trace": "x" * (admin_routes._MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH + 1)}},
            )
        assert exc.value.status_code == 422

    def test_accepts_header_value_at_maximum_length(self):
        admin_routes._validate_mcp_connection(
            {"transport": "http"},
            {"headers": {"X-Trace": "x" * admin_routes._MCP_CONNECTION_HEADER_VALUE_MAX_LENGTH}},
        )

    def test_rejects_too_many_headers(self):
        headers = {f"X-H{i}": "x" for i in range(admin_routes._MCP_CONNECTION_HEADER_MAX_ENTRIES + 1)}
        with pytest.raises(HTTPException):
            admin_routes._validate_mcp_connection({"transport": "http"}, {"headers": headers})

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


class TestPatchYamlMap:
    def _block(self, lines):
        """Full block used by these tests: header + a nested env: map."""
        return lines, 0, len(lines)

    def test_creates_block_when_absent(self):
        lines, start, end = self._block(["  - name: \"x\"", "    command: \"npx\""])
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {"FOO": "bar"}, "    ")
        assert result == [
            '  - name: "x"',
            '    command: "npx"',
            "    env:",
            '      FOO: "bar"',
        ]

    def test_empty_target_map_on_absent_block_is_a_noop(self):
        lines, start, end = self._block(["  - name: \"x\"", "    command: \"npx\""])
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {}, "    ")
        assert result == ["  - name: \"x\"", "    command: \"npx\""]

    def test_updates_existing_subkey(self):
        lines, start, end = self._block(
            ["  - name: \"x\"", "    env:", '      FOO: "old"']
        )
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {"FOO": "new"}, "    ")
        assert result == ["  - name: \"x\"", "    env:", '      FOO: "new"']

    def test_adds_new_subkey_to_existing_block(self):
        lines, start, end = self._block(
            ["  - name: \"x\"", "    env:", '      FOO: "bar"']
        )
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {"FOO": "bar", "BAZ": "qux"}, "    ")
        assert result == [
            "  - name: \"x\"",
            "    env:",
            '      FOO: "bar"',
            '      BAZ: "qux"',
        ]

    def test_removes_subkey_not_in_target_map(self):
        lines, start, end = self._block(
            ["  - name: \"x\"", "    env:", '      FOO: "bar"', '      BAZ: "qux"']
        )
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {"FOO": "bar"}, "    ")
        assert result == ["  - name: \"x\"", "    env:", '      FOO: "bar"']

    def test_empty_target_map_removes_block_header_too(self):
        lines, start, end = self._block(
            ["  - name: \"x\"", "    env:", '      FOO: "bar"', "    enabled: true"]
        )
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {}, "    ")
        assert result == ["  - name: \"x\"", "    enabled: true"]

    def test_does_not_disturb_trailing_comment_catalogue(self):
        lines, start, end = self._block(
            [
                "  - name: \"x\"",
                "    env:",
                '      FOO: "bar"',
                "",
                "  # - name: \"commented-out\"",
                "  #   env:",
                "  #     BAZ: qux",
            ]
        )
        result = admin_routes._patch_yaml_map(lines, start, end, "env", {}, "    ")
        assert result == [
            "  - name: \"x\"",
            "",
            "  # - name: \"commented-out\"",
            "  #   env:",
            "  #     BAZ: qux",
        ]

    def test_values_are_json_quoted(self):
        lines, start, end = self._block(["  - name: \"x\"", "    command: \"npx\""])
        result = admin_routes._patch_yaml_map(
            lines, start, end, "headers", {"Authorization": 'Bearer "weird" value'}, "    "
        )
        assert result[-1] == '      Authorization: "Bearer \\"weird\\" value"'

    def test_documents_why_map_keys_must_be_pre_validated(self):
        # _patch_yaml_map only quotes values, not keys (see _MCP_HEADER_KEY_RE's
        # docstring) — an unsafe key reaching this function corrupts the YAML
        # rather than raising. Callers (_validate_mcp_headers/_validate_mcp_env)
        # are the enforcement point; this test documents the failure mode they
        # exist to prevent, not a behavior to preserve.
        lines, start, end = self._block(["  - name: \"x\"", "    command: \"npx\""])
        result = admin_routes._patch_yaml_map(lines, start, end, "headers", {"X #evil": "value"}, "    ")
        reparsed = yaml.safe_load("\n".join(["mcp_clients:", "  servers:"] + ["  " + line for line in result]))
        server = reparsed["mcp_clients"]["servers"][0]
        assert server.get("headers") != {"X #evil": "value"}


class TestPatchYamlList:
    def test_creates_line_when_absent(self):
        lines = ["  - name: \"x\"", "    command: \"npx\""]
        result = admin_routes._patch_yaml_list(lines, 0, 2, "args", ["-y", "pkg"], "    ")
        assert result == ['  - name: "x"', '    command: "npx"', '    args: ["-y", "pkg"]']

    def test_replaces_existing_line(self):
        lines = ["  - name: \"x\"", '    args: ["-y", "old"]']
        result = admin_routes._patch_yaml_list(lines, 0, 2, "args", ["-y", "new"], "    ")
        assert result == ['  - name: "x"', '    args: ["-y", "new"]']

    def test_replaces_a_block_style_list_without_leaving_items_behind(self):
        lines = ["  - name: \"x\"", "    args:", "      - -y", "      - old", "    enabled: true"]
        result = admin_routes._patch_yaml_list(lines, 0, 5, "args", ["-y", "new"], "    ")
        assert result == ['  - name: "x"', '    args: ["-y", "new"]', "    enabled: true"]
        assert yaml.safe_load("\n".join(result))[0]["args"] == ["-y", "new"]

    def test_empty_list_is_written_explicitly(self):
        lines = ["  - name: \"x\"", '    args: ["-y", "old"]']
        result = admin_routes._patch_yaml_list(lines, 0, 2, "args", [], "    ")
        assert result == ['  - name: "x"', "    args: []"]

    def test_none_deletes_the_line(self):
        lines = ["  - name: \"x\"", '    args: ["-y", "old"]', "    enabled: true"]
        result = admin_routes._patch_yaml_list(lines, 0, 3, "args", None, "    ")
        assert result == ["  - name: \"x\"", "    enabled: true"]

    def test_unicode_args_round_trip_through_yaml(self):
        lines = ["  - name: \"x\""]
        result = admin_routes._patch_yaml_list(lines, 0, 1, "args", ["café", "北京"], "    ")
        parsed = yaml.safe_load("\n".join(result) + "\n")
        assert parsed[0]["name"] == "x"
        assert parsed[0]["args"] == ["café", "北京"]


class TestListMcpServersConnectionField:
    @pytest.mark.asyncio
    async def test_http_server_exposes_connection(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        result = await admin_routes.list_mcp_servers(request)

        by_name = {s["name"]: s for s in result["servers"]}
        assert by_name["http-server"]["connection"] == {
            "url": "http://127.0.0.1:9999/mcp",
            "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
        }
        assert by_name["headers-server"]["connection"]["headers"] == {"Authorization": "Bearer ${OTHER_TOKEN}"}

    @pytest.mark.asyncio
    async def test_stdio_server_exposes_command_args_env(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        result = await admin_routes.list_mcp_servers(request)

        by_name = {s["name"]: s for s in result["servers"]}
        assert by_name["stdio-server"]["connection"] == {
            "command": "npx",
            "args": ["-y", "some-package"],
            "env": {},
        }


class TestUpdateMcpServerConnection:
    @pytest.mark.asyncio
    async def test_updates_url_and_headers_on_disk(self, tmp_path):
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
                    {"connection": {"url": "http://localhost:8080/mcp", "headers": {"Authorization": "Bearer ${NEW_TOKEN}"}}},
                )

        assert result["reload_error"] is None
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        entry = next(s for s in written["mcp_clients"]["servers"] if s["name"] == "http-server")
        assert entry["url"] == "http://localhost:8080/mcp"
        assert entry["headers"] == {"Authorization": "Bearer ${NEW_TOKEN}"}

    @pytest.mark.asyncio
    async def test_rejects_http_only_field_for_stdio_server(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server(
                "stdio-server", request, {"connection": {"url": "http://x"}}
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_updates_command_args_env_for_stdio_server(self, tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}

        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=_fake_reload):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.update_mcp_server(
                    "stdio-server",
                    request,
                    {
                        "connection": {
                            "command": "uvx",
                            "args": ["mcp-atlassian"],
                            "env": {"JIRA_URL": "https://x", "JIRA_TOKEN": "${JIRA_TOKEN}"},
                        }
                    },
                )

        assert result["reload_error"] is None
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        entry = next(s for s in written["mcp_clients"]["servers"] if s["name"] == "stdio-server")
        assert entry["command"] == "uvx"
        assert entry["args"] == ["mcp-atlassian"]
        assert entry["env"] == {"JIRA_URL": "https://x", "JIRA_TOKEN": "${JIRA_TOKEN}"}
        # Unrelated servers and the surrounding structure are untouched.
        assert any(s["name"] == "http-server" for s in written["mcp_clients"]["servers"])

    @pytest.mark.asyncio
    async def test_removing_all_env_entries_drops_the_env_block(self, tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}

        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=_fake_reload):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                await admin_routes.update_mcp_server(
                    "stdio-server", request, {"connection": {"env": {"FOO": "bar"}}}
                )
                result = await admin_routes.update_mcp_server(
                    "stdio-server", request, {"connection": {"env": {}}}
                )

        assert result["reload_error"] is None
        written_text = (tmp_path / "mcp_clients.yaml").read_text()
        entry = next(
            s for s in yaml.safe_load(written_text)["mcp_clients"]["servers"] if s["name"] == "stdio-server"
        )
        assert "env" not in entry
        assert "env:" not in written_text

    @pytest.mark.asyncio
    async def test_updates_headers_for_http_transport(self, tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}

        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=_fake_reload):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.update_mcp_server(
                    "unrelated-headers-server", request, {"connection": {"headers": {"X-Trace": "abc"}}}
                )

        assert result["reload_error"] is None
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        entry = next(s for s in written["mcp_clients"]["servers"] if s["name"] == "unrelated-headers-server")
        assert entry["headers"] == {"X-Trace": "abc"}

    @pytest.mark.asyncio
    async def test_rejects_headers_edit_for_stdio_server(self, tmp_path):
        # headers is never read by the stdio branch of MCPClientManager._open_session —
        # persisting one would be a silent no-op, so the route rejects it.
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)

        with pytest.raises(HTTPException) as exc:
            await admin_routes.update_mcp_server(
                "stdio-server", request, {"connection": {"headers": {"X-Trace": "abc"}}}
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_legacy_token_edit(self, tmp_path):
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


class TestCreateMcpServer:
    @staticmethod
    def _reload_from_disk(tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}
        return _fake_reload

    @pytest.mark.asyncio
    async def test_creates_enabled_http_server_and_applies_it(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)
        with patch.object(admin_routes, "reload_adapters_config", side_effect=self._reload_from_disk(tmp_path)):
            with patch.object(mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])):
                result = await admin_routes.create_mcp_server(
                    request, {"name": "new-http", "transport": "http", "connection": {
                        "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${TOKEN}", "X-Api-Key": "${KEY}"},
                    }},
                )
        assert result["reload_error"] is None
        entry = next(s for s in yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]["servers"] if s["name"] == "new-http")
        assert entry == {"name": "new-http", "transport": "http", "url": "https://example.com/mcp", "headers": {"Authorization": "Bearer ${TOKEN}", "X-Api-Key": "${KEY}"}, "enabled": True}

    @pytest.mark.asyncio
    async def test_creates_stdio_server_with_args_and_env(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)
        with patch.object(admin_routes, "reload_adapters_config", side_effect=self._reload_from_disk(tmp_path)):
            with patch.object(mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])):
                await admin_routes.create_mcp_server(
                    request, {"name": "new-stdio", "transport": "stdio", "connection": {
                        "command": "uvx", "args": ["my-server"], "env": {"TOKEN": "${TOKEN}"},
                    }},
                )
        entry = next(s for s in yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]["servers"] if s["name"] == "new-stdio")
        assert entry["command"] == "uvx"
        assert entry["args"] == ["my-server"]
        assert entry["env"] == {"TOKEN": "${TOKEN}"}
        assert entry["enabled"] is True

    def test_inserts_before_a_commented_catalogue_when_no_server_is_active(self):
        lines = ["mcp_clients:", "  servers:", "    # - name: \"example\"", "    #   transport: \"stdio\""]
        result = admin_routes._insert_mcp_server(lines, {
            "name": "new-stdio", "transport": "stdio", "command": "uvx", "enabled": True,
        })
        parsed = yaml.safe_load("\n".join(result))
        assert parsed["mcp_clients"]["servers"] == [{
            "name": "new-stdio", "transport": "stdio", "command": "uvx", "enabled": True,
        }]
        assert result[-2:] == ["    # - name: \"example\"", "    #   transport: \"stdio\""]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body, status", [
        ({"name": "Bad Name", "transport": "http", "connection": {"url": "https://example.com/mcp"}}, 422),
        ({"name": "http-server", "transport": "http", "connection": {"url": "https://example.com/mcp"}}, 409),
        ({"name": "missing-url", "transport": "http", "connection": {}}, 422),
        ({"name": "unsupported", "transport": "sse", "connection": {"url": "https://example.com/sse"}}, 422),
    ])
    async def test_rejects_invalid_create_payload(self, tmp_path, body, status):
        config_path = _write_temp_config(tmp_path)
        with pytest.raises(HTTPException) as exc:
            await admin_routes.create_mcp_server(_fake_request(config_path), body)
        assert exc.value.status_code == status


class TestDeleteMcpServer:
    @staticmethod
    def _reload_from_disk(tmp_path):
        def _fake_reload(_config_path):
            return {"mcp_clients": yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())["mcp_clients"]}
        return _fake_reload

    @pytest.mark.asyncio
    async def test_removes_server_and_preserves_neighbors_and_comments(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        mcp_path = tmp_path / "mcp_clients.yaml"
        mcp_path.write_text(MCP_YAML.replace(
            '    - name: "headers-server"',
            '    # Catalogue notes remain after removal.\n    - name: "headers-server"',
        ), encoding="utf-8")
        request = _fake_request(config_path)

        with patch.object(admin_routes, "reload_adapters_config", side_effect=self._reload_from_disk(tmp_path)):
            with patch.object(
                mcp_client_service.MCPClientManager, "_list_tools_on_server", new=AsyncMock(return_value=[])
            ):
                result = await admin_routes.delete_mcp_server("headers-server", request)

        assert result["reload_error"] is None
        written_text = mcp_path.read_text()
        written = yaml.safe_load(written_text)["mcp_clients"]["servers"]
        assert {server["name"] for server in written} == {
            "http-server", "unrelated-headers-server", "stdio-server",
        }
        assert "Catalogue notes remain after removal." in written_text
        assert 'url: "https://example.com/headers-mcp"' not in written_text

    def test_removal_does_not_leave_same_indent_yaml_lines_behind(self):
        lines = [
            '    - name: "remove-me"',
            '    transport: "http"',
            '    url: "https://example.com/mcp"',
            '    # Keep this catalogue note.',
            '    - name: "keep-me"',
            '      transport: "stdio"',
        ]

        result = admin_routes._remove_mcp_server(lines, "remove-me")

        assert result == [
            '    # Keep this catalogue note.',
            '    - name: "keep-me"',
            '      transport: "stdio"',
        ]

    @pytest.mark.asyncio
    async def test_unknown_server_returns_404(self, tmp_path):
        with pytest.raises(HTTPException) as exc:
            await admin_routes.delete_mcp_server("does-not-exist", _fake_request(_write_temp_config(tmp_path)))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_persists_removal_when_reload_fails(self, tmp_path):
        config_path = _write_temp_config(tmp_path)
        request = _fake_request(config_path)
        with patch.object(admin_routes, "_reload_mcp_clients", side_effect=RuntimeError("reload unavailable")):
            result = await admin_routes.delete_mcp_server("stdio-server", request)

        assert result["reload_error"] == "reload unavailable"
        written = yaml.safe_load((tmp_path / "mcp_clients.yaml").read_text())
        assert all(server["name"] != "stdio-server" for server in written["mcp_clients"]["servers"])
