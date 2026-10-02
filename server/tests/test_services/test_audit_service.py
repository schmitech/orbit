"""
Unit Tests for Audit Service
=============================

Tests for the AuditService, AuditStorageStrategy implementations,
and strategy selection logic.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from pytest_asyncio import fixture

# Add parent directories to path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.audit import (
    AuditService,
    AuditRecord,
    MongoDBDAuditStrategy,
)
from services.sqlite_service import SQLiteService


# ============================================================================
# Fixtures
# ============================================================================

@fixture(scope="function")
async def sqlite_config(tmp_path):
    """Create SQLite configuration for testing."""
    db_path = os.path.join(tmp_path, "test_audit.db")
    return {
        'general': {
            'inference_provider': 'test_provider'
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {'database_path': db_path}
            },
            'audit': {
                'enabled': True,
                'storage_backend': 'sqlite',
                'collection_name': 'audit_logs'
            }
        }
    }


@fixture(scope="function")
async def mongodb_config():
    """Create MongoDB configuration for testing."""
    return {
        'general': {
            'inference_provider': 'test_provider'
        },
        'internal_services': {
            'backend': {
                'type': 'mongodb',
                'mongodb': {
                    'host': 'localhost',
                    'port': 27017,
                    'database': 'test_db'
                }
            },
            'audit': {
                'enabled': True,
                'storage_backend': 'mongodb',
                'collection_name': 'audit_logs'
            }
        }
    }


@fixture(scope="function")
async def database_config(tmp_path):
    """Create configuration using 'database' as storage backend."""
    db_path = os.path.join(tmp_path, "test_audit_database.db")
    return {
        'general': {
            'inference_provider': 'test_provider'
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {'database_path': db_path}
            },
            'audit': {
                'enabled': True,
                'storage_backend': 'database',
                'collection_name': 'audit_logs'
            }
        }
    }


@fixture(scope="function")
async def sqlite_service_with_audit(sqlite_config):
    """Create SQLite service and audit service for testing."""
    # Initialize SQLite service
    sqlite_service = SQLiteService(sqlite_config)
    await sqlite_service.initialize()

    # Initialize Audit service
    audit_service = AuditService(sqlite_config, sqlite_service)
    await audit_service.initialize()

    yield {
        'audit': audit_service,
        'db': sqlite_service,
        'config': sqlite_config
    }

    # Cleanup
    await audit_service.close()
    sqlite_service.close()
    SQLiteService.clear_cache()


@fixture
def sample_audit_record():
    """Create a sample audit record for testing."""
    return AuditRecord(
        timestamp=datetime.now(),
        query="What is the capital of France?",
        response="The capital of France is Paris.",
        provider="test_provider",
        blocked=False,
        ip="192.168.1.100",
        ip_metadata={
            "type": "ipv4",
            "isLocal": True,
            "source": "direct",
            "originalValue": "192.168.1.100"
        },
        api_key={
            "key": "test_api_key_123",
            "timestamp": datetime.now().isoformat()
        },
        session_id="session_abc123",
        user_id="user_xyz789",
        adapter_name="intent-sql-sqlite-hr"
    )


# ============================================================================
# AuditRecord Tests
# ============================================================================

class TestAuditRecord:
    """Tests for AuditRecord dataclass."""

    def test_audit_record_creation(self):
        """Test creating an AuditRecord."""
        record = AuditRecord(
            timestamp=datetime.now(),
            query="Test query",
            response="Test response",
            provider="test",
            blocked=False,
            ip="127.0.0.1"
        )
        assert record.query == "Test query"
        assert record.response == "Test response"
        assert record.blocked is False

    def test_audit_record_to_dict(self, sample_audit_record):
        """Test converting AuditRecord to dictionary."""
        result = sample_audit_record.to_dict()

        assert 'timestamp' in result
        assert result['query'] == "What is the capital of France?"
        assert result['response'] == "The capital of France is Paris."
        assert result['provider'] == "test_provider"
        assert result['blocked'] is False
        assert 'ip_metadata' in result
        assert 'api_key' in result
        assert result['session_id'] == "session_abc123"
        assert result['adapter_name'] == "intent-sql-sqlite-hr"

    def test_audit_record_to_flat_dict(self, sample_audit_record):
        """Test converting AuditRecord to flat dictionary for SQLite."""
        result = sample_audit_record.to_flat_dict()

        assert 'timestamp' in result
        assert result['query'] == "What is the capital of France?"
        assert result['blocked'] == 0  # SQLite integer for boolean
        assert result['ip_type'] == "ipv4"
        assert result['ip_is_local'] == 1  # SQLite integer for boolean
        assert result['ip_source'] == "direct"
        assert result['api_key_value'] == "test_api_key_123"
        assert result['session_id'] == "session_abc123"
        assert result['adapter_name'] == "intent-sql-sqlite-hr"


# ============================================================================
# Strategy Selection Tests
# ============================================================================

class TestStrategySelection:
    """Tests for audit storage strategy selection."""

    @pytest.mark.asyncio
    async def test_strategy_selection_sqlite(self, sqlite_config):
        """Test SQLite backend selection."""
        service = AuditService(sqlite_config)
        backend = service._resolve_storage_backend()
        assert backend == 'sqlite'

    @pytest.mark.asyncio
    async def test_strategy_selection_mongodb(self, mongodb_config):
        """Test MongoDB backend selection."""
        service = AuditService(mongodb_config)
        backend = service._resolve_storage_backend()
        assert backend == 'mongodb'

    @pytest.mark.asyncio
    async def test_strategy_selection_database_follows_backend(self, database_config):
        """Test 'database' option uses configured backend type."""
        service = AuditService(database_config)
        backend = service._resolve_storage_backend()
        # Should resolve to 'sqlite' since that's the backend.type
        assert backend == 'sqlite'

    @pytest.mark.asyncio
    async def test_strategy_selection_elasticsearch(self):
        """Test Elasticsearch backend selection."""
        config = {
            'internal_services': {
                'audit': {
                    'enabled': True,
                    'storage_backend': 'elasticsearch'
                },
                'elasticsearch': {
                    'enabled': True,
                    'node': 'http://localhost:9200',
                    'index': 'test_audit'
                }
            }
        }
        service = AuditService(config)
        backend = service._resolve_storage_backend()
        assert backend == 'elasticsearch'


# ============================================================================
# SQLite Strategy Tests
# ============================================================================

class TestSQLiteAuditStrategy:
    """Tests for SQLite audit storage strategy."""

    @pytest.mark.asyncio
    async def test_sqlite_store_audit_record(self, sqlite_service_with_audit, sample_audit_record):
        """Test storing an audit record in SQLite."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        result = await strategy.store(sample_audit_record)
        assert result is True

    @pytest.mark.asyncio
    async def test_sqlite_query_by_session_id(self, sqlite_service_with_audit, sample_audit_record):
        """Test querying audit logs by session ID."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        # Store record
        await strategy.store(sample_audit_record)

        # Query by session_id
        results = await strategy.query({'session_id': 'session_abc123'})

        assert len(results) == 1
        assert results[0]['session_id'] == 'session_abc123'
        assert results[0]['query'] == "What is the capital of France?"

    @pytest.mark.asyncio
    async def test_sqlite_query_blocked_requests(self, sqlite_service_with_audit):
        """Test querying blocked audit logs."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        # Store normal record
        normal_record = AuditRecord(
            timestamp=datetime.now(),
            query="Normal query",
            response="Normal response",
            provider="test",
            blocked=False,
            ip="127.0.0.1"
        )
        await strategy.store(normal_record)

        # Store blocked record
        blocked_record = AuditRecord(
            timestamp=datetime.now(),
            query="Blocked query",
            response="I cannot assist with that request",
            provider="test",
            blocked=True,
            ip="127.0.0.1"
        )
        await strategy.store(blocked_record)

        # Query blocked records
        results = await strategy.query({'blocked': True})

        assert len(results) == 1
        assert results[0]['blocked'] is True
        assert results[0]['query'] == "Blocked query"

    @pytest.mark.asyncio
    async def test_sqlite_unflatten_record(self, sqlite_service_with_audit, sample_audit_record):
        """Test that stored records are unflattened correctly on query."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        # Store record
        await strategy.store(sample_audit_record)

        # Query and check nested structure is restored
        results = await strategy.query({'session_id': 'session_abc123'})

        assert len(results) == 1
        record = results[0]

        # Check nested ip_metadata is restored
        assert 'ip_metadata' in record
        assert record['ip_metadata']['type'] == 'ipv4'
        assert record['ip_metadata']['isLocal'] is True

        # Check nested api_key is restored
        assert 'api_key' in record
        assert record['api_key']['key'] == 'test_api_key_123'

    @pytest.mark.asyncio
    async def test_search_treats_term_as_literal_substring(self, sqlite_service_with_audit):
        """A search term containing SQL LIKE wildcards (%, _) or regex-only
        metacharacters must match literally, not as a pattern — otherwise
        "100%" would match any model name starting with "100", and "a_b"
        would match "aXb"."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="q1", response="r1",
            provider="test", blocked=False, ip="127.0.0.1", model="100% match",
        ))
        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="q2", response="r2",
            provider="test", blocked=False, ip="127.0.0.1", model="100x match",
        ))

        results = await strategy.query({}, search="100%")
        assert {r['model'] for r in results} == {"100% match"}

    @pytest.mark.asyncio
    async def test_search_uses_fts5_index_not_a_full_table_scan(self, sqlite_service_with_audit):
        """Phase 4 P1 fix: a `search` long enough for the trigram tokenizer
        must resolve via the FTS5 index (SCAN ... VIRTUAL TABLE), not an
        unindexed LIKE scan of the whole audit_logs table."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        assert strategy._fts_available is True

        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="unique refund question", response="r1",
            provider="test", blocked=False, ip="127.0.0.1",
        ))

        fts_results = await strategy._fts_search({}, "refund", limit=100, offset=0, sort_by="timestamp", sort_order=-1)
        assert fts_results

        connection = strategy._database_service.connection
        cursor = connection.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN SELECT t.* FROM audit_logs_fts JOIN audit_logs t "
            'ON t.rowid = audit_logs_fts.rowid WHERE audit_logs_fts MATCH ? '
            'ORDER BY t."timestamp" DESC LIMIT ? OFFSET ?',
            ('"refund"', 100, 0),
        )
        plan = " ".join(row[-1] for row in cursor.fetchall())
        assert "VIRTUAL TABLE" in plan
        assert "SCAN audit_logs USING" not in plan

    @pytest.mark.asyncio
    async def test_fts_search_applies_sort_filters_and_pagination_correctly(self, sqlite_service_with_audit):
        """Regression test: _fts_search() must apply the caller's filters,
        sort order, and pagination within the single joined query (not via a
        separate id-resolution step with its own LIMIT, which truncates the
        candidate set before those are applied — see _fts_search's
        docstring)."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        assert strategy._fts_available is True

        # Three matches, stored oldest-first, with a non-search filter field
        # (adapter_name) that only the newest two share.
        await strategy.store(AuditRecord(
            timestamp=datetime(2026, 1, 1), query="refund oldest", response="r",
            provider="test", blocked=False, ip="127.0.0.1", adapter_name="other",
        ))
        await strategy.store(AuditRecord(
            timestamp=datetime(2026, 1, 2), query="refund middle", response="r",
            provider="test", blocked=False, ip="127.0.0.1", adapter_name="support",
        ))
        await strategy.store(AuditRecord(
            timestamp=datetime(2026, 1, 3), query="refund newest", response="r",
            provider="test", blocked=False, ip="127.0.0.1", adapter_name="support",
        ))

        # Newest-first ordering with limit=1 must return the newest match,
        # not whatever the FTS engine happened to list first internally.
        page1 = await strategy.query({}, limit=1, offset=0, search="refund")
        assert len(page1) == 1
        assert page1[0]["query"] == "refund newest"

        # Pagination: offset=1 must return the next-newest, not come back
        # empty just because the id-resolution step only looked at 1 row.
        page2 = await strategy.query({}, limit=1, offset=1, search="refund")
        assert len(page2) == 1
        assert page2[0]["query"] == "refund middle"

        # Combining search with another equality filter must still be an
        # AND over the full candidate set, not just whatever the (now
        # correctly unbounded-by-page-size) candidate ids already excluded.
        filtered = await strategy.query({"adapter_name": "support"}, search="refund")
        assert {r["query"] for r in filtered} == {"refund middle", "refund newest"}

    @pytest.mark.asyncio
    async def test_fts_search_pagination_is_exhaustive_with_no_candidate_cap(self, sqlite_service_with_audit):
        """There is no intermediate id-resolution step with its own LIMIT
        left to reproduce the reported bug at a larger scale — paging
        through every match in fixed-size pages must visit each one exactly
        once, regardless of how many matches exist."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        assert strategy._fts_available is True

        total = 15
        for i in range(total):
            await strategy.store(AuditRecord(
                timestamp=datetime(2026, 1, 1 + i), query=f"refund case {i}", response="r",
                provider="test", blocked=False, ip="127.0.0.1",
            ))

        page_size = 4
        seen = []
        for offset in range(0, total + page_size, page_size):
            page = await strategy.query({}, limit=page_size, offset=offset, search="refund")
            seen.extend(r["query"] for r in page)
        assert len(seen) == total
        assert len(set(seen)) == total  # no duplicates across page boundaries
        assert seen == sorted(seen, key=lambda q: int(q.split()[-1]), reverse=True)

    @pytest.mark.asyncio
    async def test_contains_fallback_uses_timestamp_index_not_a_full_scan(self, sqlite_service_with_audit):
        """The unindexed-substring fallback must still bound its own cost: its
        inner "most recent N rows" subquery should use idx_audit_logs_timestamp
        (an index-ordered scan that stops at the cap), not a full table scan."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        strategy._fts_available = False  # force the fallback path

        connection = strategy._database_service.connection
        cursor = connection.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN "
            "SELECT * FROM (SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?) recent "
            "WHERE recent.response LIKE ? ESCAPE '\\' LIMIT ? OFFSET ?",
            (strategy._FALLBACK_SCAN_CAP, "%refund%", 50, 0),
        )
        plan = " ".join(row[-1] for row in cursor.fetchall())
        assert "idx_audit_logs_timestamp" in plan

    @pytest.mark.asyncio
    async def test_contains_fallback_scan_is_bounded_by_cap(self, sqlite_service_with_audit):
        """A match older than _FALLBACK_SCAN_CAP rows must not be found via
        the fallback path — this is the explicit, accepted trade-off that
        bounds its cost; a smaller cap is used here to make the boundary
        reachable in a test without storing tens of thousands of rows."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        strategy._fts_available = False
        strategy._FALLBACK_SCAN_CAP = 5

        # One old row with the needle, then more than the cap worth of newer
        # rows without it, so the needle falls outside the bounded window.
        await strategy.store(AuditRecord(
            timestamp=datetime(2020, 1, 1), query="the needle refund phrase", response="r",
            provider="test", blocked=False, ip="127.0.0.1",
        ))
        for i in range(10):
            await strategy.store(AuditRecord(
                timestamp=datetime(2026, 1, 1 + i), query=f"unrelated {i}", response="r",
                provider="test", blocked=False, ip="127.0.0.1",
            ))

        results = await strategy.query({}, search="refund")
        assert results == []

        # Raising the cap back above the dataset size finds it again,
        # confirming the miss above was the cap, not a logic bug.
        strategy._FALLBACK_SCAN_CAP = 1000
        results = await strategy.query({}, search="refund")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_short_search_term_falls_back_without_fts(self, sqlite_service_with_audit):
        """Trigram FTS can't match terms under 3 characters — query() must
        still find them via the $contains fallback instead of silently
        returning nothing."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="test", blocked=False, ip="127.0.0.1", model="ab-model",
        ))

        assert await strategy._fts_search({}, "ab", limit=100, offset=0, sort_by="timestamp", sort_order=-1) is None
        results = await strategy.query({}, search="ab")
        assert any(r['model'] == "ab-model" for r in results)

    @pytest.mark.asyncio
    async def test_search_still_correct_when_fts_unavailable(self, sqlite_service_with_audit):
        """When FTS5/the trigram tokenizer isn't available (e.g. an older
        SQLite build), query() must fall back to $contains and still return
        correct results — just without the index. This does not bound the
        scan cost (the $contains path is an ordinary LIKE), only correctness;
        see docs/roadmap/admin-api-security-hardening.md Phase 4 for the
        explicit, documented trade-off."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy
        strategy._fts_available = False  # simulate an environment without FTS5 trigram support

        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="unique refund question", response="r",
            provider="test", blocked=False, ip="127.0.0.1",
        ))
        await strategy.store(AuditRecord(
            timestamp=datetime.now(), query="unrelated", response="r",
            provider="test", blocked=False, ip="127.0.0.1",
        ))

        assert await strategy._fts_search({}, "refund", limit=100, offset=0, sort_by="timestamp", sort_order=-1) is None
        results = await strategy.query({}, search="refund")
        assert len(results) == 1
        assert results[0]['query'] == "unique refund question"

    @pytest.mark.asyncio
    async def test_fts_setup_failure_is_non_fatal_and_falls_back(self):
        """If FTS5 virtual-table creation raises sqlite3.OperationalError
        (e.g. the SQLite build lacks FTS5, or lacks the trigram tokenizer
        specifically), _ensure_fts_index() must not propagate — it should log
        a warning and leave _fts_available False, so initialize() still
        succeeds and $contains carries search instead."""
        import sqlite3
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import MagicMock
        from services.audit.sqlite_audit_strategy import SQLiteAuditStrategy

        config = {'internal_services': {'audit': {'collection_name': 'audit_logs'}}}
        strategy = SQLiteAuditStrategy(config)

        mock_cursor = MagicMock()

        def fake_execute(sql, *params):
            if "sqlite_master WHERE type='table'" in sql:
                mock_cursor.fetchone.return_value = ("audit_logs",)
            elif "sqlite_master WHERE name=" in sql:
                mock_cursor.fetchone.return_value = None  # FTS shadow table not yet created
            elif "CREATE VIRTUAL TABLE" in sql:
                raise sqlite3.OperationalError("no such module: fts5")

        mock_cursor.execute.side_effect = fake_execute
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cursor

        mock_db_service = MagicMock()
        mock_db_service.connection = mock_connection
        mock_db_service.executor = ThreadPoolExecutor(max_workers=1)
        mock_db_service._db_lock = None
        strategy._database_service = mock_db_service

        await strategy._ensure_fts_index()

        assert strategy._fts_available is False
        mock_connection.rollback.assert_called_once()
        mock_db_service.executor.shutdown(wait=True)


# ============================================================================
# AuditService Facade Tests
# ============================================================================

class TestAuditService:
    """Tests for AuditService facade."""

    @pytest.mark.asyncio
    async def test_log_conversation_signature_compatibility(self, sqlite_service_with_audit):
        """Test that log_conversation matches LoggerService signature."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Call with same signature as LoggerService
        await audit.log_conversation(
            query="Test query",
            response="Test response",
            ip="192.168.1.1",
            provider="ollama",
            blocked=False,
            api_key="test_key",
            session_id="session_123",
            user_id="user_456"
        )

        # Verify record was stored
        results = await audit.query_audit_logs({'session_id': 'session_123'})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_log_conversation_with_adapter_name(self, sqlite_service_with_audit):
        """Test that adapter_name is stored and retrievable."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Call with adapter_name
        await audit.log_conversation(
            query="Test query with adapter",
            response="Test response",
            ip="192.168.1.1",
            provider="ollama",
            api_key="test_key",
            session_id="session_adapter_test",
            adapter_name="intent-mongodb-mflix"
        )

        # Verify record was stored with adapter_name
        results = await audit.query_audit_logs({'session_id': 'session_adapter_test'})
        assert len(results) == 1
        assert results[0]['adapter_name'] == "intent-mongodb-mflix"

    @pytest.mark.asyncio
    async def test_api_key_is_masked_in_audit_logs(self, sqlite_service_with_audit):
        """Test that API keys are masked when stored in audit logs."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Use a realistic API key
        full_api_key = "api_abc123def456ghi789jkl012mno345"

        await audit.log_conversation(
            query="Test query",
            response="Test response",
            api_key=full_api_key,
            session_id="session_mask_test"
        )

        # Verify API key is masked (should show last 6 chars only)
        results = await audit.query_audit_logs({'session_id': 'session_mask_test'})
        assert len(results) == 1

        stored_api_key = results[0]['api_key']['key']
        # Should be masked, not the full key
        assert stored_api_key != full_api_key
        # Should be in format "...{last_6_chars}"
        assert stored_api_key == "...mno345"

    @pytest.mark.asyncio
    async def test_api_key_id_resolved_and_stored_when_api_key_service_wired(self, sqlite_config):
        """When AuditService is given an api_key_service, log_conversation
        must look up the raw key's document id and store it alongside the
        masked value — the Phase 4 stable identifier."""
        sqlite_service = SQLiteService(sqlite_config)
        await sqlite_service.initialize()

        full_api_key = "api_abc123def456ghi789jkl012mno345"
        inserted_id = await sqlite_service.insert_one('api_keys', {
            'api_key': full_api_key, 'client_name': 'Acme Corp', 'active': True,
            'created_at': datetime(2026, 1, 1).isoformat(),
        })

        class _FakeApiKeyService:
            def __init__(self, database):
                self.database = database
                self.collection_name = 'api_keys'
                self.config = {}

            async def _find_by_raw_key(self, api_key):
                return await self.database.find_one(self.collection_name, {'api_key': api_key})

        audit_service = AuditService(sqlite_config, sqlite_service, _FakeApiKeyService(sqlite_service))
        await audit_service.initialize()

        await audit_service.log_conversation(
            query="Test query", response="Test response",
            api_key=full_api_key, session_id="session_id_resolve_test",
        )

        results = await audit_service.query_audit_logs({'session_id': 'session_id_resolve_test'})
        assert len(results) == 1
        assert results[0]['api_key']['key'] == "...mno345"
        assert results[0]['api_key']['id'] == str(inserted_id)

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_api_key_id_absent_when_key_not_found(self, sqlite_config):
        """A raw key that doesn't match any api_keys document (e.g. it was
        deleted after the request was authorized) must not block logging —
        the record just falls back to masked-only, as if no lookup ran."""
        sqlite_service = SQLiteService(sqlite_config)
        await sqlite_service.initialize()

        class _FakeApiKeyService:
            def __init__(self, database):
                self.database = database
                self.collection_name = 'api_keys'
                self.config = {}

            async def _find_by_raw_key(self, api_key):
                return await self.database.find_one(self.collection_name, {'api_key': api_key})

        audit_service = AuditService(sqlite_config, sqlite_service, _FakeApiKeyService(sqlite_service))
        await audit_service.initialize()

        await audit_service.log_conversation(
            query="Test query", response="Test response",
            api_key="api_never_registered_key_000000", session_id="session_no_match_test",
        )

        results = await audit_service.query_audit_logs({'session_id': 'session_no_match_test'})
        assert len(results) == 1
        assert 'id' not in results[0]['api_key']

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_disabled_audit_service(self, tmp_path):
        """Test that disabled audit service doesn't store records."""
        config = {
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': str(tmp_path / 'disabled.db')}
                },
                'audit': {
                    'enabled': False,
                    'storage_backend': 'sqlite'
                }
            }
        }

        service = AuditService(config)
        await service.initialize()

        assert service.is_enabled is False

        # Should not raise, just return early
        await service.log_conversation(
            query="Test",
            response="Response"
        )

        await service.close()

    @pytest.mark.asyncio
    async def test_ip_format_detection(self, sqlite_service_with_audit):
        """Test IP address format detection."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Test IPv4
        metadata = audit._format_ip_address("192.168.1.1")
        assert metadata['type'] == 'ipv4'
        assert metadata['isLocal'] is True

        # Test localhost
        metadata = audit._format_ip_address("127.0.0.1")
        assert metadata['type'] == 'local'
        assert metadata['isLocal'] is True

        # Test IPv6 localhost
        metadata = audit._format_ip_address("::1")
        assert metadata['type'] == 'local'
        assert metadata['isLocal'] is True

        # Test public IP
        metadata = audit._format_ip_address("8.8.8.8")
        assert metadata['type'] == 'ipv4'
        assert metadata['isLocal'] is False

    @pytest.mark.asyncio
    async def test_blocked_response_detection(self, sqlite_service_with_audit):
        """Test blocked response auto-detection."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Test explicit blocked flag
        assert audit._detect_blocked_response("any response", blocked=True) is True

        # Test blocked phrase detection
        assert audit._detect_blocked_response(
            "I cannot assist with that request",
            blocked=False
        ) is True

        # Test normal response
        assert audit._detect_blocked_response(
            "Here's the information you requested.",
            blocked=False
        ) is False

    @pytest.mark.asyncio
    async def test_query_audit_logs(self, sqlite_service_with_audit):
        """Test querying audit logs through the facade."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Store multiple records
        for i in range(5):
            await audit.log_conversation(
                query=f"Query {i}",
                response=f"Response {i}",
                session_id=f"session_{i % 2}",  # Two different sessions
                provider="test"
            )

        # Query all
        results = await audit.query_audit_logs(limit=10)
        assert len(results) == 5

        # Query by session
        results = await audit.query_audit_logs({'session_id': 'session_0'})
        assert len(results) == 3  # Indices 0, 2, 4

    @pytest.mark.asyncio
    async def test_query_with_pagination(self, sqlite_service_with_audit):
        """Test pagination in query."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Store 10 records
        for i in range(10):
            await audit.log_conversation(
                query=f"Query {i}",
                response=f"Response {i}",
                session_id="session_test"
            )

        # Query with limit
        results = await audit.query_audit_logs(limit=5)
        assert len(results) == 5

        # Query with offset
        results = await audit.query_audit_logs(limit=5, offset=5)
        assert len(results) == 5


