"""
Tests for ConversationHistoryHandler.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler


class TestConversationHistoryHandler:
    """Test suite for ConversationHistoryHandler."""

    def test_initialization(self, base_config, mock_adapter_manager, mock_chat_history_service):
        """Test handler initialization with valid config."""
        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager,
            verbose=True
        )

        assert handler._base_enabled is True
        assert handler.verbose is True
        assert handler.chat_history_service == mock_chat_history_service
        assert handler.adapter_manager == mock_adapter_manager

    def test_initialization_disabled(self, base_config):
        """Test handler when chat history is disabled in config."""
        base_config['chat_history']['enabled'] = False
        handler = ConversationHistoryHandler(config=base_config)

        assert handler._base_enabled is False

    def test_should_enable_for_passthrough_adapter(self, base_config, mock_adapter_manager):
        """Test that chat history is enabled for passthrough adapters."""
        handler = ConversationHistoryHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        assert handler.should_enable('test_adapter') is True

    def test_should_disable_for_non_passthrough_adapter(self, base_config, mock_adapter_manager):
        """Test that chat history is disabled for non-passthrough adapters."""
        mock_adapter_manager.get_adapter_config.return_value = {
            'type': 'rag',  # Not passthrough
            'inference_provider': 'openai'
        }

        handler = ConversationHistoryHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        assert handler.should_enable('rag_adapter') is False

    def test_should_disable_when_base_disabled(self, base_config, mock_adapter_manager):
        """Test that chat history is disabled when base config is disabled."""
        base_config['chat_history']['enabled'] = False

        handler = ConversationHistoryHandler(
            config=base_config,
            adapter_manager=mock_adapter_manager
        )

        assert handler.should_enable('test_adapter') is False

    def test_should_disable_when_no_adapter_manager(self, base_config):
        """Test that chat history is disabled when no adapter manager."""
        handler = ConversationHistoryHandler(config=base_config)

        assert handler.should_enable('test_adapter') is False

    @pytest.mark.asyncio
    async def test_get_context_returns_messages(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test getting conversation context returns messages."""
        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager,
            verbose=True
        )

        context = await handler.get_context('session123', 'test_adapter')

        assert len(context) == 2
        assert context[0]['role'] == 'user'
        assert context[1]['role'] == 'assistant'
        mock_chat_history_service.get_context_messages.assert_awaited_once_with('session123')

    @pytest.mark.asyncio
    async def test_get_context_returns_empty_when_disabled(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that empty list is returned when history is disabled."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'rag'}

        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        context = await handler.get_context('session123', 'rag_adapter')

        assert context == []
        mock_chat_history_service.get_context_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_context_returns_empty_on_error(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that empty list is returned on error."""
        mock_chat_history_service.get_context_messages.side_effect = Exception("DB error")

        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        context = await handler.get_context('session123', 'test_adapter')

        assert context == []

    @pytest.mark.asyncio
    async def test_store_turn_success(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test storing conversation turn successfully."""
        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager,
            verbose=True
        )

        await handler.store_turn(
            session_id='session123',
            user_message='Hello',
            assistant_response='Hi there!',
            adapter_name='test_adapter',
            user_id='user1',
            api_key='key123',
            metadata={'extra': 'data'}
        )

        mock_chat_history_service.add_conversation_turn.assert_called_once_with(
            session_id='session123',
            user_message='Hello',
            assistant_response='Hi there!',
            user_id='user1',
            api_key='key123',
            metadata={'extra': 'data'}
        )

    @pytest.mark.asyncio
    async def test_store_turn_skipped_when_disabled(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that store_turn is skipped when history is disabled."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'rag'}

        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        await handler.store_turn(
            session_id='session123',
            user_message='Hello',
            assistant_response='Hi there!',
            adapter_name='rag_adapter'
        )

        mock_chat_history_service.add_conversation_turn.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_limit_warning_returns_warning(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that warning is returned when approaching limit."""
        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        warning = await handler.check_limit_warning('session123', 'test_adapter')

        assert warning is not None
        assert '3600' in warning  # current_tokens
        assert '4000' in warning  # max_tokens
        assert 'Warning' in warning

    @pytest.mark.asyncio
    async def test_check_limit_warning_returns_none_when_not_approaching(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that no warning is returned when not approaching limit."""
        mock_chat_history_service._session_token_counts = {'session123': 500}
        mock_chat_history_service._get_session_token_count.return_value = 500

        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        warning = await handler.check_limit_warning('session123', 'test_adapter')

        assert warning is None

    @pytest.mark.asyncio
    async def test_check_limit_warning_returns_none_when_disabled(
        self, base_config, mock_adapter_manager, mock_chat_history_service
    ):
        """Test that no warning is returned when history is disabled."""
        mock_adapter_manager.get_adapter_config.return_value = {'type': 'rag'}

        handler = ConversationHistoryHandler(
            config=base_config,
            chat_history_service=mock_chat_history_service,
            adapter_manager=mock_adapter_manager
        )

        warning = await handler.check_limit_warning('session123', 'rag_adapter')

        assert warning is None
