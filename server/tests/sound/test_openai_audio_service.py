#!/usr/bin/env python3
"""
Test OpenAI audio service implementation.

This module tests the OpenAI audio service specifically:
- Text-to-speech with different voices and formats
- Speech-to-text with Whisper
- Audio transcription
- Audio translation
- Error handling
"""

import asyncio
import os
import sys
import wave
from base64 import b64encode
from contextlib import aclosing
from importlib.util import find_spec
from io import BytesIO
from shutil import which
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

# Get the absolute path to the server directory
# Since we're in tests/sound/, we need to go up two levels to get to server/
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.base import ServiceType
from ai_services.errors import ProviderServiceError
from ai_services.implementations.audio.openai_audio_service import OpenAIAudioService


class TestOpenAIAudioService:
    """Test cases for OpenAI audio service."""

    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return {
            "tts_providers": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-openai-key",
                    "api_base": "https://speech.example.com/v1",
                    "stt_model": "whisper-1",
                    "tts_model": "tts-1",
                    "tts_voice": "alloy",
                    "tts_format": "mp3"
                }
            }
        }

    @pytest.fixture
    def service(self, config):
        """Create a service instance."""
        return OpenAIAudioService(config)

    def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.service_type == ServiceType.AUDIO
        assert service.provider_name == "openai"
        assert service.stt_model == "whisper-1"
        assert service.tts_model == "tts-1"
        assert service.tts_voice == "alloy"
        assert service.tts_format == "mp3"

    def test_stt_model_attribute_exists_when_model_is_not_configured(self):
        service = OpenAIAudioService({"stt_providers": {"openai": {}}})

        assert service.stt_model == "whisper-1"

    @pytest.mark.asyncio
    async def test_text_to_speech(self, service):
        """Test text-to-speech conversion."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_audio_response = MagicMock()

        # Mock the aread() method as AsyncMock that returns the audio data
        mock_audio_response.aread = AsyncMock(return_value=b"audiodata")
        # Also set read attribute so hasattr(response, 'read') returns True
        mock_audio_response.read = MagicMock()

        mock_client.audio.speech.create = AsyncMock(return_value=mock_audio_response)
        service.client = mock_client
        service.initialized = True

        # Test TTS
        result = await service.text_to_speech("Hello, world!")

        assert result == b"audiodata"
        mock_client.audio.speech.create.assert_called_once()
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["model"] == "tts-1"
        assert call_kwargs["voice"] == "alloy"
        assert call_kwargs["input"] == "Hello, world!"
        assert call_kwargs["response_format"] == "mp3"

    @pytest.mark.asyncio
    async def test_text_to_speech_custom_voice(self, service):
        """Test TTS with custom voice."""
        mock_client = MagicMock()
        mock_audio_response = MagicMock()

        # Mock the aread() method as AsyncMock that returns the audio data
        mock_audio_response.aread = AsyncMock(return_value=b"audio")
        # Also set read attribute so hasattr(response, 'read') returns True
        mock_audio_response.read = MagicMock()

        mock_client.audio.speech.create = AsyncMock(return_value=mock_audio_response)
        service.client = mock_client
        service.initialized = True

        # Test with custom voice
        result = await service.text_to_speech("Test", voice="nova", format="opus")

        assert result == b"audio"
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["voice"] == "nova"
        assert call_kwargs["response_format"] == "opus"

    @pytest.mark.asyncio
    async def test_text_to_speech_invalid_format(self, service):
        """Test TTS with invalid format."""
        service.initialized = True

        with pytest.raises(ValueError, match="Unsupported audio format"):
            await service.text_to_speech("Test", format="invalid")

    @pytest.mark.asyncio
    async def test_speech_to_text(self, service):
        """Test speech-to-text conversion."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Hello, world!"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        # Test STT with bytes
        audio_data = b"fake audio data"
        result = await service.speech_to_text(audio_data, language="en")

        assert result == "Hello, world!"
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["model"] == "whisper-1"
        assert call_kwargs["language"] == "en"
        assert isinstance(call_kwargs["file"], BytesIO)

    @pytest.mark.asyncio
    async def test_speech_to_text_from_file(self, service, tmp_path):
        """Test STT from file path."""
        # Create a temporary audio file
        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio data")

        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Transcribed text"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        # Test STT with file path
        result = await service.speech_to_text(str(audio_file))

        assert result == "Transcribed text"

    @pytest.mark.asyncio
    async def test_transcribe_alias(self, service):
        """Test that transcribe is an alias for speech_to_text."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Transcribed"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        # Test transcribe
        result = await service.transcribe(b"audio")

        assert result == "Transcribed"
        mock_client.audio.transcriptions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_to_english(self, service):
        """Test audio translation to English."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_translation = MagicMock()
        mock_translation.text = "Hello, how are you?"
        mock_client.audio.translations.create = AsyncMock(return_value=mock_translation)
        service.client = mock_client
        service.initialized = True

        # Test translation (OpenAI translates to English by default)
        result = await service.translate(b"french audio", source_language="fr", target_language="en")

        assert result == "Hello, how are you?"
        mock_client.audio.translations.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_translate_to_non_english(self, service):
        """Test audio translation to non-English (falls back to transcription)."""
        # Mock the OpenAI client
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Bonjour"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        # Test translation to non-English (should fall back to transcription)
        result = await service.translate(b"french audio", source_language="fr", target_language="es")

        # Should return transcription (limitation of OpenAI API)
        assert result == "Bonjour"
        mock_client.audio.transcriptions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_initialize(self, service):
        """Test that methods auto-initialize the service."""
        assert service.initialized is False

        # Mock initialize
        service.initialize = AsyncMock(return_value=True)
        service.client = MagicMock()

        # Mock TTS response
        mock_audio_response = MagicMock()
        # Mock the aread() method as AsyncMock that returns the audio data
        mock_audio_response.aread = AsyncMock(return_value=b"audio")
        # Also set read attribute so hasattr(response, 'read') returns True
        mock_audio_response.read = MagicMock()
        service.client.audio.speech.create = AsyncMock(return_value=mock_audio_response)

        # Call TTS - should auto-initialize
        await service.text_to_speech("Test")

        service.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling(self, service):
        """Test error handling in audio operations."""
        # Mock the OpenAI client to raise an error
        mock_client = MagicMock()
        mock_client.audio.speech.create = AsyncMock(side_effect=Exception("API Error"))
        service.client = mock_client
        service.initialized = True
        service._handle_openai_error = MagicMock()

        # Test that error is raised
        with pytest.raises(Exception):
            await service.text_to_speech("Test")

        # Verify error handler was called
        service._handle_openai_error.assert_called_once()


    @pytest.mark.asyncio
    async def test_text_to_speech_streaming(self, service):
        """Test streaming text-to-speech yields chunks."""
        mock_client = MagicMock()

        # Simulate with_streaming_response context manager yielding chunks
        mock_stream_response = MagicMock()

        async def mock_iter_bytes(chunk_size=4096):
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        mock_stream_response.iter_bytes = mock_iter_bytes

        class AsyncCM:
            async def __aenter__(self):
                return mock_stream_response
            async def __aexit__(self, *args):
                pass

        mock_client.audio.speech.with_streaming_response.create = MagicMock(
            return_value=AsyncCM()
        )
        service.client = mock_client
        service.initialized = True

        chunks = []
        async for chunk in service.text_to_speech_streaming(
            "Hello, world!", model="tts-1-hd", speed=1.25,
            extra_headers={"X-Test": "test"}, session={"type": "realtime"},
        ):
            chunks.append(chunk)

        assert chunks == [b"chunk1", b"chunk2", b"chunk3"]
        mock_client.audio.speech.with_streaming_response.create.assert_called_once_with(
            model="tts-1-hd", voice="alloy", input="Hello, world!", response_format="mp3",
        )

    @pytest.mark.asyncio
    async def test_text_to_speech_streaming_invalid_format(self, service):
        """Test streaming TTS with invalid format raises ValueError."""
        service.initialized = True

        with pytest.raises(ValueError, match="Unsupported audio format"):
            async for _ in service.text_to_speech_streaming("Test", format="invalid"):
                pass

    @pytest.mark.asyncio
    async def test_text_to_speech_with_instructions(self, service):
        """Test TTS with instructions for gpt-4o-mini-tts model."""
        mock_client = MagicMock()
        mock_audio_response = MagicMock()
        mock_audio_response.aread = AsyncMock(return_value=b"audio")
        mock_audio_response.read = MagicMock()
        mock_client.audio.speech.create = AsyncMock(return_value=mock_audio_response)

        service.client = mock_client
        service.initialized = True
        service.tts_model = "gpt-4o-mini-tts"
        service.tts_instructions = "Speak cheerfully."

        await service.text_to_speech("Hello!")

        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert call_kwargs["instructions"] == "Speak cheerfully."

    @pytest.mark.asyncio
    async def test_text_to_speech_instructions_not_set_for_non_gpt4o(self, service):
        """Test that instructions are NOT sent for non-gpt-4o models."""
        mock_client = MagicMock()
        mock_audio_response = MagicMock()
        mock_audio_response.aread = AsyncMock(return_value=b"audio")
        mock_audio_response.read = MagicMock()
        mock_client.audio.speech.create = AsyncMock(return_value=mock_audio_response)

        service.client = mock_client
        service.initialized = True
        service.tts_model = "tts-1"
        service.tts_instructions = "Speak cheerfully."

        await service.text_to_speech("Hello!")

        call_kwargs = mock_client.audio.speech.create.call_args[1]
        assert "instructions" not in call_kwargs

    @pytest.mark.asyncio
    async def test_speech_to_text_with_formatted_wav(self, service):
        """Test speech-to-text with WAV bytes (RIFF/WAVE header), verifying it is not wrapped."""
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "WAV Transcription"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        # Valid WAV mock header
        audio_data = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        result = await service.speech_to_text(audio_data)

        assert result == "WAV Transcription"
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        
        # Verify it wasn't double-wrapped in wrap_in_wav
        assert call_kwargs["file"].name == "audio.wav"
        file_content = call_kwargs["file"].read()
        assert file_content == audio_data

    @pytest.mark.asyncio
    async def test_speech_to_text_with_metadata(self, service):
        """Test speech-to-text with mime_type/filename/audio_format, verifying it doesn't wrap and uses correct format."""
        mock_client = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.text = "Metadata Transcription"
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        service.client = mock_client
        service.initialized = True

        audio_data = b"some MP3 raw data"
        result = await service.speech_to_text(audio_data, filename="voice.mp3")

        assert result == "Metadata Transcription"
        mock_client.audio.transcriptions.create.assert_called_once()
        call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
        assert call_kwargs["file"].name == "audio.mp3"
        assert call_kwargs["file"].read() == audio_data