# ============================================================================
# MongoDB Strategy Tests (Mocked)
# ============================================================================

class TestMongoDBDAuditStrategy:
    """Tests for MongoDB audit storage strategy (mocked)."""

    @pytest.mark.asyncio
    async def test_mongodb_store_audit_record(self, sample_audit_record):
        """Test storing an audit record in MongoDB (mocked)."""
        # Create mock database service
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.insert_one = AsyncMock(return_value="mock_id_123")
        mock_db.create_index = AsyncMock()

        config = {
            'internal_services': {
                'audit': {
                    'collection_name': 'audit_logs'
                }
            }
        }

        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        result = await strategy.store(sample_audit_record)

        assert result is True
        mock_db.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_mongodb_index_creation(self):
        """Test that required indexes are created."""
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()

        config = {
            'internal_services': {
                'audit': {
                    'collection_name': 'audit_logs'
                }
            }
        }

        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        # Verify indexes were created (timestamp, session_id, user_id, blocked, provider, adapter_name, compound)
        assert mock_db.create_index.call_count >= 6

    @pytest.mark.asyncio
    async def test_mongodb_query(self, sample_audit_record):
        """Test querying audit records from MongoDB (mocked)."""
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.find_many = AsyncMock(return_value=[
            {'_id': '1', 'query': 'Test', 'session_id': 'session_123'}
        ])

        config = {
            'internal_services': {
                'audit': {
                    'collection_name': 'audit_logs'
                }
            }
        }

        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        results = await strategy.query({'session_id': 'session_123'})

        assert len(results) == 1
        mock_db.find_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_mongodb_query_keeps_plain_text_query_when_response_is_compressed(self):
        """MongoDB query path should only decompress the response field."""
        from services.audit import compress_text

        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.find_many = AsyncMock(return_value=[
            {
                '_id': '1',
                'query': 'Plain text query',
                'response': compress_text('Compressed response body'),
                'response_compressed': True,
                'session_id': 'session_123',
            }
        ])

        config = {
            'internal_services': {
                'audit': {
                    'collection_name': 'audit_logs'
                }
            }
        }

        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        results = await strategy.query({'session_id': 'session_123'})

        assert len(results) == 1
        assert results[0]['query'] == 'Plain text query'
        assert results[0]['response'] == 'Compressed response body'

    @pytest.mark.asyncio
    async def test_mongodb_search_escapes_regex_metacharacters(self):
        """A search term containing a regex metacharacter (e.g. "[") must be
        matched literally — an un-escaped $regex would otherwise be invalid
        regex syntax and silently match nothing."""
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.find_many = AsyncMock(return_value=[])

        config = {'internal_services': {'audit': {'collection_name': 'audit_logs'}}}
        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        await strategy.query({}, search="[bracket]")

        # First call is the primary search; its $or clauses must carry the
        # re.escape()'d pattern, not the raw bracket (which is a regex
        # metacharacter — passed through unescaped, pymongo/the server
        # itself would reject it as invalid regex).
        call_query = mock_db.find_many.call_args_list[0].kwargs['query']
        or_patterns = {clause[field]['$regex'] for clause in call_query['$or'] for field in clause}
        assert or_patterns == {r"\[bracket\]"}

    @pytest.mark.asyncio
    async def test_mongodb_search_matches_compressed_response_text(self):
        """A search term that only appears in a compressed response must
        still be found — response_plain (an always-plaintext copy, written
        only when the response is compressed) is included in the pushed-down
        $or, so this needs no separate decompress-and-check pass."""
        from services.audit import compress_text

        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.find_many = AsyncMock(return_value=[{
            '_id': '1', 'query': 'q', 'session_id': 's1',
            'response': compress_text('unique refund message'),
            'response_plain': 'unique refund message',
            'response_compressed': True,
        }])

        config = {'internal_services': {'audit': {'collection_name': 'audit_logs'}}}
        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        results = await strategy.query({}, search="refund")

        # A single query, not a primary-plus-decompress-scan pair.
        mock_db.find_many.assert_called_once()
        assert len(results) == 1
        assert results[0]['response'] == 'unique refund message'
        # The search-only helper field is never leaked in the API response.
        assert 'response_plain' not in results[0]

    async def test_mongodb_search_includes_response_plain_field(self):
        """response_plain must be one of the fields the pushed-down $or
        checks, since it's the only place a compressed response's text is
        searchable in plain form."""
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.find_many = AsyncMock(return_value=[])

        config = {'internal_services': {'audit': {'collection_name': 'audit_logs'}}}
        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        await strategy.query({}, search="refund")

        call_query = mock_db.find_many.call_args.kwargs['query']
        searched_fields = {field for clause in call_query['$or'] for field in clause}
        assert 'response_plain' in searched_fields


