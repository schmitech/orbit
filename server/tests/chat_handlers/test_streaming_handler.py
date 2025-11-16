"""
Tests for StreamingHandler.
"""

import pytest
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# Add the server directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.chat_handlers.streaming_handler import StreamingHandler, StreamingState
from services.chat_handlers.audio_handler import AudioHandler


class TestStreamingState:
    """Test suite for StreamingState."""

    def test_initialization_without_audio(self):
        """Test state initialization without audio."""
        state = StreamingState(return_audio=False)

        assert state.accumulated_text == ""
        assert state.sources == []
        assert state.stream_completed is False
        assert state.first_chunk_yielded is False
        assert state.chunk_count == 0
        assert state.sentence_detector is None
        assert state.audio_chunks_sent == 0
        assert state.return_audio is False

    def test_initialization_with_audio(self):
        """Test state initialization with audio enabled."""
        state = StreamingState(return_audio=True)

        assert state.sentence_detector is not None
        assert state.return_audio is True


class TestStreamingHandler:
    """Test suite for StreamingHandler."""

    @pytest.fixture
    def mock_audio_handler(self):
        """Mock audio handler."""
        handler = AsyncMock(spec=AudioHandler)
        handler.generate_audio = AsyncMock(return_value=(b'audio_data', 'mp3'))
        return handler

    def test_initialization(self, base_config, mock_audio_handler):
        """Test handler initialization."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler,
            verbose=True
        )

        assert handler.audio_handler == mock_audio_handler
        assert handler.verbose is True
        assert handler.audio_timeout == 45.0

    @pytest.mark.asyncio
    async def test_generate_sentence_audio_success(self, base_config, mock_audio_handler):
        """Test successful sentence audio generation."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        result = await handler._generate_sentence_audio(
            sentence="Hello world.",
            adapter_name="test_adapter",
            tts_voice="alloy",
            language="en",
            chunk_index=0
        )

        assert result is not None
        assert "audio_chunk" in result
        assert result["audioFormat"] == "mp3"
        assert result["chunk_index"] == 0
        assert result["done"] is False

    @pytest.mark.asyncio
    async def test_generate_sentence_audio_timeout(self, base_config, mock_audio_handler):
        """Test audio generation timeout."""
        import asyncio

        async def slow_audio(*args, **kwargs):
            await asyncio.sleep(10)  # Longer than timeout
            return b'audio', 'mp3'

        mock_audio_handler.generate_audio = slow_audio

        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )
        handler.audio_timeout = 0.01  # Very short timeout

        result = await handler._generate_sentence_audio(
            sentence="Hello world.",
            adapter_name="test_adapter",
            tts_voice="alloy",
            language="en",
            chunk_index=0
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_process_stream_text_only(self, base_config, mock_audio_handler):
        """Test processing stream without audio."""

        async def mock_stream():
            yield json.dumps({"response": "Hello "})
            yield json.dumps({"response": "world!"})
            yield json.dumps({"done": True, "sources": [{"title": "Source 1"}]})

        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        chunks = []
        final_state = None
        async for chunk, state in handler.process_stream(
            pipeline_stream=mock_stream(),
            adapter_name="test_adapter",
            return_audio=False
        ):
            chunks.append(chunk)
            final_state = state

        # Should yield 2 text chunks (done is not yielded)
        assert len(chunks) == 2
        assert final_state.accumulated_text == "Hello world!"
        assert final_state.sources == [{"title": "Source 1"}]
        assert final_state.stream_completed is True

    @pytest.mark.asyncio
    async def test_process_stream_handles_errors(self, base_config, mock_audio_handler):
        """Test that errors in stream are handled."""

        async def mock_stream():
            yield json.dumps({"error": "Something went wrong"})

        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        chunks = []
        async for chunk, state in handler.process_stream(
            pipeline_stream=mock_stream(),
            adapter_name="test_adapter"
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "error" in chunks[0]

    @pytest.mark.asyncio
    async def test_process_stream_invalid_json(self, base_config, mock_audio_handler):
        """Test handling of invalid JSON chunks."""

        async def mock_stream():
            yield "not valid json"
            yield json.dumps({"response": "Valid"})
            yield json.dumps({"done": True})

        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        chunks = []
        final_state = None
        async for chunk, state in handler.process_stream(
            pipeline_stream=mock_stream(),
            adapter_name="test_adapter"
        ):
            chunks.append(chunk)
            final_state = state

        # Should still process valid chunks
        assert len(chunks) == 2  # Invalid chunk + valid chunk
        assert final_state.accumulated_text == "Valid"

    @pytest.mark.asyncio
    async def test_process_stream_with_audio(self, base_config, mock_audio_handler):
        """Test processing stream with audio generation."""

        async def mock_stream():
            yield json.dumps({"response": "Hello. "})
            yield json.dumps({"response": "World!"})
            yield json.dumps({"done": True})

        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        chunks = []
        final_state = None
        async for chunk, state in handler.process_stream(
            pipeline_stream=mock_stream(),
            adapter_name="test_adapter",
            tts_voice="alloy",
            return_audio=True
        ):
            chunks.append(chunk)
            final_state = state

        # Should have text chunks and audio chunks
        assert final_state.accumulated_text == "Hello. World!"
        assert final_state.audio_chunks_sent > 0

    @pytest.mark.asyncio
    async def test_generate_remaining_audio(self, base_config, mock_audio_handler):
        """Test generating audio for remaining text."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=True)
        state.audio_chunks_sent = 1
        # Add some text that doesn't form a complete sentence
        state.sentence_detector.add_text("Some remaining text")

        result = await handler.generate_remaining_audio(
            state=state,
            adapter_name="test_adapter",
            tts_voice="alloy",
            language="en"
        )

        assert result is not None
        assert "audio_chunk" in result
        assert state.audio_chunks_sent == 2

    @pytest.mark.asyncio
    async def test_generate_remaining_audio_no_remaining(self, base_config, mock_audio_handler):
        """Test generating remaining audio when no text remains."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=True)
        state.audio_chunks_sent = 1

        result = await handler.generate_remaining_audio(
            state=state,
            adapter_name="test_adapter"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_remaining_audio_no_streaming_audio(self, base_config, mock_audio_handler):
        """Test that None is returned when no streaming audio was sent."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=False)

        result = await handler.generate_remaining_audio(
            state=state,
            adapter_name="test_adapter"
        )

        assert result is None

    def test_build_done_chunk_basic(self, base_config, mock_audio_handler):
        """Test building basic done chunk."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=False)
        state.sources = [{"title": "Source 1"}]

        result = handler.build_done_chunk(state)

        data = json.loads(result.replace("data: ", "").strip())
        assert data["done"] is True
        assert data["sources"] == [{"title": "Source 1"}]

    def test_build_done_chunk_with_audio(self, base_config, mock_audio_handler):
        """Test building done chunk with audio data."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=False)

        result = handler.build_done_chunk(
            state=state,
            audio_data=b'test_audio',
            audio_format_str='mp3'
        )

        data = json.loads(result.replace("data: ", "").strip())
        assert data["done"] is True
        assert "audio" in data
        assert data["audioFormat"] == "mp3"

    def test_build_done_chunk_streaming_audio_no_embed(self, base_config, mock_audio_handler):
        """Test that audio is not embedded when streaming audio was used."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=True)
        state.audio_chunks_sent = 3

        result = handler.build_done_chunk(
            state=state,
            audio_data=b'test_audio',
            audio_format_str='mp3'
        )

        data = json.loads(result.replace("data: ", "").strip())
        assert data["done"] is True
        assert "audio" not in data
        assert data["total_audio_chunks"] == 3

    def test_build_done_chunk_format(self, base_config, mock_audio_handler):
        """Test that done chunk has correct SSE format."""
        handler = StreamingHandler(
            config=base_config,
            audio_handler=mock_audio_handler
        )

        state = StreamingState(return_audio=False)

        result = handler.build_done_chunk(state)

        assert result.startswith("data: ")
        assert result.endswith("\n\n")