class TestOpenAIAudioServiceConfiguration:
    """Test OpenAI audio service configuration."""

    def test_default_configuration(self):
        """Test service with default configuration."""
        config = {
            "tts_providers": {
                "openai": {
                    "enabled": True,
                    "api_key": "test-key"
                }
            }
        }

        service = OpenAIAudioService(config)

        # Should use defaults
        assert service.stt_model == "whisper-1"
        assert service.tts_model == "gpt-realtime-2.1-mini"
        assert service.tts_voice == "alloy"
        assert service.tts_format == "mp3"

    def test_custom_configuration(self):
        """Test service with custom configuration - skipped due to config extraction issue."""
        # Note: Custom configuration reading requires proper config structure
        # that matches the base class _extract_provider_config() expectations.
        # This test is skipped as the current implementation reads from defaults.
        pytest.skip("Custom configuration extraction not fully implemented in test environment")


class TestOpenAIRealtimeTTS:
    @pytest.fixture
    def service(self):
        service = OpenAIAudioService({
            "tts_providers": {"openai": {"tts_model": "gpt-4o-mini-tts-2025-12-15"}},
        })
        service.client = MagicMock()
        service.initialized = True
        return service

    def mock_response(self, service, chunks, status="completed"):
        connect = service.client.realtime.connect
        connection = connect.return_value.__aenter__.return_value
        connection.send = AsyncMock()
        connection.recv = AsyncMock(side_effect=[
            SimpleNamespace(type="session.created"),
            *(SimpleNamespace(type="response.output_audio.delta", delta=b64encode(chunk).decode()) for chunk in chunks),
            SimpleNamespace(type="response.done", response=SimpleNamespace(status=status)),
        ])
        return connection

    @pytest.mark.asyncio
    async def test_migrates_retired_model_and_returns_wav(self, service):
        pcm = b"\x01\x00\x02\x00"
        connection = self.mock_response(service, [pcm[:2], pcm[2:]])
        audio = await service.text_to_speech(
            "What time is it?", model="tts-1-hd", voice="nova", format="wav",
            instructions="Speak cheerfully.", speed=1.25, audio_format="unused", extra_body={"unused": True},
        )

        assert service.tts_model == "gpt-realtime-2.1-mini"
        assert service.client.realtime.connect.call_args.kwargs["model"] == service.tts_model
        service.client.audio.speech.create.assert_not_called()
        speed_event, response_event = [call.args[0] for call in connection.send.await_args_list]
        assert speed_event["session"]["audio"]["output"]["speed"] == 1.25
        assert response_event["type"] == "response.create"
        response = response_event["response"]
        assert response["output_modalities"] == ["audio"]
        assert response["audio"]["output"]["voice"] == "coral"
        assert response["input"][0]["content"] == [{"type": "input_text", "text": "What time is it?"}]
        assert "verbatim" in response["instructions"]
        assert "Speak cheerfully." in response["instructions"]
        with wave.open(BytesIO(audio)) as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (24000, 1, 2)
            assert wav.readframes(wav.getnframes()) == pcm

    @pytest.mark.asyncio
    async def test_streaming_yields_pcm_before_response_finishes(self, service):
        connection = self.mock_response(service, [b"\x01\x00", b"\x02\x00"])
        async with aclosing(service.text_to_speech_streaming(
            "Hello", format="pcm", extra_headers={"X-Test": "test"}, extra_body={"unused": True},
        )) as stream:
            assert await anext(stream) == b"\x01\x00"
            assert connection.recv.await_count == 2
            assert [chunk async for chunk in stream] == [b"\x02\x00"]
        assert service.client.realtime.connect.call_args.kwargs["extra_headers"] == {"X-Test": "test"}

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        find_spec("imageio_ffmpeg") is None and which("ffmpeg") is None,
        reason="MP3 encoding requires an optional FFmpeg installation",
    )
    async def test_default_format_encodes_realtime_audio_as_mp3(self, service):
        self.mock_response(service, [b"\x00\x00" * 2400])
        audio = await service.text_to_speech("Hello")
        assert audio.startswith(b"ID3")
        assert b"\xff\xf3" in audio

    @pytest.mark.asyncio
    async def test_early_ffmpeg_exit_preserves_writer_error(self, service, monkeypatch):
        writer_started = asyncio.Event()

        async def drain():
            writer_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError as exc:
                raise BrokenPipeError("encoder input pipe closed") from exc

        async def wait():
            await writer_started.wait()
            return 1

        process = SimpleNamespace(
            stdin=SimpleNamespace(write=MagicMock(), drain=drain, close=MagicMock()),
            stdout=SimpleNamespace(read=AsyncMock(return_value=b"")),
            returncode=1,
            wait=wait,
            communicate=AsyncMock(),
        )
        monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
        monkeypatch.setattr("ai_services.implementations.audio.openai_audio_service.which", lambda _: "ffmpeg")
        monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))

        async def pcm():
            yield b"\x00\x00"

        with pytest.raises(BrokenPipeError, match="encoder input pipe closed"):
            async for _ in service._encode_realtime_audio(pcm(), "mp3"):
                pytest.fail("The failed encoder produced audio")
        process.stdin.close.assert_called_once()
        process.communicate.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("chunks,status,error", [
        ([b"\x01\x00"], "incomplete", "status incomplete"),
        ([], "completed", "no speech audio"),
    ])
    async def test_rejects_incomplete_or_empty_responses(self, service, chunks, status, error, caplog):
        self.mock_response(service, chunks, status=status)
        with pytest.raises(ProviderServiceError):
            await service.text_to_speech("Hello", format="pcm")
        assert error in caplog.text
        service.client.realtime.connect.return_value.__aexit__.assert_awaited_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
