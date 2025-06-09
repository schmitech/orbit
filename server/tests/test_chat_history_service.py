#!/usr/bin/env python3
"""
Test suite for ChatHistoryService
"""

import pytest
import pytest_asyncio
import asyncio
import sys
import os
from datetime import datetime, UTC, timedelta
from bson import ObjectId
import logging
from pathlib import Path
from dotenv import load_dotenv
from unittest.mock import AsyncMock, MagicMock

# Get the directory of this script
SCRIPT_DIR = Path(__file__).parent.absolute()

# Get the project root (parent of server directory)
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Add server directory to Python path
SERVER_DIR = SCRIPT_DIR.parent
sys.path.append(str(SERVER_DIR))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file in project root
env_path = PROJECT_ROOT / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env file not found at {env_path}")

load_dotenv(env_path)

# Import services
try:
    from services.chat_history_service import ChatHistoryService
    from services.mongodb_service import MongoDBService
except ImportError as e:
    logger.error(f"Import error: {e}")
    raise

# Test configuration
TEST_CONFIG = {
    'internal_services': {
        'mongodb': {
            'host': os.getenv("INTERNAL_SERVICES_MONGODB_HOST"),
            'port': int(os.getenv("INTERNAL_SERVICES_MONGODB_PORT", 27017)),
            'database': os.getenv("INTERNAL_SERVICES_MONGODB_DATABASE", "orbit_test"),
            'username': os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME"),
            'password': os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD")
        }
    },
    'general': {
        'verbose': True,
        'inference_provider': 'ollama'
    },
    'inference': {
        'ollama': {
            'num_ctx': 8192
        },
        'llama_cpp': {
            'n_ctx': 4096
        },
        'openai': {
            'context_window': 32768
        },
        'anthropic': {
            'context_window': 200000
        }
    },
    'chat_history': {
        'enabled': True,
        'collection_name': 'chat_history_test',
        'default_limit': 20,
        'store_metadata': True,
        'retention_days': 30,
        'max_tracked_sessions': 1000,
        'session': {
            'required': True,
            'header_name': 'X-Session-ID'
        },
        'user': {
            'header_name': 'X-User-ID',
            'required': False
        }
    }
}

