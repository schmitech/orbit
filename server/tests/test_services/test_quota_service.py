"""
Unit tests for QuotaService.

Uses a real SqliteCacheProvider (no external service required) so the atomic
check_and_increment() path is exercised for real, not mocked away.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.quota_service import QuotaService
from services.cache_backends.sqlite_provider import SqliteCacheProvider

TEST_DB_PATH = "/tmp/test_quota_service_cache.db"


def _config(daily_limit=5, monthly_limit=50, enabled=True):
    return {
        "internal_services": {
            "sqlite_cache": {
                "enabled": True,
                "database_path": TEST_DB_PATH,
                "ttl": 3600,
            }
        },
        "security": {
            "throttling": {
                "enabled": enabled,
                "default_quotas": {
                    "daily_limit": daily_limit,
                    "monthly_limit": monthly_limit,
                },
            }
        },
    }


@pytest.fixture
async def cache_service():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    SqliteCacheProvider.clear_cache()
    svc = SqliteCacheProvider(_config())
    await svc.initialize()
    yield svc
    await svc.close()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture
async def quota_service(cache_service):
    QuotaService.clear_cache()
    service = QuotaService(_config(), database_service=None, cache_service=cache_service)
    await service.initialize()
    yield service


class TestIncrementUsage:
    """increment_usage() - soft usage tracking with no limit enforcement."""

    async def test_counts_up_across_calls(self, quota_service):
        daily, monthly, _, _ = await quota_service.increment_usage("key-1")
        assert (daily, monthly) == (1, 1)

        daily, monthly, _, _ = await quota_service.increment_usage("key-1")
        assert (daily, monthly) == (2, 2)

    async def test_tracks_different_keys_independently(self, quota_service):
        await quota_service.increment_usage("key-a")
        await quota_service.increment_usage("key-a")

        daily, monthly, _, _ = await quota_service.increment_usage("key-b")
        assert (daily, monthly) == (1, 1)

    async def test_disabled_service_returns_zeros(self):
        QuotaService.clear_cache()
        service = QuotaService(_config(enabled=False), database_service=None, cache_service=None)
        await service.initialize()

        result = await service.increment_usage("key-x")
        assert result == (0, 0, 86400, 2592000)


class TestCheckAndIncrementUsage:
    """check_and_increment_usage() - hard-limit enforcement."""

    async def test_allows_requests_under_limit(self, quota_service):
        for i in range(1, 6):
            daily, _, _, _, exceeded = await quota_service.check_and_increment_usage(
                "key-limit", daily_limit=5, monthly_limit=50
            )
            assert exceeded is None
            assert daily == i

    async def test_rejects_request_over_daily_limit(self, quota_service):
        for _ in range(5):
            await quota_service.check_and_increment_usage("key-daily", daily_limit=5, monthly_limit=50)

        daily, monthly, _, _, exceeded = await quota_service.check_and_increment_usage(
            "key-daily", daily_limit=5, monthly_limit=50
        )
        assert exceeded == "daily"
        assert daily == 5  # unchanged - the rejected request must not increment
        assert monthly == 5  # regression guard for the fail-open bug (see below)

    async def test_rejects_request_over_monthly_limit(self, quota_service):
        for _ in range(3):
            await quota_service.check_and_increment_usage("key-monthly", daily_limit=None, monthly_limit=3)

        daily, monthly, _, _, exceeded = await quota_service.check_and_increment_usage(
            "key-monthly", daily_limit=None, monthly_limit=3
        )
        assert exceeded == "monthly"
        assert monthly == 3

    async def test_rejected_request_does_not_increment_the_other_counter(self, quota_service):
        for _ in range(5):
            await quota_service.check_and_increment_usage("key-safe", daily_limit=5, monthly_limit=500)

        await quota_service.check_and_increment_usage("key-safe", daily_limit=5, monthly_limit=500)

        usage = await quota_service.get_usage("key-safe")
        assert usage["monthly_used"] == 5  # not bumped to 6 by the rejected 6th request

    async def test_unlimited_when_limit_is_none(self, quota_service):
        for _ in range(20):
            _, _, _, _, exceeded = await quota_service.check_and_increment_usage(
                "key-unlimited", daily_limit=None, monthly_limit=None
            )
            assert exceeded is None

    async def test_disabled_service_returns_empty_result(self):
        QuotaService.clear_cache()
        service = QuotaService(_config(enabled=False), database_service=None, cache_service=None)
        await service.initialize()

        result = await service.check_and_increment_usage("key-x", daily_limit=5, monthly_limit=50)
        assert result == (0, 0, 86400, 2592000, None)


class TestRegressionFixes:
    """Regression coverage for review findings fixed in this session.

    P1: check_and_increment() used to omit counters after the one that
    triggered rejection, which made quota_service KeyError, hit its
    catch-all, and silently allow the request (fail open). P2: the
    check used current >= limit instead of current + amount > limit,
    letting amount > 1 overshoot a limit. Quota only ever uses amount=1,
    so P2 is covered at the cache_backends layer, not here.
    """

    async def test_daily_rejection_does_not_fail_open(self, quota_service):
        api_key = "regression-p1"
        for _ in range(5):
            _, _, _, _, exceeded = await quota_service.check_and_increment_usage(
                api_key, daily_limit=5, monthly_limit=500
            )
            assert exceeded is None

        daily, monthly, _, _, exceeded = await quota_service.check_and_increment_usage(
            api_key, daily_limit=5, monthly_limit=500
        )
        assert exceeded == "daily", "the 6th request must be rejected, not silently allowed"
        assert daily == 5
        assert monthly == 5


class TestGetUsageAndReset:
    async def test_get_usage_reflects_increments(self, quota_service):
        await quota_service.increment_usage("key-usage")
        await quota_service.increment_usage("key-usage")

        usage = await quota_service.get_usage("key-usage")
        assert usage["daily_used"] == 2
        assert usage["monthly_used"] == 2
        assert usage["last_request_at"] is not None

    async def test_get_usage_for_unknown_key_is_zero(self, quota_service):
        usage = await quota_service.get_usage("never-seen-key")
        assert usage["daily_used"] == 0
        assert usage["monthly_used"] == 0
        assert usage["last_request_at"] is None

    async def test_reset_usage_daily_only_leaves_monthly_untouched(self, quota_service):
        await quota_service.increment_usage("key-reset")
        await quota_service.increment_usage("key-reset")

        await quota_service.reset_usage("key-reset", period="daily")

        usage = await quota_service.get_usage("key-reset")
        assert usage["daily_used"] == 0
        assert usage["monthly_used"] == 2

    async def test_reset_usage_all_clears_everything(self, quota_service):
        await quota_service.increment_usage("key-reset-all")

        await quota_service.reset_usage("key-reset-all", period="all")

        usage = await quota_service.get_usage("key-reset-all")
        assert usage["daily_used"] == 0
        assert usage["monthly_used"] == 0
        assert usage["last_request_at"] is None


class TestQuotaConfig:
    async def test_get_quota_config_returns_defaults_without_database(self, quota_service):
        config = await quota_service.get_quota_config("any-key")
        assert config["daily_limit"] == 5
        assert config["monthly_limit"] == 50
        assert config["throttle_enabled"] is True

    async def test_get_quota_config_overridden_by_database(self, cache_service):
        QuotaService.clear_cache()
        mock_db = AsyncMock()
        mock_db.find_one = AsyncMock(return_value={
            "quota_daily_limit": 100,
            "quota_monthly_limit": 1000,
        })
        service = QuotaService(_config(), database_service=mock_db, cache_service=cache_service)
        await service.initialize()

        config = await service.get_quota_config("key-with-override")
        assert config["daily_limit"] == 100
        assert config["monthly_limit"] == 1000

    def test_calculate_remaining_with_limits(self, quota_service):
        remaining = quota_service.calculate_remaining(
            {"daily_limit": 10, "monthly_limit": 100},
            {"daily_used": 3, "monthly_used": 20},
        )
        assert remaining == (7, 80)

    def test_calculate_remaining_unlimited(self, quota_service):
        remaining = quota_service.calculate_remaining(
            {"daily_limit": None, "monthly_limit": None},
            {"daily_used": 3, "monthly_used": 20},
        )
        assert remaining == (None, None)
