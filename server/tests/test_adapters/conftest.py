"""
Conftest for adapter tests.

- Adds server/ and project root to sys.path so imports resolve
  regardless of where pytest is invoked from.
- Auto-skips integration tests (marked with @pytest.mark.integration)
  unless --run-integration is passed.
"""

import sys
from pathlib import Path

import pytest

# Resolve paths from this file's location (server/tests/test_adapters/conftest.py)
_this = Path(__file__).resolve()
_server_root = str(_this.parents[2])   # .../orbit/server
_project_root = str(_this.parents[3])  # .../orbit

# server/ must be on sys.path (for 'from adapters...', 'from services...', etc.)
if _server_root not in sys.path:
    sys.path.insert(0, _server_root)

# project root must also be on sys.path (for 'from server.ai_services...' style imports)
if _project_root not in sys.path:
    sys.path.insert(1, _project_root)


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require a running server",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(reason="needs --run-integration option and a running server")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
