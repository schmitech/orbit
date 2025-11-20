"""
Tests for ResponseProcessor.
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.response_processor import ResponseProcessor
from services.chat_handlers.conversation_history_handler import ConversationHistoryHandler


class TestResponseProcessor:
    """Test suite for ResponseProcessor."""

    @pytest.fixture
    def mock_conversation_handler(self):
        """Mock conversation history handler."""
        handler = AsyncMock(spec=ConversationHistoryHandler)
        handler.check_limit_warning = AsyncMock(return_value=None)
        # store_turn now returns (user_msg_id, assistant_msg_id)
        handler.store_turn = AsyncMock(return_value=("user_msg_123", "assistant_msg_456"))
        return handler

    def test_initialization(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test processor initialization."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        assert processor.config == base_config
        assert processor.conversation_handler == mock_conversation_handler
        assert processor.logger_service == mock_logger_service

    def test_format_response(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test response formatting."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Test with text that needs formatting
        response = "Hello  world\n\nMultiple  spaces"
        result = processor.format_response(response)

        # Should clean up formatting issues
        assert isinstance(result, str)
        assert "Hello" in result
        assert "world" in result

    def test_inject_warning_with_warning(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test warning injection when warning provided."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        response = "Original response"
        warning = "This is a warning"

        result = processor.inject_warning(response, warning)

        assert "Original response" in result
        assert "This is a warning" in result
        assert "---" in result

    def test_inject_warning_without_warning(self, base_config, mock_conversation_handler, mock_logger_service):
        """Test warning injection when no warning."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        response = "Original response"

        result = processor.inject_warning(response, None)

        assert result == "Original response"

    @pytest.mark.asyncio
    async def test_log_request_details(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test request details logging."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Should not raise any exceptions
        await processor.log_request_details(
            message="Test message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            system_prompt_id="prompt123",
            api_key="sk-1234567890abcdef",
            session_id="session123",
            user_id="user456"
        )

    @pytest.mark.asyncio
    async def test_log_conversation_success(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test successful conversation logging."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        await processor.log_conversation(
            query="User query",
            response="Assistant response",
            client_ip="127.0.0.1",
            backend="openai",
            api_key="key123",
            session_id="session456",
            user_id="user789"
        )

        mock_logger_service.log_conversation.assert_called_once_with(
            query="User query",
            response="Assistant response",
            ip="127.0.0.1",
            backend="openai",
            blocked=False,
            api_key="key123",
            session_id="session456",
            user_id="user789"
        )

    @pytest.mark.asyncio
    async def test_log_conversation_handles_error(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test that logging errors are handled gracefully."""
        mock_logger_service.log_conversation.side_effect = Exception("Logging failed")

        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # Should not raise exception
        await processor.log_conversation(
            query="User query",
            response="Assistant response",
            client_ip="127.0.0.1",
            backend="openai"
        )

    @pytest.mark.asyncio
    async def test_process_response_complete_flow(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test complete response processing flow."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        # process_response now returns (processed_response, assistant_message_id)
        processed_response, assistant_message_id = await processor.process_response(
            response="This is the response",
            message="User message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id="session123",
            user_id="user456",
            api_key="key789",
            backend="openai",
            processing_time=1.5
        )

        # Check that response is formatted
        assert "This is the response" in processed_response
        # Check that assistant_message_id is returned
        assert assistant_message_id == "assistant_msg_456"

        # Check that conversation was stored
        mock_conversation_handler.store_turn.assert_called_once()
        call_args = mock_conversation_handler.store_turn.call_args
        assert call_args[1]['session_id'] == "session123"
        assert call_args[1]['user_message'] == "User message"
        assert call_args[1]['adapter_name'] == "test_adapter"

        # Check that conversation was logged
        mock_logger_service.log_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_response_with_warning(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test response processing with warning injection."""
        mock_conversation_handler.check_limit_warning.return_value = "Warning message"

        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        processed_response, assistant_message_id = await processor.process_response(
            response="Original response",
            message="User message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id="session123",
            user_id=None,
            api_key=None,
            backend="openai",
            processing_time=1.0
        )

        assert "Original response" in processed_response
        assert "Warning message" in processed_response
        assert assistant_message_id == "assistant_msg_456"

    @pytest.mark.asyncio
    async def test_process_response_without_session(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test response processing without session ID."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        processed_response, assistant_message_id = await processor.process_response(
            response="Response",
            message="Message",
            client_ip="127.0.0.1",
            adapter_name="test_adapter",
            session_id=None,  # No session
            user_id=None,
            api_key=None,
            backend="openai",
            processing_time=1.0
        )

        # Should not store conversation turn (no session)
        mock_conversation_handler.store_turn.assert_not_called()

        # assistant_message_id should be None when no session
        assert assistant_message_id is None

        # But should still log
        mock_logger_service.log_conversation.assert_called_once()

    def test_build_result_basic(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building basic result dictionary."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[{"title": "Source 1"}],
            metadata={"key": "value"},
            processing_time=1.5
        )

        assert result["response"] == "Test response"
        assert result["sources"] == [{"title": "Source 1"}]
        assert result["metadata"]["key"] == "value"
        assert result["metadata"]["processing_time"] == 1.5
        assert result["metadata"]["pipeline_used"] is True

    def test_build_result_with_audio(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building result with audio data."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[],
            metadata={},
            processing_time=1.0,
            audio_data=b'test_audio_data',
            audio_format='mp3'
        )

        assert "audio" in result
        assert result["audio_format"] == "mp3"
        # Should be base64 encoded
        import base64
        decoded = base64.b64decode(result["audio"])
        assert decoded == b'test_audio_data'

    def test_build_result_without_audio(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test building result without audio data."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test response",
            sources=[],
            metadata={},
            processing_time=1.0,
            audio_data=None,
            audio_format=None
        )

        assert "audio" not in result
        assert "audio_format" not in result

    def test_build_result_preserves_metadata(
        self, base_config, mock_conversation_handler, mock_logger_service
    ):
        """Test that existing metadata is preserved."""
        processor = ResponseProcessor(
            config=base_config,
            conversation_handler=mock_conversation_handler,
            logger_service=mock_logger_service
        )

        result = processor.build_result(
            response="Test",
            sources=[],
            metadata={"existing_key": "existing_value", "another": 123},
            processing_time=2.0
        )

        assert result["metadata"]["existing_key"] == "existing_value"
        assert result["metadata"]["another"] == 123
        assert result["metadata"]["processing_time"] == 2.0
        assert result["metadata"]["pipeline_used"] is True