# ============================================================================
# Integration Tests
# ============================================================================

class TestAuditServiceIntegration:
    """Integration tests for audit service."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, sqlite_service_with_audit):
        """Test complete audit service lifecycle."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Log a conversation
        await audit.log_conversation(
            query="What's the weather?",
            response="It's sunny today.",
            ip="10.0.0.1",
            provider="test_llm",
            session_id="lifecycle_test",
            user_id="test_user",
            adapter_name="intent-duckdb-analytics"
        )

        # Query the log
        results = await audit.query_audit_logs({'session_id': 'lifecycle_test'})

        assert len(results) == 1
        record = results[0]
        assert record['query'] == "What's the weather?"
        assert record['response'] == "It's sunny today."
        assert record['provider'] == "test_llm"
        assert record['user_id'] == "test_user"
        assert record['adapter_name'] == "intent-duckdb-analytics"

    @pytest.mark.asyncio
    async def test_error_handling_graceful(self, sqlite_service_with_audit):
        """Test that audit errors don't crash the application."""
        services = sqlite_service_with_audit
        audit = services['audit']

        # Close the strategy to simulate error condition
        await audit._strategy.close()

        # This should not raise an exception
        await audit.log_conversation(
            query="Test",
            response="Response"
        )

        # Service should handle gracefully
        await audit.query_audit_logs({})
        # Results may be empty due to closed strategy, but no exception