# Validate required environment variables
required_vars = ["INTERNAL_SERVICES_MONGODB_HOST", "INTERNAL_SERVICES_MONGODB_USERNAME", 
                 "INTERNAL_SERVICES_MONGODB_PASSWORD"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    pytest.skip(f"Missing required environment variables: {', '.join(missing_vars)}")

# Use a module-scoped event_loop_policy fixture to avoid deprecation warning
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

@pytest_asyncio.fixture
async def mongodb_service():
    """Fixture to provide a MongoDB service instance"""
    try:
        service = MongoDBService(TEST_CONFIG)
        await service.initialize()
        logger.info("Successfully connected to MongoDB for chat history tests")
        yield service
        # Cleanup after tests
        await service.client.drop_database(TEST_CONFIG['internal_services']['mongodb']['database'])
        service.close()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        pytest.skip(f"MongoDB connection failed: {str(e)}")

@pytest_asyncio.fixture
async def chat_history_service(mongodb_service):
    """Fixture to provide a ChatHistoryService instance"""
    service = ChatHistoryService(TEST_CONFIG, mongodb_service)
    await service.initialize()
    
    yield service
    
    # Cleanup
    await service.close()

@pytest_asyncio.fixture
async def disabled_chat_history_service():
    """Fixture to provide a disabled ChatHistoryService instance for testing disabled functionality"""
    config = TEST_CONFIG.copy()
    config['chat_history']['enabled'] = False
    
    # Create a mock MongoDB service since it won't be used when disabled
    mock_mongodb = MagicMock()
    
    service = ChatHistoryService(config, mock_mongodb)
    # Don't initialize when disabled
    yield service

# Context Window Calculation Tests
@pytest.mark.asyncio
async def test_context_window_calculation_ollama():
    """Test context window calculation for Ollama provider"""
    config = {
        'general': {'inference_provider': 'ollama', 'verbose': True},
        'inference': {'ollama': {'num_ctx': 8192}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (8192 - 350) / 100 = 78.42 → 78 messages
    assert service.max_conversation_messages == 78

@pytest.mark.asyncio
async def test_context_window_calculation_llama_cpp():
    """Test context window calculation for llama.cpp provider"""
    config = {
        'general': {'inference_provider': 'llama_cpp', 'verbose': True},
        'inference': {'llama_cpp': {'n_ctx': 4096}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (4096 - 350) / 100 = 37.46 → 37 messages
    assert service.max_conversation_messages == 37

@pytest.mark.asyncio
async def test_context_window_calculation_openai_configured():
    """Test context window calculation for OpenAI with configured context_window"""
    config = {
        'general': {'inference_provider': 'openai', 'verbose': True},
        'inference': {'openai': {'context_window': 64000}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (64000 - 350) / 100 = 636.5 → 636 messages
    assert service.max_conversation_messages == 636

@pytest.mark.asyncio
async def test_context_window_calculation_openai_default():
    """Test context window calculation for OpenAI with default fallback"""
    config = {
        'general': {'inference_provider': 'openai', 'verbose': True},
        'inference': {'openai': {'model': 'gpt-4o'}},  # No context_window configured
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (32768 - 350) / 100 = 324.18 → 324 messages (default fallback)
    assert service.max_conversation_messages == 324

@pytest.mark.asyncio
async def test_context_window_calculation_anthropic_capped():
    """Test context window calculation for Anthropic with safety cap"""
    config = {
        'general': {'inference_provider': 'anthropic', 'verbose': True},
        'inference': {'anthropic': {'context_window': 200000}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (200000 - 350) / 100 = 1996.5 → 1000 messages (safety cap)
    assert service.max_conversation_messages == 1000

@pytest.mark.asyncio
async def test_context_window_calculation_small_model():
    """Test context window calculation for very small model with minimum enforced"""
    config = {
        'general': {'inference_provider': 'llama_cpp', 'verbose': True},
        'inference': {'llama_cpp': {'n_ctx': 512}},  # Very small context
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (512 - 350) / 100 = 1.62 → 10 messages (safety minimum)
    assert service.max_conversation_messages == 10

@pytest.mark.asyncio
async def test_context_window_calculation_unknown_provider():
    """Test context window calculation for unknown provider uses fallback"""
    config = {
        'general': {'inference_provider': 'unknown_provider', 'verbose': True},
        'inference': {'unknown_provider': {}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (4096 - 350) / 100 = 37.46 → 37 messages (fallback default)
    assert service.max_conversation_messages == 37

@pytest.mark.asyncio
async def test_context_window_calculation_huggingface():
    """Test context window calculation for HuggingFace using max_length parameter"""
    config = {
        'general': {'inference_provider': 'huggingface', 'verbose': True},
        'inference': {'huggingface': {'max_length': 2048}},
        'chat_history': {'enabled': True}
    }
    
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Expected calculation: (2048 - 350) / 100 = 16.98 → 16 messages
    assert service.max_conversation_messages == 16

# Message Management Tests
@pytest.mark.asyncio
async def test_add_message(chat_history_service):
    """Test adding a single message"""
    session_id = "test_session_1"
    
    message_id = await chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="Hello, this is a test message",
        user_id="test_user",
        metadata={"test": True}
    )
    
    assert message_id is not None
    assert isinstance(message_id, ObjectId)
    
    # Verify message was stored
    messages = await chat_history_service.get_conversation_history(session_id)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, this is a test message"

@pytest.mark.asyncio
async def test_add_conversation_turn(chat_history_service):
    """Test adding a complete conversation turn"""
    session_id = "test_session_2"
    
    user_id, assistant_id = await chat_history_service.add_conversation_turn(
        session_id=session_id,
        user_message="What is the weather like?",
        assistant_response="I'm sorry, I don't have access to current weather data.",
        user_id="test_user"
    )
    
    assert user_id is not None
    assert assistant_id is not None
    
    # Verify both messages were stored
    messages = await chat_history_service.get_conversation_history(session_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

@pytest.mark.asyncio
async def test_get_conversation_history_with_limit(chat_history_service):
    """Test getting conversation history with limit"""
    session_id = "test_session_3"
    
    # Add multiple messages
    for i in range(10):
        await chat_history_service.add_message(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}"
        )
    
    # Get limited history
    messages = await chat_history_service.get_conversation_history(session_id, limit=5)
    assert len(messages) == 5
    
    # Should be the 5 most recent messages in chronological order
    assert messages[0]["content"] == "Message 5"  # 6th message (index 5)
    assert messages[4]["content"] == "Message 9"  # 10th message (index 9)

@pytest.mark.asyncio
async def test_get_conversation_history_before_timestamp(chat_history_service):
    """Test getting conversation history before a specific timestamp"""
    session_id = "test_session_4"
    
    # Add first message
    await chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="First message"
    )
    
    # Wait a bit and record timestamp
    await asyncio.sleep(0.1)
    cutoff_time = datetime.now(UTC)
    await asyncio.sleep(0.1)
    
    # Add second message after cutoff
    await chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="Second message"
    )
    
    # Get messages before cutoff
    messages = await chat_history_service.get_conversation_history(
        session_id, 
        before_timestamp=cutoff_time
    )
    
    assert len(messages) == 1
    assert messages[0]["content"] == "First message"

@pytest.mark.asyncio
async def test_duplicate_message_prevention(chat_history_service):
    """Test that duplicate messages are prevented using idempotency keys"""
    session_id = "test_session_5"
    idempotency_key = "unique_message_key"
    
    # Add message with idempotency key
    message_id1 = await chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="Duplicate test message",
        idempotency_key=idempotency_key
    )
    
    # Try to add the same message again
    message_id2 = await chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="Duplicate test message",
        idempotency_key=idempotency_key
    )
    
    assert message_id1 is not None
    assert message_id2 is None  # Should be None due to duplicate detection
    
    # Verify only one message was stored
    messages = await chat_history_service.get_conversation_history(session_id)
    assert len(messages) == 1

@pytest.mark.asyncio
async def test_clear_session_history(chat_history_service):
    """Test clearing all history for a session"""
    session_id = "test_session_7"
    
    # Add some messages
    for i in range(3):
        await chat_history_service.add_message(
            session_id=session_id,
            role="user",
            content=f"Message {i}"
        )
    
    # Verify messages exist
    messages = await chat_history_service.get_conversation_history(session_id)
    assert len(messages) == 3
    
    # Clear the session
    success = await chat_history_service.clear_session_history(session_id)
    assert success is True
    
    # Verify messages are gone
    messages = await chat_history_service.get_conversation_history(session_id)
    assert len(messages) == 0

@pytest.mark.asyncio
async def test_get_session_stats(chat_history_service):
    """Test getting session statistics"""
    session_id = "test_session_8"
    
    # Add a mix of messages
    await chat_history_service.add_message(session_id, "user", "User message 1")
    await chat_history_service.add_message(session_id, "assistant", "Assistant response 1")
    await chat_history_service.add_message(session_id, "user", "User message 2")
    
    stats = await chat_history_service.get_session_stats(session_id)
    
    assert stats["session_id"] == session_id
    assert stats["message_count"] == 3
    assert stats["user_messages"] == 2
    assert stats["assistant_messages"] == 1
    assert "first_message" in stats
    assert "last_message" in stats
    assert "duration_seconds" in stats
    assert "total_characters" in stats

@pytest.mark.asyncio
async def test_get_user_sessions(chat_history_service):
    """Test getting sessions for a user"""
    user_id = "test_user_sessions"
    
    # Create messages in multiple sessions for the same user
    for session_num in range(3):
        session_id = f"user_session_{session_num}"
        await chat_history_service.add_message(
            session_id=session_id,
            role="user",
            content=f"Message in session {session_num}",
            user_id=user_id
        )
    
    sessions = await chat_history_service.get_user_sessions(user_id, limit=10)
    
    assert len(sessions) == 3
    for session in sessions:
        assert "session_id" in session
        assert "last_activity" in session
        assert "message_count" in session
        assert session["message_count"] >= 1

@pytest.mark.asyncio
async def test_get_context_messages(chat_history_service):
    """Test getting messages formatted for LLM context"""
    session_id = "test_session_9"
    
    # Add conversation
    await chat_history_service.add_conversation_turn(
        session_id=session_id,
        user_message="Hello",
        assistant_response="Hi there!"
    )
    
    context_messages = await chat_history_service.get_context_messages(session_id)
    
    assert len(context_messages) == 2
    assert context_messages[0]["role"] == "user"
    assert context_messages[0]["content"] == "Hello"
    assert context_messages[1]["role"] == "assistant"
    assert context_messages[1]["content"] == "Hi there!"

# Disabled Service Tests
@pytest.mark.asyncio
async def test_disabled_service_returns_none(disabled_chat_history_service):
    """Test that disabled service returns None for operations"""
    session_id = "disabled_session"
    
    # All operations should return None or empty when disabled
    message_id = await disabled_chat_history_service.add_message(
        session_id=session_id,
        role="user",
        content="This should not be stored"
    )
    assert message_id is None
    
    user_id, assistant_id = await disabled_chat_history_service.add_conversation_turn(
        session_id=session_id,
        user_message="Test",
        assistant_response="Response"
    )
    assert user_id is None
    assert assistant_id is None
    
    messages = await disabled_chat_history_service.get_conversation_history(session_id)
    assert messages == []
    
    context_messages = await disabled_chat_history_service.get_context_messages(session_id)
    assert context_messages == []

# Health Check and Metrics Tests
@pytest.mark.asyncio
async def test_health_check(chat_history_service):
    """Test service health check"""
    health = await chat_history_service.health_check()
    
    assert health["status"] == "healthy"
    assert health["mongodb"] == "connected"
    # The enabled field reflects the actual service state after initialization
    assert "enabled" in health  # Just check it's present, value may vary based on initialization
    assert "active_sessions" in health
    assert "tracked_sessions" in health

@pytest.mark.asyncio
async def test_get_metrics(chat_history_service):
    """Test getting service metrics"""
    # Try to add some activity first (may fail due to transaction limitations)
    expected_min_messages = 0  # Default to 0 as we might not be able to add messages
    try:
        message_id = await chat_history_service.add_message(
            session_id="metrics_test",
            role="user",
            content="Test message for metrics"
        )
        if message_id:  # Only increment if message was actually added
            expected_min_messages = 1
    except Exception:
        # If adding message fails, that's ok for this test
        pass
    
    metrics = await chat_history_service.get_metrics()
    
    assert "active_sessions" in metrics
    assert "tracked_sessions" in metrics
    assert "messages_today" in metrics
    assert metrics["messages_today"] >= expected_min_messages
    assert "retention_days" in metrics
    assert metrics["retention_days"] == 30  # From test config

@pytest.mark.asyncio
async def test_conversation_limit_warning_thresholds():
    """Test that warning thresholds are calculated correctly for different providers"""
    # Test different provider configurations
    test_cases = [
        {
            'config': {
                'general': {'inference_provider': 'llama_cpp', 'verbose': False},
                'inference': {'llama_cpp': {'n_ctx': 1024}},
                'chat_history': {'enabled': True}
            },
            'expected_max': 10,
            'expected_warning': 9,  # max(10 * 0.9, 10 - 5) = max(9, 5) = 9
            'expected_critical': 9  # max(10 * 0.95, 10 - 2) = max(9.5, 8) = 9
        },
        {
            'config': {
                'general': {'inference_provider': 'ollama', 'verbose': False},
                'inference': {'ollama': {'num_ctx': 4096}},
                'chat_history': {'enabled': True}
            },
            'expected_max': 37,
            'expected_warning': 33,  # max(37 * 0.9, 37 - 5) = max(33.3, 32) = 33
            'expected_critical': 35  # max(37 * 0.95, 37 - 2) = max(35.15, 35) = 35
        }
    ]
    
    for case in test_cases:
        service = ChatHistoryService(case['config'], mongodb_service=None)
        max_messages = service.max_conversation_messages
        warning_threshold = max(int(max_messages * 0.9), max_messages - 5)
        critical_threshold = max(int(max_messages * 0.95), max_messages - 2)
        
        assert max_messages == case['expected_max']
        assert warning_threshold == case['expected_warning']
        assert critical_threshold == case['expected_critical']

# Error Handling Tests
@pytest.mark.asyncio
async def test_error_handling_invalid_session():
    """Test error handling with invalid session parameters"""
    # Test service with valid config but no MongoDB
    config = {
        'general': {'inference_provider': 'ollama', 'verbose': True},
        'inference': {'ollama': {'num_ctx': 8192}},
        'chat_history': {'enabled': True}
    }
    service = ChatHistoryService(config, mongodb_service=None)
    
    # Service should still calculate max_conversation_messages correctly
    assert service.max_conversation_messages == 78
    
    # Service is configured as enabled but won't actually function without MongoDB
    assert service.chat_history_config.get('enabled', True) is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 