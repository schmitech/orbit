"""
Integration tests for the real /mcp mount (fastmcp), not the docs-test dummy.

These exercise the actual mount + lifespan wiring end-to-end so a regression
like the one fixed here (wrong mount path, un-chained lifespan leaving the
StreamableHTTPSessionManager task group uninitialized) fails loudly instead
of only surfacing at runtime against a real deployment.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from inference_server import InferenceServer


class _DummyStaticFiles:
    def __init__(self, *args, **kwargs):
        pass

    async def __call__(self, scope, receive, send):
        return None


def _build_server(config: dict | None = None) -> InferenceServer:
    mock_logger = Mock()
    mock_thread_pool_manager = Mock()

    with patch("inference_server.load_config", return_value=config or {}), \
         patch("inference_server.LoggingConfigurator.setup_initial_logging", return_value=mock_logger), \
         patch("inference_server.LoggingConfigurator.setup_full_logging", return_value=mock_logger), \
         patch("inference_server.ConfigResolver"), \
         patch("inference_server.ServiceFactory"), \
         patch("inference_server.RouteConfigurator") as mock_route_configurator, \
         patch("inference_server.ConfigurationSummaryLogger"), \
         patch("inference_server.DatasourceFactory"), \
         patch("inference_server.ThreadPoolManager", return_value=mock_thread_pool_manager), \
         patch("inference_server.setup_aiohttp_session_tracking"), \
         patch("inference_server.StaticFiles", _DummyStaticFiles):
        mock_route_configurator.return_value.configure_routes.return_value = None
        server = InferenceServer(config_path="test-config.yaml")

    # Assigned as instance attributes (rather than patched on the class) so the
    # mocks stay in effect once the `with` block above exits and the app's
    # lifespan actually runs them from inside TestClient's context manager.
    server._initialize_services = AsyncMock()
    server._shutdown_services = AsyncMock()
    return server


@pytest.fixture
def mcp_client():
    server = _build_server()
    with TestClient(server.app) as client:
        yield client


def _initialize_body():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }


class TestMCPMount:
    def test_initialize_succeeds_at_mcp(self, mcp_client):
        """The mount path + chained lifespan must serve a real MCP handshake at /mcp."""
        response = mcp_client.post(
            "/mcp",
            json=_initialize_body(),
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "localhost",
            },
        )

        assert response.status_code == 200
        assert "mcp-session-id" in response.headers


class TestMCPHostValidation:
    def test_rejects_non_localhost_host_header(self, mcp_client):
        response = mcp_client.post(
            "/mcp",
            json=_initialize_body(),
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "evil.example.com",
            },
        )

        assert response.status_code == 400

    def test_rejects_non_localhost_origin_header(self, mcp_client):
        response = mcp_client.post(
            "/mcp",
            json=_initialize_body(),
            headers={
                "Accept": "application/json, text/event-stream",
                "Origin": "https://evil.example.com",
            },
        )

        assert response.status_code == 400

    def test_allows_localhost_host_header(self, mcp_client):
        response = mcp_client.post(
            "/mcp",
            json=_initialize_body(),
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1:3000",
            },
        )

        assert response.status_code == 200
