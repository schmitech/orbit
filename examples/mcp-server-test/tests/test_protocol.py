"""Protocol conformance for the sample MCP server. No LLM, no API keys.

These are the contract the rest of the harness stands on: if the server stops
behaving this way, ground-truth resolution is meaningless and every agent score
becomes unattributable. Fail here first, loudly.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.integration

EXPECTED_TOOLS = {
    "build_account_plan",
    "create_support_ticket",
    "delete_support_ticket",
    "get_customer_health",
    "get_product_telemetry",
    "get_sales_rep_performance",
    "get_support_ticket",
    "list_customers",
    "list_support_tickets",
    "search_opportunities",
    "simulate_churn_risk_scenario",
    "summarize_pipeline",
    "update_support_ticket",
}


def test_health_endpoint(raw_client):
    health = raw_client.health()
    assert health["ok"] is True
    assert health["name"] == "orbit-business-sample"


def test_initialize_handshake(raw_client):
    info = raw_client.initialize()
    assert info["serverInfo"]["name"] == "orbit-business-sample"


def test_all_thirteen_tools_are_discoverable(raw_client):
    assert set(raw_client.tool_names()) == EXPECTED_TOOLS


def test_every_tool_declares_a_description_and_schema(raw_client):
    for tool in raw_client.list_tools():
        assert tool.get("description"), f"{tool['name']} has no description"
        assert tool.get("inputSchema", {}).get("type") == "object", tool["name"]


def test_get_on_mcp_path_is_rejected(mcp_server):
    """The endpoint is POST-only.

    Pinned because the Python MCP client opens a GET SSE stream after
    initialize; the adapter tolerates the 405 today, and this test makes it
    obvious if that assumption ever changes.
    """
    response = httpx.get(mcp_server.mcp_url, headers=mcp_server.auth_headers, timeout=5)
    assert response.status_code == 405


def test_missing_bearer_token_is_unauthorized(mcp_server, unauthenticated_client):
    if not mcp_server.mcp_token:
        pytest.skip("MCP_TOKEN is empty, so the server has auth disabled.")
    response = unauthenticated_client.post(mcp_server.mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
