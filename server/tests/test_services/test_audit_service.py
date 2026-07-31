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
from unittest.mock import AsyncMock

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
            reasoning_tokens=80,
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
        assert stored['cost_usd'] == pytest.approx(0.00027)
        assert stored['pricing_source'] == "exact"

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
            'cost_usd', 'input_rate_per_1m', 'output_rate_per_1m', 'pricing_source',
            'usage_unit', 'usage_quantity',
        ):
            assert expected in columns, f"migration did not add column {expected}"

        sqlite_service.close()
        SQLiteService.clear_cache()


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
            {**base, "model": "gpt-4o-mini", "call_type": None},
            {**base, "model": "text-embedding-3-small", "call_type": "embedding", "cost_usd": 0.02},
        ])

        inference = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"call_type": "inference"}, group_by="call_type",
        )
        embeddings = await audit_service.aggregate_usage(
            since="2026-01-01T00:00:00", until="2026-01-02T00:00:00",
            filters={"call_type": "embedding"}, group_by="call_type",
        )

        assert inference["totals"]["requests"] == 1
        assert embeddings["totals"]["requests"] == 1
        assert embeddings["groups"][0]["key"] == "embedding"

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
