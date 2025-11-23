"""
Shared fixtures for chat handlers tests.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, Mock

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Add the project root to fix import issues
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))


@pytest.fixture
def base_config():
    """Basic configuration for testing."""
    return {
        'general': {
            'inference_provider': 'openai'
        },
        'chat_history': {
            'enabled': True
        },
        'messages': {
            'conversation_limit_warning': (
                "Warning: Conversation is using {current_tokens}/{max_tokens} tokens."
            )
        },
        'sound': {
            'provider': 'openai',
            'tts_limits': {
                'max_text_length': 4096,
                'max_audio_size_mb': 5,
                'truncate_text': True,
                'warn_on_truncate': True
            }
        },
        'sounds': {
            'openai': {
                'tts_format': 'mp3'
            }
        }
    }


@pytest.fixture
def mock_adapter_manager():
    """Mock adapter manager."""
    manager = MagicMock()
    manager.get_adapter_config.return_value = {
        'type': 'passthrough',
        'inference_provider': 'openai',
        'audio_provider': 'openai',
        'config': {
            'timezone': 'America/New_York'
        }
    }
    return manager


@pytest.fixture
def mock_chat_history_service():
    """Mock chat history service."""
    service = AsyncMock()
    service.get_context_messages = AsyncMock(return_value=[
        {'role': 'user', 'content': 'Hello'},
        {'role': 'assistant', 'content': 'Hi there!'}
    ])
    service.add_conversation_turn = AsyncMock()
    service._session_token_counts = {'session123': 3600}
    service.max_token_budget = 4000
    service._get_rolling_window_token_count = AsyncMock(return_value=3600)
    return service


@pytest.fixture
def mock_logger_service():
    """Mock logger service."""
    service = AsyncMock()
    service.log_conversation = AsyncMock()
    return service


@pytest.fixture
def mock_audio_service():
    """Mock audio service."""
    service = AsyncMock()
    service.text_to_speech = AsyncMock(return_value=b'fake_audio_data')
    service.initialize = AsyncMock()
    return service