# ============================================================================
# Compression Tests
# ============================================================================

class TestCompressionUtilities:
    """Tests for compression utility functions."""

    def test_compress_text(self):
        """Test text compression."""
        from services.audit import compress_text, decompress_text

        original = "This is a test response from an LLM that should compress well because text typically has patterns."
        compressed = compress_text(original)

        # Compressed should be base64 string
        assert isinstance(compressed, str)
        # Should decompress back to original
        decompressed = decompress_text(compressed)
        assert decompressed == original

    def test_compress_large_text(self):
        """Test compression on larger text (simulating LLM response)."""
        from services.audit import compress_text, decompress_text

        # Simulate a large LLM response
        original = "The capital of France is Paris. " * 100
        compressed = compress_text(original)
        decompressed = decompress_text(compressed)

        assert decompressed == original
        # Compression should be significant for repetitive text
        assert len(compressed) < len(original)

    def test_is_compressed(self):
        """Test compression detection."""
        from services.audit import compress_text, is_compressed

        original = "Plain text response"
        compressed = compress_text(original)

        assert is_compressed(compressed) is True
        assert is_compressed(original) is False
        assert is_compressed("") is False
        assert is_compressed(None) is False

    def test_compress_unicode(self):
        """Test compression with Unicode characters."""
        from services.audit import compress_text, decompress_text

        original = "Bonjour! 你好! مرحبا! 🌍🚀"
        compressed = compress_text(original)
        decompressed = decompress_text(compressed)

        assert decompressed == original


class TestAuditRecordCompression:
    """Tests for AuditRecord compression methods."""

    def test_to_dict_with_compression(self, sample_audit_record):
        """Test to_dict with compression enabled."""
        from services.audit import decompress_text

        result = sample_audit_record.to_dict(compress=True)

        assert result['response_compressed'] is True
        # Response should be compressed
        decompressed = decompress_text(result['response'])
        assert decompressed == "The capital of France is Paris."

    def test_to_dict_without_compression(self, sample_audit_record):
        """Test to_dict with compression disabled."""
        result = sample_audit_record.to_dict(compress=False)

        assert result['response_compressed'] is False
        assert result['response'] == "The capital of France is Paris."

    def test_to_flat_dict_with_compression(self, sample_audit_record):
        """Test to_flat_dict with compression enabled."""
        from services.audit import decompress_text

        result = sample_audit_record.to_flat_dict(compress=True)

        assert result['response_compressed'] == 1  # SQLite integer
        decompressed = decompress_text(result['response'])
        assert decompressed == "The capital of France is Paris."

    def test_to_flat_dict_without_compression(self, sample_audit_record):
        """Test to_flat_dict with compression disabled."""
        result = sample_audit_record.to_flat_dict(compress=False)

        assert result['response_compressed'] == 0  # SQLite integer
        assert result['response'] == "The capital of France is Paris."


