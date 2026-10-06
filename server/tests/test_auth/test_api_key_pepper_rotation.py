"""
Test ORBIT_API_KEY_PEPPER rotation detection (Phase 5 of the admin/API-key
security hardening plan).

Covers:
- ApiKeyService.initialize() warns when the pepper's fingerprint differs from
  the one persisted on a prior run, and names how many active keys will fail
  to validate.
- No warning fires when the pepper is unchanged.
- The persisted fingerprint is never the raw pepper.
"""

import os
import shutil
import tempfile
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from services.api_key_service import ApiKeyService, _pepper_fingerprint, count_active_or_total_api_keys
from services.database_service import DatabaseOperationError
from services.sqlite_service import SQLiteService

TEMP_DIR = None


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    global TEMP_DIR
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def _make_config(db_path: str, pepper: str | None) -> dict:
    config = {
        'adapters': [],
        'api_keys': {'prefix': 'test_', 'allow_default': True},
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {'database_path': db_path},
            }
        },
        'mongodb': {'apikey_collection': 'api_keys'},
    }
    if pepper is not None:
        config['api_keys']['hash_pepper'] = pepper
    return config


@pytest_asyncio.fixture
async def db_path():
    path = os.path.join(TEMP_DIR, f"pepper_rotation_{os.getpid()}_{id(object())}.db")
    yield path


async def _make_service(db_path: str, pepper: str) -> ApiKeyService:
    # ORBIT_API_KEY_PEPPER (e.g. loaded from a developer .env by another test
    # module) takes precedence over config in _get_api_key_pepper() - clear it
    # so these tests control the pepper purely via config, deterministically.
    os.environ.pop("ORBIT_API_KEY_PEPPER", None)
    ApiKeyService.clear_cache()
    SQLiteService.clear_cache()
    config = _make_config(db_path, pepper)
    sqlite_service = SQLiteService(config)
    await sqlite_service.initialize()
    service = ApiKeyService(config, sqlite_service)
    await service.initialize()
    return service


@pytest.mark.asyncio
async def test_no_warning_on_first_run(db_path, caplog):
    """A brand-new database has no prior fingerprint to compare against."""
    await _make_service(db_path, "pepper-one")

    assert not any("ORBIT_API_KEY_PEPPER appears to have changed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_no_warning_when_pepper_unchanged(db_path, caplog):
    await _make_service(db_path, "pepper-one")
    caplog.clear()

    await _make_service(db_path, "pepper-one")

    assert not any("ORBIT_API_KEY_PEPPER appears to have changed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_warning_fires_and_names_active_key_count(db_path, caplog):
    service = await _make_service(db_path, "pepper-one")
    now = datetime.now(UTC)

    for name, hash_value, active in (
        ("client-a", "hash-a", True),
        ("client-b", "hash-b", True),
        ("client-c", "hash-c", False),
    ):
        await service.database.insert_one(
            service.collection_name,
            {
                "client_name": name,
                "active": active,
                "api_key_hash": hash_value,
                "created_at": now,
            },
        )

    caplog.clear()
    import logging
    caplog.set_level(logging.WARNING)

    await _make_service(db_path, "pepper-two")

    warnings = [r.message for r in caplog.records if "ORBIT_API_KEY_PEPPER appears to have changed" in r.message]
    assert len(warnings) == 1
    assert "2 active API key" in warnings[0]


@pytest.mark.asyncio
async def test_legacy_key_without_active_field_counts_as_active(db_path):
    """A key document with no `active` field at all (legacy/Mongo rows) is
    treated as active everywhere else in this module (see e.g.
    validate_api_key()'s "only check for explicit False" comment) - the count
    used for the pepper blast-radius figure must agree, not silently exclude
    it via a naive {"active": True} filter."""
    service = await _make_service(db_path, "pepper-one")
    now = datetime.now(UTC)

    await service.database.insert_one(
        service.collection_name,
        {"client_name": "legacy-client", "api_key_hash": "hash-legacy", "created_at": now},
    )
    await service.database.insert_one(
        service.collection_name,
        {"client_name": "explicitly-inactive", "active": False, "api_key_hash": "hash-inactive", "created_at": now},
    )

    count = await count_active_or_total_api_keys(service.database, service.collection_name, active_only=True)

    assert count == 1


@pytest.mark.asyncio
async def test_count_active_or_total_raises_on_database_error(db_path):
    """A database failure must surface as an exception, never a confident-
    looking "0 affected" - count() on every backend swallows its own errors
    to 0, which is why this goes through count_strict() instead."""
    service = await _make_service(db_path, "pepper-one")

    with (
        patch.object(service.database, "count_strict", AsyncMock(side_effect=DatabaseOperationError("boom"))),
        pytest.raises(DatabaseOperationError),
    ):
        await count_active_or_total_api_keys(service.database, service.collection_name, active_only=True)


@pytest.mark.asyncio
async def test_strict_count_rejects_missing_sql_result(db_path):
    service = await _make_service(db_path, "pepper-one")

    with (
        patch.object(service.database, "_execute_sql_fetchone", return_value=None),
        pytest.raises(DatabaseOperationError, match="COUNT query returned no row"),
    ):
        await service.database.count_strict(service.collection_name, {})


@pytest.mark.asyncio
async def test_warning_omits_fabricated_count_on_database_error(db_path, caplog):
    """When the fingerprint differs AND the count query fails, the warning
    must say the count is unknown rather than report a wrong number."""
    await _make_service(db_path, "pepper-one")

    caplog.clear()
    import logging
    caplog.set_level(logging.WARNING)

    with patch(
        "services.api_key_service.count_active_or_total_api_keys",
        AsyncMock(side_effect=DatabaseOperationError("boom")),
    ):
        await _make_service(db_path, "pepper-two")

    warnings = [r.message for r in caplog.records if "ORBIT_API_KEY_PEPPER appears to have changed" in r.message]
    assert len(warnings) == 1
    assert "could not determine exact count" in warnings[0]
    assert "active API key(s) will fail" not in warnings[0]


@pytest.mark.asyncio
async def test_persisted_fingerprint_never_stores_raw_pepper(db_path):
    service = await _make_service(db_path, "super-secret-pepper-value")

    doc_id = f"api_key_pepper_fingerprint:{service.collection_name}"
    stored = await service.database.find_one("system_state", {"_id": doc_id})

    assert stored is not None
    assert stored["value"] == _pepper_fingerprint("super-secret-pepper-value")
    assert "super-secret-pepper-value" not in stored["value"]
