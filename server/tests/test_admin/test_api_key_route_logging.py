"""
Functional tests for API key lifecycle logging in admin_routes.py.

These call the route handler coroutines directly (bypassing FastAPI's HTTP
layer and dependency injection) with mocked services, and assert on the
emitted log records via caplog. This covers two regressions fixed in this
module:

  1. Raw API keys / record identifiers must never appear unmasked in logs.
     `api_key_id` path params are resolved by record _id OR raw api_key value
     (see api_key_service._resolve_key_doc), so any endpoint that logs
     `api_key_id` directly risks leaking a real key.
  2. Successful create/rename/update/deactivate/delete of an API key must be
     logged at INFO (the standard audit level for lifecycle actions), not
     DEBUG.
"""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routes import admin_routes


RAW_KEY_LOOKING_ID = "sk-live-abcdefghijklmnopqrstuvwxyz"


def make_request(**state_kwargs) -> SimpleNamespace:
    """Minimal stand-in for FastAPI's Request, exposing app.state.<service>."""
    state = SimpleNamespace(**state_kwargs)
    app = SimpleNamespace(state=state)
    return SimpleNamespace(app=app)


class TestDeleteApiKeyLogging:

    @pytest.mark.asyncio
    async def test_logs_at_info_level(self, caplog):
        service = SimpleNamespace(delete_api_key_by_id=AsyncMock(return_value=True))
        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            result = await admin_routes.delete_api_key(RAW_KEY_LOOKING_ID, api_key_service=service)

        assert result == {"status": "success", "message": "API key deleted"}
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("Deleted API key" in r.message for r in info_records), (
            "Delete must be logged at INFO so it is visible in production logs, "
            "matching create/rename/update/deactivate"
        )

    @pytest.mark.asyncio
    async def test_does_not_leak_raw_identifier(self, caplog):
        service = SimpleNamespace(delete_api_key_by_id=AsyncMock(return_value=True))
        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            await admin_routes.delete_api_key(RAW_KEY_LOOKING_ID, api_key_service=service)

        for record in caplog.records:
            assert RAW_KEY_LOOKING_ID not in record.message


class TestDeactivateApiKeyLogging:

    @pytest.mark.asyncio
    async def test_logs_at_info_level(self, caplog):
        service = SimpleNamespace(deactivate_api_key_by_id=AsyncMock(return_value=True))
        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            await admin_routes.deactivate_api_key(RAW_KEY_LOOKING_ID, api_key_service=service)

        assert any(
            r.levelno == logging.INFO and "Deactivated API key" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_does_not_leak_raw_identifier(self, caplog):
        service = SimpleNamespace(deactivate_api_key_by_id=AsyncMock(return_value=True))
        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            await admin_routes.deactivate_api_key(RAW_KEY_LOOKING_ID, api_key_service=service)

        for record in caplog.records:
            assert RAW_KEY_LOOKING_ID not in record.message


class TestRenameApiKeyLogging:

    @pytest.mark.asyncio
    async def test_logs_at_info_level_and_masks_both_keys(self, caplog):
        new_key = "sk-live-brand-new-secret-value-0000"
        service = SimpleNamespace(rename_api_key_by_id=AsyncMock(return_value=True))
        request = make_request(api_key_service=service)

        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            result = await admin_routes.rename_api_key(
                RAW_KEY_LOOKING_ID, new_api_key=new_key, request=request
            )

        assert result["new_api_key_masked"] == "***0000"
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("Renamed API key" in r.message for r in info_records)
        for record in caplog.records:
            assert RAW_KEY_LOOKING_ID not in record.message
            assert new_key not in record.message


class TestUpdateApiKeyLogging:

    @pytest.mark.asyncio
    async def test_logs_at_info_level_and_masks_identifier(self, caplog):
        service = SimpleNamespace(update_api_key_metadata=AsyncMock(return_value=True))
        request = make_request(api_key_service=service, adapter_manager=None)
        data = SimpleNamespace(
            client_name="Test Client", adapter_name="simple-chat",
            system_prompt_id=None, notes=None,
        )

        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            await admin_routes.update_api_key(RAW_KEY_LOOKING_ID, data=data, request=request)

        assert any(
            r.levelno == logging.INFO and "Updated API key metadata" in r.message
            for r in caplog.records
        )
        for record in caplog.records:
            assert RAW_KEY_LOOKING_ID not in record.message


class TestGetApiKeyStatusLogging:

    @pytest.mark.asyncio
    async def test_does_not_leak_raw_identifier(self, caplog):
        service = SimpleNamespace(
            get_api_key_status_by_id=AsyncMock(return_value={"exists": True}),
            get_api_key_status=AsyncMock(return_value={"exists": True}),
        )
        request = make_request(api_key_service=service)

        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            await admin_routes.get_api_key_status(RAW_KEY_LOOKING_ID, request=request)

        for record in caplog.records:
            assert RAW_KEY_LOOKING_ID not in record.message


class TestCreateApiKeyLogging:

    @pytest.mark.asyncio
    async def test_created_key_is_masked_in_log(self, caplog):
        created_key = "sk-live-newly-generated-secret-1111"
        service = SimpleNamespace(
            create_api_key=AsyncMock(return_value={"api_key": created_key, "adapter_name": "simple-chat"})
        )
        request = make_request(api_key_service=service)
        api_key_data = SimpleNamespace(
            client_name="Test Client", notes=None, system_prompt_id=None, adapter_name="simple-chat"
        )

        with caplog.at_level(logging.DEBUG, logger="routes.admin_routes"):
            result = await admin_routes.create_api_key(api_key_data, request=request)

        assert result["api_key"] == created_key  # response payload still carries the real key
        for record in caplog.records:
            assert created_key not in record.message
        assert any(
            r.levelno == logging.INFO and "***1111" in r.message for r in caplog.records
        )