class TestSQLiteAuditCompression:
    """Tests for SQLite audit storage with compression."""

    @pytest.mark.asyncio
    async def test_store_with_compression(self, tmp_path):
        """Test storing with compression enabled."""
        db_path = os.path.join(tmp_path, "test_compress.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'compress_responses': True  # Enable compression
                }
            }
        }

        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        # Log a conversation
        await audit_service.log_conversation(
            query="Test query",
            response="This is a test response that should be compressed.",
            session_id="compress_test"
        )

        # Query back (should be decompressed automatically)
        results = await audit_service.query_audit_logs({'session_id': 'compress_test'})

        assert len(results) == 1
        assert results[0]['response'] == "This is a test response that should be compressed."
        assert results[0]['response_compressed'] is True

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_query_remains_plain_text_when_response_is_compressed(self, tmp_path):
        """Query text should not be decompressed when only response compression is enabled."""
        db_path = os.path.join(tmp_path, "test_query_plain.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'compress_responses': True
                }
            }
        }

        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        query_text = "What is the status of order #12345?"
        await audit_service.log_conversation(
            query=query_text,
            response="Order #12345 is processing.",
            session_id="query_plain_test"
        )

        results = await audit_service.query_audit_logs({'session_id': 'query_plain_test'})

        assert len(results) == 1
        assert results[0]['query'] == query_text
        assert results[0]['response'] == "Order #12345 is processing."
        assert results[0]['response_compressed'] is True

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_store_without_compression(self, tmp_path):
        """Test storing without compression."""
        db_path = os.path.join(tmp_path, "test_no_compress.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'compress_responses': False  # Disable compression
                }
            }
        }

        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        await audit_service.log_conversation(
            query="Test query",
            response="Plain text response.",
            session_id="no_compress_test"
        )

        results = await audit_service.query_audit_logs({'session_id': 'no_compress_test'})

        assert len(results) == 1
        assert results[0]['response'] == "Plain text response."
        assert results[0]['response_compressed'] is False

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_search_matches_compressed_response_text(self, tmp_path):
        """A `search` term that only appears in a compressed response must
        still be found — the pushed-down query can only match a compressed
        response's base64-gzip bytes, so query() must also decompress and
        check compressed rows directly (see _merge_compressed_response_matches)."""
        db_path = os.path.join(tmp_path, "test_search_compressed.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {'type': 'sqlite', 'sqlite': {'database_path': db_path}},
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'compress_responses': True,
                },
            },
        }

        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()
        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        await audit_service.log_conversation(
            query="what's the policy", response="unique refund message", session_id="s1",
        )
        await audit_service.log_conversation(
            query="hello", response="hi, how can I help?", session_id="s2",
        )

        results = await audit_service.query_audit_logs({}, search="refund")
        assert len(results) == 1
        assert results[0]['session_id'] == 's1'
        assert results[0]['response'] == "unique refund message"

        await audit_service.close()
        sqlite_service.close()
        SQLiteService.clear_cache()


# ============================================================================
# Clear on Startup Tests
# ============================================================================

