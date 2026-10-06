"""
Unit tests for GET /admin/api-keys/count (Phase 5 of the admin/API-key
security hardening plan).

Calls the route coroutine directly with a stubbed `app.state`, rather than
spinning up a live server like test_admin_integration.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from routes.admin.api_keys import count_api_keys


def _make_request(api_key_service):
    app = SimpleNamespace(state=SimpleNamespace(api_key_service=api_key_service))
    return SimpleNamespace(app=app)


def _make_api_key_service(active_total: int, inactive_total: int):
    service = SimpleNamespace()
    service._initialized = True
    service.collection_name = "api_keys"
    service.database = SimpleNamespace()

    async def _count_strict(collection_name, query):
        if query == {}:
            return active_total + inactive_total
        if query == {"active": False}:
            return inactive_total
        raise AssertionError(f"unexpected query: {query}")

    service.database.count_strict = AsyncMock(side_effect=_count_strict)
    return service


@pytest.mark.asyncio
async def test_count_active_only_excludes_explicitly_inactive():
    service = _make_api_key_service(active_total=3, inactive_total=2)
    request = _make_request(service)

    result = await count_api_keys(request, active_only=True)

    assert result == {"count": 3, "active_only": True}


@pytest.mark.asyncio
async def test_count_total_includes_everything():
    service = _make_api_key_service(active_total=3, inactive_total=2)
    request = _make_request(service)

    result = await count_api_keys(request, active_only=False)

    assert result == {"count": 5, "active_only": False}


@pytest.mark.asyncio
async def test_database_error_returns_503_not_a_fabricated_zero():
    service = _make_api_key_service(active_total=0, inactive_total=0)
    from services.database_service import DatabaseOperationError
    service.database.count_strict = AsyncMock(side_effect=DatabaseOperationError("boom"))
    request = _make_request(service)

    with pytest.raises(HTTPException) as exc_info:
        await count_api_keys(request, active_only=True)

    assert exc_info.value.status_code == 503
