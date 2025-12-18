#!/usr/bin/env python3
"""
Unit Tests for Logger Service
==============================

Tests for the LoggerService that handles logging to file and Elasticsearch.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_asyncio import fixture

# Add parent directories to path (server directory)
SCRIPT_DIR = Path(__file__).parent.absolute()
SERVER_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SERVER_DIR))

from services.logger_service import LoggerService


# ============================================================================
# Fixtures
# ============================================================================

@fixture(scope="function")
async def test_config(tmp_path):
    """Create a minimal test configuration."""
    log_dir = os.path.join(tmp_path, "logs")
    os.makedirs(log_dir, exist_ok=True)

    return {
        'general': {
            'inference_provider': 'test_provider'
        },
        'internal_services': {
            'elasticsearch': {
                'enabled': False  # Disable ES for unit tests
            }
        },
        'logging': {
            'file': {
                'directory': log_dir
            }
        }
    }


@fixture(scope="function")
async def logger_service(test_config):
    """Fixture to create and initialize a logger service for testing."""
    service = LoggerService(test_config)
    await service.initialize_elasticsearch()

    try:
        yield service
    finally:
        await service.close()


# ============================================================================
# LoggerService Basic Tests
# ============================================================================

@pytest.mark.asyncio
async def test_logger_service_initialization(logger_service):
    """Test that LoggerService initializes correctly."""
    assert logger_service is not None
    assert logger_service.inference_provider == 'test_provider'
    # ES should be disabled in test config
    assert logger_service.es_client is None


@pytest.mark.asyncio
async def test_log_conversation(logger_service):
    """Test logging a conversation (ES disabled, should not raise)."""
    test_query = "What is the capital of France?"
    test_response = "The capital of France is Paris."
    test_ip = "192.168.1.100"

    # Should not raise when ES is disabled
    await logger_service.log_conversation(
        query=test_query,
        response=test_response,
        ip=test_ip,
        backend="ollama-test",
        blocked=False
    )


@pytest.mark.asyncio
async def test_log_localhost(logger_service):
    """Test logging with localhost IP."""
    localhost_ip = "127.0.0.1"
    await logger_service.log_conversation(
        query="Local test query",
        response="Local test response",
        ip=localhost_ip,
        backend="ollama-test",
        blocked=False
    )


@pytest.mark.asyncio
async def test_log_blocked(logger_service):
    """Test logging a blocked query."""
    await logger_service.log_conversation(
        query="This is a blocked query",
        response="I cannot assist with that request",
        ip="203.0.113.1",  # Example external IP
        backend="ollama-test",
        blocked=True
    )


@pytest.mark.asyncio
async def test_log_with_session_and_user(logger_service):
    """Test logging with session and user IDs."""
    await logger_service.log_conversation(
        query="Test query with IDs",
        response="Test response",
        ip="10.0.0.1",
        backend="ollama-test",
        blocked=False,
        session_id="test-session-123",
        user_id="test-user-456"
    )


@pytest.mark.asyncio
async def test_log_with_api_key(logger_service):
    """Test logging with API key."""
    await logger_service.log_conversation(
        query="Test query with API key",
        response="Test response",
        ip="10.0.0.1",
        backend="ollama-test",
        blocked=False,
        api_key="orbit_test_key_12345"
    )


# ============================================================================
# IP Formatting Tests
# ============================================================================

@pytest.mark.asyncio
async def test_format_ip_localhost(logger_service):
    """Test IP formatting for localhost (127.0.0.1 -> 'localhost')."""
    ip_metadata = logger_service._format_ip_address("127.0.0.1")

    # Localhost IPs are converted to 'localhost' with type 'local'
    assert ip_metadata['address'] == "localhost"
    assert ip_metadata['isLocal'] is True
    assert ip_metadata['type'] == 'local'
    assert ip_metadata['originalValue'] == "127.0.0.1"


@pytest.mark.asyncio
async def test_format_ip_ipv4_external(logger_service):
    """Test IP formatting for external IPv4 (8.8.8.8 - Google DNS)."""
    ip_metadata = logger_service._format_ip_address("8.8.8.8")

    assert ip_metadata['address'] == "8.8.8.8"
    assert ip_metadata['type'] == 'ipv4'
    assert ip_metadata['isLocal'] is False  # Truly external IP


@pytest.mark.asyncio
async def test_format_ip_ipv4_private(logger_service):
    """Test IP formatting for private IPv4."""
    ip_metadata = logger_service._format_ip_address("192.168.1.100")

    assert ip_metadata['address'] == "192.168.1.100"
    assert ip_metadata['type'] == 'ipv4'
    assert ip_metadata['isLocal'] is True  # Private IPs are considered local


@pytest.mark.asyncio
async def test_format_ip_ipv6_loopback(logger_service):
    """Test IP formatting for IPv6 loopback (::1 -> 'localhost')."""
    ip_metadata = logger_service._format_ip_address("::1")

    # IPv6 loopback is converted to 'localhost' with type 'local'
    assert ip_metadata['address'] == "localhost"
    assert ip_metadata['isLocal'] is True
    assert ip_metadata['type'] == 'local'


@pytest.mark.asyncio
async def test_format_ip_none(logger_service):
    """Test IP formatting for None."""
    ip_metadata = logger_service._format_ip_address(None)

    # None returns default metadata with 'unknown' values
    assert ip_metadata['address'] == "unknown"
    assert ip_metadata['type'] == 'unknown'


@pytest.mark.asyncio
async def test_format_ip_invalid(logger_service):
    """Test IP formatting for invalid IP string."""
    ip_metadata = logger_service._format_ip_address("not-an-ip")

    # Invalid IPs are still processed (assumed ipv4), but _is_local_ip fails gracefully
    assert ip_metadata['originalValue'] == "not-an-ip"
    assert ip_metadata['type'] == 'ipv4'  # Assumed IPv4 if no colons
    assert ip_metadata['isLocal'] is False  # ValueError in is_private returns False


@pytest.mark.asyncio
async def test_format_ip_list(logger_service):
    """Test IP formatting for list of IPs (proxy scenario)."""
    ip_metadata = logger_service._format_ip_address(["192.168.1.1", "10.0.0.1"])

    # Takes first IP from list, marks as proxy
    assert ip_metadata['address'] == "192.168.1.1"
    assert ip_metadata['source'] == "proxy"
    assert ip_metadata['originalValue'] == "192.168.1.1"  # Returns the cleaned first IP


# ============================================================================
# Elasticsearch Mocked Tests
# ============================================================================

@pytest.mark.asyncio
async def test_log_conversation_with_es_mocked(test_config):
    """Test logging to Elasticsearch with mocked client."""
    # Enable ES in config
    test_config['internal_services']['elasticsearch']['enabled'] = True
    test_config['internal_services']['elasticsearch']['node'] = 'http://localhost:9200'
    test_config['internal_services']['elasticsearch']['index'] = 'test_orbit'

    service = LoggerService(test_config)

    # Mock the ES client
    mock_es = AsyncMock()
    mock_es.ping = AsyncMock(return_value=True)
    mock_es.indices.exists = AsyncMock(return_value=False)
    mock_es.indices.create = AsyncMock()
    mock_es.index = AsyncMock()
    mock_es.close = AsyncMock()

    service.es_client = mock_es

    # Log a conversation
    await service.log_conversation(
        query="Test query",
        response="Test response",
        ip="192.168.1.100",
        backend="test-backend",
        blocked=False
    )

    # Verify ES index was called
    mock_es.index.assert_called_once()
    call_kwargs = mock_es.index.call_args[1]
    assert call_kwargs['index'] == 'test_orbit'
    assert 'document' in call_kwargs
    assert call_kwargs['document']['query'] == "Test query"
    assert call_kwargs['document']['response'] == "Test response"

    await service.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
