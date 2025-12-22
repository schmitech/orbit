"""
Unit Tests for Audit Service
=============================

Tests for the AuditService, AuditStorageStrategy implementations,
and strategy selection logic.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_asyncio import fixture

# Add parent directories to path
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.audit import (
    AuditService,
    AuditStorageStrategy,
    AuditRecord,
    SQLiteAuditStrategy,
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
        backend="test_provider",
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
        user_id="user_xyz789"
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
            backend="test",
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
        assert result['backend'] == "test_provider"
        assert result['blocked'] is False
        assert 'ip_metadata' in result
        assert 'api_key' in result
        assert result['session_id'] == "session_abc123"

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
            backend="test",
            blocked=False,
            ip="127.0.0.1"
        )
        await strategy.store(normal_record)

        # Store blocked record
        blocked_record = AuditRecord(
            timestamp=datetime.now(),
            query="Blocked query",
            response="I cannot assist with that request",
            backend="test",
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
            backend="ollama",
            blocked=False,
            api_key="test_key",
            session_id="session_123",
            user_id="user_456"
        )

        # Verify record was stored
        results = await audit.query_audit_logs({'session_id': 'session_123'})
        assert len(results) == 1

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
                backend="test"
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

        # Verify indexes were created
        assert mock_db.create_index.call_count >= 5  # timestamp, session_id, user_id, blocked, backend, compound

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
            backend="test_llm",
            session_id="lifecycle_test",
            user_id="test_user"
        )

        # Query the log
        results = await audit.query_audit_logs({'session_id': 'lifecycle_test'})

        assert len(results) == 1
        record = results[0]
        assert record['query'] == "What's the weather?"
        assert record['response'] == "It's sunny today."
        assert record['backend'] == "test_llm"
        assert record['user_id'] == "test_user"

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
        results = await audit.query_audit_logs({})
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
                backend="test",
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
