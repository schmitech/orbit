"""
Unit tests for `orbit key rotate-pepper --dry-run` (Phase 5 of the admin/API-key
security hardening plan).

Mocks ApiService's HTTP layer so these run without a live ORBIT server, unlike
test_cli_integration.py.
"""

import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bin.orbit.commands.keys import KeyRotatePepperCommand
from bin.orbit.services.api_service import ApiService
from bin.orbit.utils.exceptions import OrbitError


def _make_command(active_count: int, total_count: int):
    api_service = MagicMock(spec=ApiService)
    api_service.count_api_keys.side_effect = lambda active_only=False: (
        active_count if active_only else total_count
    )
    formatter = MagicMock()
    return KeyRotatePepperCommand(api_service, formatter), api_service, formatter


def test_dry_run_reports_active_and_total_counts():
    cmd, _api_service, formatter = _make_command(active_count=3, total_count=5)
    args = argparse.Namespace(dry_run=True, output='json')

    exit_code = cmd.execute(args)

    assert exit_code == 0
    formatter.format_json.assert_called_once_with({'active_keys': 3, 'total_keys': 5})


def test_dry_run_makes_no_writes():
    """count_api_keys is the only ApiService method rotate-pepper may call - it
    must never call any mutating key-management method."""
    cmd, api_service, _formatter = _make_command(active_count=0, total_count=0)
    args = argparse.Namespace(dry_run=True, output='table')

    cmd.execute(args)

    assert api_service.method_calls
    called_methods = {call[0] for call in api_service.method_calls}
    assert called_methods == {'count_api_keys'}


def test_without_dry_run_flag_makes_no_api_calls_and_errors():
    cmd, api_service, formatter = _make_command(active_count=1, total_count=1)
    args = argparse.Namespace(dry_run=False, output='table')

    exit_code = cmd.execute(args)

    assert exit_code == 1
    api_service.count_api_keys.assert_not_called()
    formatter.error.assert_called_once()


@pytest.mark.parametrize('payload', [{}, {'count': None}, {'count': -1}])
def test_count_api_keys_rejects_invalid_response(payload):
    api_client = MagicMock()
    api_client.get.return_value.json.return_value = payload
    auth_service = MagicMock()
    auth_service.token = 'test-token'
    service = ApiService(api_client, auth_service)

    with pytest.raises(OrbitError, match='Count API keys failed'):
        service.count_api_keys(active_only=True)
