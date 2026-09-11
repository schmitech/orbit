"""Shared fixtures.

Prerequisite handling is deliberately skip-not-fail: a stopped MCP server or an
absent API key is a missing prerequisite, not a behavioural regression, and
must never look like one in a test report.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcpeval.config import MCP_SERVER_DIR, Settings
from mcpeval.protocol import RawMcpClient, server_healthy


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture(scope="session")
def mcp_server(settings: Settings):
    """Ensure the sample MCP server is reachable.

    Autostart is opt-in (ORBIT_MCP_TEST_AUTOSTART=1) and never touches a server
    it did not start: if the port is already answering, it just yields. Starting
    Node from pytest is the classic source of flakiness in harnesses like this,
    so the documented path is to run `npm start` yourself.
    """
    if server_healthy(settings):
        yield settings
        return

    if not settings.autostart:
        pytest.skip(
            f"MCP server not reachable at {settings.health_url}. Start it with:\n"
            f"  cd {MCP_SERVER_DIR} && MCP_TOKEN=test-secret npm start\n"
            f"or set ORBIT_MCP_TEST_AUTOSTART=1 to let pytest manage it."
        )

    if not (MCP_SERVER_DIR / "node_modules").exists():
        pytest.skip(f"Autostart requested but {MCP_SERVER_DIR}/node_modules is missing — run npm install.")

    proc = subprocess.Popen(
        ["node", "src/server.js"],
        cwd=MCP_SERVER_DIR,
        env={**os.environ, "MCP_TOKEN": settings.mcp_token},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(30):
            if server_healthy(settings):
                break
            time.sleep(0.5)
        else:
            proc.terminate()
            pytest.skip(f"Autostarted MCP server never became healthy at {settings.health_url}.")
        yield settings
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def raw_client(mcp_server: Settings):
    with RawMcpClient(mcp_server) as client:
        yield client


@pytest.fixture(scope="session")
def unauthenticated_client(mcp_server: Settings) -> httpx.Client:
    with httpx.Client(timeout=10) as client:
        yield client