class TestClearOnStartup:
    """Tests for clear_on_startup functionality."""

    @pytest.mark.asyncio
    async def test_sqlite_clear_method(self, sqlite_service_with_audit, sample_audit_record):
        """Test that SQLite clear() method removes all audit records."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        # Store multiple records
        for i in range(5):
            record = AuditRecord(
                timestamp=datetime.now(),
                query=f"Query {i}",
                response=f"Response {i}",
                provider="test",
                blocked=False,
                ip="127.0.0.1"
            )
            await strategy.store(record)

        # Verify records exist
        results = await strategy.query({})
        assert len(results) == 5

        # Clear all records
        success = await strategy.clear()
        assert success is True

        # Verify all records are deleted
        results = await strategy.query({})
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_mongodb_clear_method(self):
        """Test that MongoDB clear() method removes all audit records (mocked)."""
        mock_db = AsyncMock()
        mock_db._initialized = True
        mock_db.create_index = AsyncMock()
        mock_db.clear_collection = AsyncMock(return_value=10)

        config = {
            'internal_services': {
                'audit': {
                    'collection_name': 'audit_logs'
                }
            }
        }

        strategy = MongoDBDAuditStrategy(config, mock_db)
        await strategy.initialize()

        success = await strategy.clear()

        assert success is True
        mock_db.clear_collection.assert_called_once_with('audit_logs')

    @pytest.mark.asyncio
    async def test_clear_on_startup_enabled(self, tmp_path):
        """Test that clear_on_startup=True clears audit logs during initialization."""
        db_path = os.path.join(tmp_path, "test_clear_startup.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'clear_on_startup': False  # Initially disabled
                }
            }
        }

        # First, create service and add some records
        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        # Store some records
        for i in range(3):
            await audit_service.log_conversation(
                query=f"Query {i}",
                response=f"Response {i}",
                session_id="startup_test"
            )

        # Verify records exist
        results = await audit_service.query_audit_logs({})
        assert len(results) == 3

        await audit_service.close()

        # Now enable clear_on_startup and create a new service
        config['internal_services']['audit']['clear_on_startup'] = True

        audit_service2 = AuditService(config, sqlite_service)
        await audit_service2.initialize()

        # Records should be cleared
        results = await audit_service2.query_audit_logs({})
        assert len(results) == 0

        await audit_service2.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_clear_on_startup_disabled(self, tmp_path):
        """Test that clear_on_startup=False preserves audit logs during initialization."""
        db_path = os.path.join(tmp_path, "test_no_clear_startup.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs',
                    'clear_on_startup': False
                }
            }
        }

        # Create service and add records
        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        audit_service = AuditService(config, sqlite_service)
        await audit_service.initialize()

        for i in range(3):
            await audit_service.log_conversation(
                query=f"Query {i}",
                response=f"Response {i}",
                session_id="preserve_test"
            )

        await audit_service.close()

        # Create new service (clear_on_startup still False)
        audit_service2 = AuditService(config, sqlite_service)
        await audit_service2.initialize()

        # Records should be preserved
        results = await audit_service2.query_audit_logs({})
        assert len(results) == 3

        await audit_service2.close()
        sqlite_service.close()
        SQLiteService.clear_cache()

    @pytest.mark.asyncio
    async def test_clear_on_startup_default_is_false(self, tmp_path):
        """Test that clear_on_startup defaults to False when not specified."""
        db_path = os.path.join(tmp_path, "test_default_clear.db")
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {
                    'type': 'sqlite',
                    'sqlite': {'database_path': db_path}
                },
                'audit': {
                    'enabled': True,
                    'storage_backend': 'sqlite',
                    'collection_name': 'audit_logs'
                    # clear_on_startup not specified
                }
            }
        }

        audit_service = AuditService(config)
        assert audit_service._clear_on_startup is False

    @pytest.mark.asyncio
    async def test_clear_empty_table(self, sqlite_service_with_audit):
        """Test that clear() works on an empty table."""
        services = sqlite_service_with_audit
        strategy = services['audit']._strategy

        # Clear empty table should succeed
        success = await strategy.clear()
        assert success is True

        # Verify still empty
        results = await strategy.query({})
        assert len(results) == 0


# ============================================================================
# Token usage / cost fields — round trip and aggregation
# ============================================================================

class TestUsageFieldsRoundTrip:
    """AuditRecord usage/cost fields must survive to_dict/to_flat_dict/store/query,
    distinguishing None (unreported/unpriced) from 0.0 (a real free/local rate)."""

    def test_to_dict_omits_none_usage_fields(self):
        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="ollama", blocked=False, ip="127.0.0.1",
        )
        result = record.to_dict()
        assert 'prompt_tokens' not in result
        assert 'cost_usd' not in result

    def test_to_dict_includes_zero_cost_explicitly(self):
        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="ollama", blocked=False, ip="127.0.0.1",
            prompt_tokens=10, completion_tokens=5, total_tokens=15,
            cost_usd=0.0, input_rate_per_1m=0.0, output_rate_per_1m=0.0,
            pricing_source="local_zero",
        )
        result = record.to_dict()
        assert result['cost_usd'] == 0.0
        assert result['pricing_source'] == "local_zero"

    def test_to_flat_dict_always_has_usage_keys(self):
        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="openai", blocked=False, ip="127.0.0.1",
        )
        flat = record.to_flat_dict()
        assert flat['prompt_tokens'] is None
        assert flat['reasoning_tokens'] is None
        assert flat['cost_usd'] is None
        assert flat['pricing_source'] is None
        assert flat['usage_unit'] is None
        assert flat['usage_quantity'] is None

    def test_to_dict_omits_usage_unit_when_none(self):
        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="openai", blocked=False, ip="127.0.0.1",
        )
        result = record.to_dict()
        assert 'usage_unit' not in result
        assert 'usage_quantity' not in result

    def test_to_dict_includes_usage_unit_when_set(self):
        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="openai", blocked=False, ip="127.0.0.1",
            usage_unit="images", usage_quantity=2.0,
            cost_usd=0.08, pricing_source="pattern",
        )
        result = record.to_dict()
        assert result['usage_unit'] == "images"
        assert result['usage_quantity'] == 2.0

    @pytest.mark.asyncio
    async def test_sqlite_store_and_query_preserves_media_usage_fields(self, sqlite_service_with_audit):
        """A discrete-unit media request (image generation, TTS, etc.) must
        round-trip usage_unit/usage_quantity alongside the shared cost_usd
        column, the same way a token-billed request round-trips tokens."""
        services = sqlite_service_with_audit
        audit_service = services['audit']

        record = AuditRecord(
            timestamp=datetime.now(), query="a photo of a cat", response="generated",
            provider="openai", blocked=False, ip="127.0.0.1",
            model="dall-e-3",
            usage_unit="images", usage_quantity=2.0,
            cost_usd=0.08, pricing_source="pattern",
        )
        success = await audit_service._strategy.store(record)
        assert success is True

        results = await audit_service.query_audit_logs({})
        assert len(results) == 1
        stored = results[0]
        assert stored['usage_unit'] == "images"
        assert stored['usage_quantity'] == pytest.approx(2.0)
        assert stored['cost_usd'] == pytest.approx(0.08)
        # A media-priced row has no tokens at all — must stay None, not 0.
        assert stored.get('prompt_tokens') is None

    @pytest.mark.asyncio
    async def test_sqlite_store_and_query_preserves_usage_fields(self, sqlite_service_with_audit):
        services = sqlite_service_with_audit
        audit_service = services['audit']

        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="openai", blocked=False, ip="127.0.0.1",
            model="gpt-4o-mini",
            prompt_tokens=1000, completion_tokens=200, total_tokens=1200,
            reasoning_tokens=80, cached_prompt_tokens=900,
            cost_usd=0.00027, input_rate_per_1m=0.15, output_rate_per_1m=0.60,
            pricing_source="exact",
        )
        success = await audit_service._strategy.store(record)
        assert success is True

        results = await audit_service.query_audit_logs({})
        assert len(results) == 1
        stored = results[0]
        assert stored['prompt_tokens'] == 1000
        assert stored['completion_tokens'] == 200
        assert stored['total_tokens'] == 1200
        assert stored['reasoning_tokens'] == 80
        assert stored['cached_prompt_tokens'] == 900
        assert stored['cost_usd'] == pytest.approx(0.00027)
        assert stored['pricing_source'] == "exact"

    @pytest.mark.asyncio
    async def test_log_conversation_persists_cached_prompt_tokens(self, sqlite_service_with_audit):
        """
        cached_prompt_tokens (Anthropic cache_control reads, DeepSeek/xAI
        automatic caching — see PricingService.estimate) must flow from the
        usage dict passed to log_conversation() through AuditRecord and into
        the stored row, the same path reasoning_tokens already takes, so the
        admin audit dossier can display it (see audit.js).
        """
        services = sqlite_service_with_audit
        audit_service = services['audit']

        await audit_service.log_conversation(
            query="hello", response="hi there",
            provider="anthropic", model="claude-sonnet-5",
            usage={
                "prompt_tokens": 1000, "completion_tokens": 50, "total_tokens": 1050,
                "cached_prompt_tokens": 900,
                "cost_usd": 0.00105, "pricing_source": "exact",
            },
        )

        results = await audit_service.query_audit_logs({})
        assert len(results) == 1
        assert results[0]['cached_prompt_tokens'] == 900

    @pytest.mark.asyncio
    async def test_log_conversation_omits_cached_prompt_tokens_when_absent(self, sqlite_service_with_audit):
        """A provider that never reports a cache hit must not gain a stray 0/None row."""
        services = sqlite_service_with_audit
        audit_service = services['audit']

        await audit_service.log_conversation(
            query="hello", response="hi there",
            provider="ollama", model="granite4:1b",
            usage={"prompt_tokens": 50, "completion_tokens": 10, "total_tokens": 60},
        )

        results = await audit_service.query_audit_logs({})
        assert results[0].get('cached_prompt_tokens') is None

    @pytest.mark.asyncio
    async def test_sqlite_store_local_zero_cost_is_not_dropped(self, sqlite_service_with_audit):
        """A real $0.00 local-model cost must round-trip as 0.0, not be
        indistinguishable from an unreported/unpriced request."""
        services = sqlite_service_with_audit
        audit_service = services['audit']

        record = AuditRecord(
            timestamp=datetime.now(), query="q", response="r",
            provider="ollama", blocked=False, ip="127.0.0.1",
            model="granite4:1b",
            prompt_tokens=50, completion_tokens=10, total_tokens=60,
            cost_usd=0.0, input_rate_per_1m=0.0, output_rate_per_1m=0.0,
            pricing_source="local_zero",
        )
        await audit_service._strategy.store(record)

        results = await audit_service.query_audit_logs({})
        stored = results[0]
        assert stored['cost_usd'] == 0.0
        assert stored['pricing_source'] == "local_zero"

    @pytest.mark.asyncio
    async def test_sqlite_migration_adds_usage_columns_to_old_table(self, tmp_path):
        """A table created before this feature (no usage columns) must gain
        them automatically on the next SQLiteService initialization, via the
        existing _migrate_table_schema DDL-diff mechanism."""
        db_path = os.path.join(tmp_path, "test_migrate.db")

        # Create an old-shape audit_logs table directly, bypassing SQLiteService's
        # current (already-migrated) schema.
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute('''
            CREATE TABLE audit_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                response TEXT NOT NULL,
                response_compressed INTEGER NOT NULL DEFAULT 0,
                provider TEXT,
                blocked INTEGER NOT NULL DEFAULT 0,
                ip TEXT,
                ip_type TEXT,
                ip_is_local INTEGER DEFAULT 0,
                ip_source TEXT,
                ip_original_value TEXT,
                api_key_value TEXT,
                api_key_timestamp TEXT,
                session_id TEXT,
                user_id TEXT,
                adapter_name TEXT,
                model TEXT
            )
        ''')
        conn.commit()
        conn.close()

        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {
                'backend': {'type': 'sqlite', 'sqlite': {'database_path': db_path}},
            }
        }
        sqlite_service = SQLiteService(config)
        await sqlite_service.initialize()

        conn = sqlite3.connect(db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(audit_logs)").fetchall()}
        conn.close()

        for expected in (
            'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens',
            'cached_prompt_tokens',
            'cost_usd', 'input_rate_per_1m', 'output_rate_per_1m', 'pricing_source',
            'usage_unit', 'usage_quantity', 'api_key_id',
        ):
            assert expected in columns, f"migration did not add column {expected}"

        # The migration must be additive, not merely column-present: an
        # existing database must open and be queryable before any new row
        # carrying api_key_id is ever written.
        rows = await sqlite_service.find_many('audit_logs', {})
        assert rows == []

        sqlite_service.close()
        SQLiteService.clear_cache()


class TestGroupByFieldMapping:
    """Every backend must accept the same logical group-by dimension names and
    resolve each to its own storage field/expression. Verified directly on
    the mapping (via _resolve_dimension_field, uniform across all four
    strategies since Phase 4) so Postgres/MongoDB/Elasticsearch are covered
    without a live server."""

    _SHARED = ("model", "provider", "adapter_name", "user_id", "call_type")
    _MINIMAL_CONFIG = {'internal_services': {'audit': {}}}

    def _strategies(self):
        from services.audit.sqlite_audit_strategy import SQLiteAuditStrategy
        from services.audit.postgres_audit_strategy import PostgresAuditStrategy
        from services.audit.mongodb_audit_strategy import MongoDBDAuditStrategy as MongoStrategy
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy
        return {
            "sqlite": SQLiteAuditStrategy(self._MINIMAL_CONFIG),
            "postgres": PostgresAuditStrategy(self._MINIMAL_CONFIG),
            "mongodb": MongoStrategy(self._MINIMAL_CONFIG),
            "elasticsearch": ElasticsearchAuditStrategy(self._MINIMAL_CONFIG),
        }

    @pytest.mark.unit
    def test_api_key_field_resolution(self):
        """SQLite/Postgres resolve api_key to a self-joining COALESCE
        expression (Phase 4 — merges legacy masked-only rows onto a newer
        row's stable id for the same key) via _resolve_dimension_field.
        Mongo/Elasticsearch resolve it via their own pipeline-level
        mechanisms instead (a $lookup stage / a precomputed masked-to-id
        map respectively — see the aggregate_usage tests), so
        _resolve_dimension_field intentionally returns None for them."""
        for name in ("sqlite", "postgres"):
            field = self._strategies()[name]._resolve_dimension_field("api_key")
            assert "api_key_id" in field and "api_key_value" in field and "SELECT" in field, name
        for name in ("mongodb", "elasticsearch"):
            assert self._strategies()[name]._resolve_dimension_field("api_key") is None, name

    @pytest.mark.unit
    def test_shared_dimensions_are_identity_mappings(self):
        for name, strategy in self._strategies().items():
            for dimension in self._SHARED:
                assert strategy._resolve_dimension_field(dimension) == dimension, f"{name}:{dimension}"

    @pytest.mark.unit
    def test_backend_field_names_are_not_accepted_as_dimensions(self):
        """The mapping is one-way: a caller passing the raw storage field name
        must not be able to reach it, so the API surface stays backend-agnostic."""
        for name, strategy in self._strategies().items():
            assert "api_key_value" not in strategy._GROUP_BY_FIELDS, name
            assert "api_key.key" not in strategy._GROUP_BY_FIELDS, name
            assert "api_key_id" not in strategy._GROUP_BY_FIELDS, name


class TestFilterFieldMapping:
    """Every backend must accept the same logical filter dimension names,
    reusing _resolve_dimension_field for non-api_key fields, and must not
    accept filters outside that allowlist (e.g. user_id, which is groupable
    but not filterable) or raw backend field names. api_key itself is
    special-cased inside each aggregate_usage (see the mixed-legacy/new-row
    tests), not resolved through this method."""

    _SHARED = ("provider", "adapter_name", "model", "call_type")
    _MINIMAL_CONFIG = {'internal_services': {'audit': {}}}

    def _strategies(self):
        from services.audit.sqlite_audit_strategy import SQLiteAuditStrategy
        from services.audit.postgres_audit_strategy import PostgresAuditStrategy
        from services.audit.mongodb_audit_strategy import MongoDBDAuditStrategy as MongoStrategy
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy
        return [SQLiteAuditStrategy, PostgresAuditStrategy, MongoStrategy, ElasticsearchAuditStrategy]

    @pytest.mark.unit
    def test_api_key_is_filterable(self):
        for strategy in self._strategies():
            assert "api_key" in strategy._FILTERABLE_DIMENSIONS, strategy.__name__

    @pytest.mark.unit
    def test_shared_dimensions_are_filterable(self):
        for strategy in self._strategies():
            for dimension in self._SHARED:
                assert dimension in strategy._FILTERABLE_DIMENSIONS, f"{strategy.__name__}:{dimension}"

    @pytest.mark.unit
    def test_user_id_is_not_filterable(self):
        """user_id is a valid group_by dimension but was never added to the
        filter allowlist — reusing _resolve_dimension_field for the mapping
        must not silently widen what's filterable."""
        for strategy in self._strategies():
            assert "user_id" not in strategy._FILTERABLE_DIMENSIONS, strategy.__name__

    @pytest.mark.unit
    def test_every_non_api_key_filterable_dimension_has_a_field_mapping(self):
        for strategy_cls in self._strategies():
            instance = strategy_cls(self._MINIMAL_CONFIG)
            for dimension in strategy_cls._FILTERABLE_DIMENSIONS - {"api_key"}:
                assert instance._resolve_dimension_field(dimension), f"{strategy_cls.__name__}:{dimension}"


class TestAggregateUsage:
    """SQLite aggregate_usage: bucketing, group-by, unpriced counting, window exclusion."""

    async def _seed(self, audit_service, rows):
        for row in rows:
            await audit_service._strategy.store(AuditRecord(**row))

    @pytest.mark.asyncio
    async def test_aggregate_totals_and_series(self, sqlite_service_with_audit):
        services = sqlite_service_with_audit
        audit_service = services['audit']

        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1"}
        await self._seed(audit_service, [
            {**base, "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
             "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost_usd": 0.01},
            {**base, "timestamp": datetime(2026, 1, 1, 11, 0, 0), "model": "gpt-4o-mini",
             "prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300, "cost_usd": 0.02},
            {**base, "timestamp": datetime(2026, 1, 2, 9, 0, 0), "model": "gpt-4o-mini",
             "prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75, "cost_usd": None},
            # Outside the query window — must be excluded.
            {**base, "timestamp": datetime(2025, 1, 1, 9, 0, 0), "model": "gpt-4o-mini",
             "prompt_tokens": 999, "completion_tokens": 999, "total_tokens": 1998, "cost_usd": 5.0},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-03T00:00:00",
            bucket="day", group_by="model",
        )

        assert result['totals']['requests'] == 3
        assert result['totals']['total_tokens'] == 525
        assert result['totals']['cost_usd'] == pytest.approx(0.03)
        assert result['totals']['unpriced_requests'] == 1

        assert len(result['series']) == 2  # two distinct days
        day_totals = {s['bucket']: s['requests'] for s in result['series']}
        assert sum(day_totals.values()) == 3

        assert len(result['groups']) == 1
        assert result['groups'][0]['key'] == "gpt-4o-mini"
        assert result['groups'][0]['requests'] == 3

    @pytest.mark.asyncio
    async def test_aggregate_usage_filters_and_groups_by_call_type(self, sqlite_service_with_audit):
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "cost_usd": 0.01}
        await self._seed(audit_service, [
            {**base, "model": "gpt-4o-mini", "call_type": "chat"},
            {**base, "model": "text-embedding-3-small", "call_type": "embedding", "cost_usd": 0.02},
        ])

        chat = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"call_type": "chat"}, group_by="call_type",
        )
        embeddings = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"call_type": "embedding"}, group_by="call_type",
        )

        assert chat["totals"]["requests"] == 1
        assert embeddings["totals"]["requests"] == 1
        assert embeddings["groups"][0]["key"] == "embedding"

    @pytest.mark.asyncio
    async def test_aggregate_usage_groups_by_api_key(self, sqlite_service_with_audit):
        """Grouping by the logical "api_key" dimension must resolve to the
        flattened api_key_value column (the masked key). Rows with no API key
        are excluded from `groups` but still counted in `totals`."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"},
             "cost_usd": 0.01},
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"},
             "cost_usd": 0.02},
            {**base, "api_key": {"key": "...bbb222", "timestamp": "2026-01-01T10:00:00"},
             "cost_usd": 0.05},
            # No API key (e.g. key enforcement disabled) — counted in totals only.
            {**base, "api_key": None, "cost_usd": 0.10},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            bucket="day", group_by="api_key",
        )

        assert result['totals']['requests'] == 4
        assert result['totals']['cost_usd'] == pytest.approx(0.18)

        groups = {group['key']: group for group in result['groups']}
        assert set(groups) == {"...aaa111", "...bbb222"}
        assert groups["...aaa111"]['requests'] == 2
        assert groups["...aaa111"]['cost_usd'] == pytest.approx(0.03)
        assert groups["...bbb222"]['requests'] == 1
        assert groups["...bbb222"]['cost_usd'] == pytest.approx(0.05)
        # Ranked by cost — the more expensive key leads.
        assert result['groups'][0]['key'] == "...bbb222"

    @pytest.mark.asyncio
    async def test_aggregate_usage_groups_by_api_key_prefers_stable_id(self, sqlite_service_with_audit):
        """Rows carrying the stable api_key_id (Phase 4) must group on it,
        not the masked value — and two rows sharing an id collapse into one
        group even if that id happens to not match their masked suffix."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00", "id": "key-id-1"},
             "cost_usd": 0.01},
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00", "id": "key-id-1"},
             "cost_usd": 0.02},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00", group_by="api_key",
        )

        assert len(result['groups']) == 1
        assert result['groups'][0]['key'] == "key-id-1"
        assert result['groups'][0]['requests'] == 2
        assert result['groups'][0]['cost_usd'] == pytest.approx(0.03)

    @pytest.mark.asyncio
    async def test_aggregate_usage_api_key_grouping_mixes_old_and_new_rows_without_duplicates(
        self, sqlite_service_with_audit
    ):
        """A store containing both pre-Phase-4 rows (masked value only) and
        post-Phase-4 rows (stable id present) for different keys must
        produce exactly one group per key — the id-less rows must not
        vanish, and neither key should appear twice."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            # Old-style rows for key A: no id, masked value only.
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.01},
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.01},
            # New-style rows for key B: stable id present.
            {**base, "api_key": {"key": "...bbb222", "timestamp": "2026-01-01T10:00:00", "id": "key-id-b"},
             "cost_usd": 0.05},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00", group_by="api_key",
        )

        groups = {g['key']: g for g in result['groups']}
        assert len(result['groups']) == 2
        assert groups["...aaa111"]['requests'] == 2
        assert groups["...aaa111"]['cost_usd'] == pytest.approx(0.02)
        assert groups["key-id-b"]['requests'] == 1
        assert groups["key-id-b"]['cost_usd'] == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_aggregate_usage_merges_legacy_and_new_rows_for_the_same_key(
        self, sqlite_service_with_audit
    ):
        """The exact upgrade scenario: one key with rows from before this
        deployment (masked value only, no api_key_id) and rows from after
        (stable id present). COALESCE(api_key_id, api_key_value) alone
        would split these into two groups since the legacy rows' resolved
        value ("...aaa111") differs from the new rows' ("key-id-1") — the
        self-join must resolve the legacy rows onto the SAME id, since
        another row for that key already recorded one."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            # Legacy rows for the key: no id yet.
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.01},
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.01},
            # A newer row for the SAME key: stable id now present.
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00", "id": "key-id-1"},
             "cost_usd": 0.05},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00", group_by="api_key",
        )

        assert len(result['groups']) == 1
        assert result['groups'][0]['key'] == "key-id-1"
        assert result['groups'][0]['requests'] == 3
        assert result['groups'][0]['cost_usd'] == pytest.approx(0.07)

        # Filtering by the id a group row exposes must include the legacy
        # rows too, not just the ones that carry the id themselves.
        filtered = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"api_key": "key-id-1"},
        )
        assert filtered['totals']['requests'] == 3
        assert filtered['totals']['cost_usd'] == pytest.approx(0.07)

    @pytest.mark.asyncio
    async def test_aggregate_usage_filters_by_stable_api_key_id(self, sqlite_service_with_audit):
        """Filtering by the stable id (as a group row's `key` would be, once
        Phase 4 rows exist) must narrow to just that key's rows."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00", "id": "key-id-1"},
             "cost_usd": 0.01},
            {**base, "api_key": {"key": "...bbb222", "timestamp": "2026-01-01T10:00:00", "id": "key-id-2"},
             "cost_usd": 0.05},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"api_key": "key-id-1"},
        )

        assert result['totals']['requests'] == 1
        assert result['totals']['cost_usd'] == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_aggregate_usage_filters_by_api_key(self, sqlite_service_with_audit):
        """Filtering by `api_key` (the masked value) must narrow totals to
        just that key's rows, matching the corresponding group's row from
        the unfiltered aggregate."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.01},
            {**base, "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.02},
            {**base, "api_key": {"key": "...bbb222", "timestamp": "2026-01-01T10:00:00"}, "cost_usd": 0.05},
        ])

        unfiltered = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00", group_by="api_key",
        )
        target_group = next(g for g in unfiltered['groups'] if g['key'] == "...aaa111")

        filtered = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"api_key": "...aaa111"},
        )

        assert filtered['totals']['requests'] == target_group['requests'] == 2
        assert filtered['totals']['cost_usd'] == pytest.approx(target_group['cost_usd']) == pytest.approx(0.03)

    @pytest.mark.asyncio
    async def test_aggregate_usage_api_key_filter_composes_with_provider_filter(self, sqlite_service_with_audit):
        """The api_key filter must narrow further within another active
        filter, not replace it."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        base = {"query": "q", "response": "r", "blocked": False, "ip": "127.0.0.1",
                "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini",
                "api_key": {"key": "...aaa111", "timestamp": "2026-01-01T10:00:00"},
                "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        await self._seed(audit_service, [
            {**base, "provider": "openai", "cost_usd": 0.01},
            {**base, "provider": "anthropic", "cost_usd": 0.02},
        ])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"api_key": "...aaa111", "provider": "openai"},
        )

        assert result['totals']['requests'] == 1
        assert result['totals']['cost_usd'] == pytest.approx(0.01)

    @pytest.mark.asyncio
    async def test_aggregate_usage_unknown_group_by_yields_no_groups(self, sqlite_service_with_audit):
        """An unrecognized dimension must produce no groups rather than being
        interpolated into the SQL as a column name."""
        services = sqlite_service_with_audit
        audit_service = services['audit']
        await self._seed(audit_service, [{
            "query": "q", "response": "r", "provider": "openai", "blocked": False, "ip": "127.0.0.1",
            "timestamp": datetime(2026, 1, 1, 10, 0, 0), "model": "gpt-4o-mini", "cost_usd": 0.01,
        }])

        result = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00", group_by="api_key_value",
        )

        assert result['totals']['requests'] == 1
        assert result['groups'] == []

    @pytest.mark.asyncio
    async def test_aggregate_usage_disabled_audit_returns_empty_skeleton(self, tmp_path):
        """AuditService.aggregate_usage must never raise — a disabled/unsupported
        backend returns the zeroed skeleton so the route can 200 with empty data."""
        config = {
            'general': {'inference_provider': 'test'},
            'internal_services': {'audit': {'enabled': False}},
        }
        audit_service = AuditService(config)
        await audit_service.initialize()

        result = await audit_service.aggregate_usage(since="2026-01-01", until="2026-01-02")

        assert result['totals']['requests'] == 0
        assert result['totals']['cost_usd'] == 0.0
        assert result['series'] == []
        assert result['groups'] == []


class TestElasticsearchWildcardEscaping:
    """A search term containing a Lucene wildcard metacharacter (*, ?) must
    be escaped before being embedded in a `wildcard` query pattern —
    otherwise the user's own literal "*"/"?" would be interpreted as a
    wildcard instead of matched as text."""

    def test_chat_strategy_escapes_wildcard_metacharacters(self):
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy
        assert ElasticsearchAuditStrategy._escape_wildcard("50% off*") == r"50% off\*"
        assert ElasticsearchAuditStrategy._escape_wildcard("a?b") == r"a\?b"
        assert ElasticsearchAuditStrategy._escape_wildcard(r"back\slash") == r"back\\slash"

    def test_admin_strategy_escapes_wildcard_metacharacters(self):
        from services.audit.elasticsearch_admin_audit_strategy import ElasticsearchAdminAuditStrategy
        assert ElasticsearchAdminAuditStrategy._escape_wildcard("50% off*") == r"50% off\*"
        assert ElasticsearchAdminAuditStrategy._escape_wildcard("a?b") == r"a\?b"


class TestElasticsearchRawSubfieldSearch:
    """A wildcard query against an analyzed `text` field can only match
    within a single indexed token, so a multi-word search term (e.g. "refund
    message") spanning a token boundary could never match "refund message"
    stored in `response`. query/response/response_plain must be searched via
    their `.raw` keyword multi-field instead, which holds the whole value
    verbatim."""

    def test_search_text_fields_target_the_raw_subfield(self):
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy
        assert ElasticsearchAuditStrategy._SEARCH_TEXT_FIELDS == (
            "query.raw", "response.raw", "response_plain.raw",
        )

    def test_mapping_declares_the_raw_subfield_with_a_length_ceiling(self):
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy
        props = ElasticsearchAuditStrategy._usage_mapping_properties()
        for field in ("query", "response", "response_plain"):
            assert props[field]["type"] == "text"
            raw = props[field]["fields"]["raw"]
            assert raw["type"] == "keyword"
            assert raw["ignore_above"] == ElasticsearchAuditStrategy._RAW_SUBFIELD_IGNORE_ABOVE

    @pytest.mark.asyncio
    async def test_query_builds_wildcard_clauses_against_raw_fields(self):
        """End-to-end (mocked client): the actual search query sent to
        Elasticsearch must reference `response.raw`, not bare `response`, so
        a multi-word term can match the whole stored value."""
        from services.audit.elasticsearch_audit_strategy import ElasticsearchAuditStrategy

        strategy = ElasticsearchAuditStrategy({'internal_services': {'audit': {}}})
        strategy._initialized = True
        strategy._es_client = AsyncMock()
        strategy._es_client.search = AsyncMock(return_value={"hits": {"hits": []}})

        await strategy.query({}, search="refund message")

        query_arg = strategy._es_client.search.call_args.kwargs["query"]
        should_fields = {
            field
            for clause in query_arg["bool"]["must"][0]["bool"]["should"]
            for field in clause["wildcard"]
        }
        assert "response.raw" in should_fields
        assert "response" not in should_fields


class TestPostgresSearchAlwaysBounded:
    """Whether Postgres's planner actually uses a pg_trgm GIN index for a
    given `ILIKE '%term%'` is a cost-based decision this code cannot verify
    or predict from the term alone — a pattern's selectivity (not just its
    length) determines whether the planner prefers the index or a full scan
    (e.g. a low-selectivity pattern like "..." can make the planner prefer a
    full scan even with the index present and the term 3+ characters long).
    So query() must always route search through the bounded fallback,
    regardless of _trgm_available or the term's length — there is no
    "trust the index" fast path left to accidentally bypass the bound.
    https://www.postgresql.org/docs/current/pgtrgm.html#PGTRGM-INDEX"""

    @pytest.mark.asyncio
    async def test_chat_strategy_always_uses_the_bounded_path(self):
        from services.audit.postgres_audit_strategy import PostgresAuditStrategy

        config = {'internal_services': {'audit': {'collection_name': 'audit_logs'}}}
        strategy = PostgresAuditStrategy(config, database_service=AsyncMock())
        strategy._initialized = True

        for trgm_available, term in ((True, "ab"), (True, "refund"), (False, "refund")):
            strategy._trgm_available = trgm_available
            with patch.object(strategy, "_bounded_contains_search", new=AsyncMock(return_value=[])) as bounded:
                await strategy.query({}, search=term)
            bounded.assert_called_once()
            strategy._database_service.find_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_strategy_always_uses_the_bounded_path(self):
        from services.audit.postgres_admin_audit_strategy import PostgresAdminAuditStrategy

        config = {'internal_services': {'audit': {'admin_events': {'collection_name': 'audit_admin_logs'}}}}
        strategy = PostgresAdminAuditStrategy(config, database_service=AsyncMock())
        strategy._initialized = True

        for trgm_available, term in ((True, "ab"), (True, "alice"), (False, "alice")):
            strategy._trgm_available = trgm_available
            with patch.object(strategy, "_bounded_contains_search", new=AsyncMock(return_value=[])) as bounded:
                await strategy.query({}, search=term)
            bounded.assert_called_once()
            strategy._database_service.find_many.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
