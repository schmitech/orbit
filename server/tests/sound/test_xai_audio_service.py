#!/usr/bin/env python3
"""
Test xAI audio service implementation.

This module tests the xAI/Grok speech-to-text provider:
- Audio service registration
- Multipart STT request construction
- URL-based transcription
- Raw audio validation
- Unsupported TTS/translation operations
"""

import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(server_dir)

from ai_services.base import ServiceType
from ai_services.factory import AIServiceFactory
from ai_services.implementations.audio.xai_audio_service import XAIAudioService
from ai_services.registry import register_audio_services


def _response(
    status_code: int = 200,
    json: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=json or {"text": "Hello from Grok"},
        request=httpx.Request("POST", "https://api.x.ai/v1/stt"),
    )


def _field_values(parts: List[Tuple[str, Any]], name: str) -> List[str]:
    return [part[1][1] for part in parts if part[0] == name and part[1][0] is None]


class TestXAIAudioRegistration:
    @pytest.fixture(autouse=True)
    def reset_factory(self):
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        import ai_services.registry as registry_module

        registry_module._services_registered = False
        yield
        AIServiceFactory._service_registry = {}
        AIServiceFactory._service_cache = {}
        registry_module._services_registered = False

    def test_register_xai_audio_provider(self):
        config: Dict[str, Any] = {
            "tts": {"enabled": False},
            "stt": {"enabled": True},
            "tts_providers": {"xai": {"enabled": False}},
            "stt_providers": {
                "xai": {
                    "enabled": True,
                    "api_key": "test-key",
                    "stt_model": "grok-stt",
                }
            },
        }

        real_import = __import__
        with patch("builtins.__import__") as mock_import:
            mock_module = MagicMock()
            mock_module.XAIAudioService = MagicMock()

            def side_effect(name, *args, **kwargs):
                if "ai_services.implementations.audio" in name:
                    return mock_module
                return real_import(name, *args, **kwargs)

            mock_import.side_effect = side_effect
            register_audio_services(config)

        available_services = AIServiceFactory.list_available_services()
        assert "xai" in available_services.get("audio", [])


class TestXAIAudioService:
    @pytest.fixture
    def config(self):
        return {
            "stt_providers": {
                "xai": {
                    "enabled": True,
                    "api_key": "test-key",
                    "api_base": "https://api.x.ai/v1",
                    "stt_model": "grok-stt",
                    "retry": {"enabled": False},
                }
            }
        }

    @pytest.fixture
    def service(self, config):
        return XAIAudioService(config)

    def test_service_initialization(self, service):
        assert service.service_type == ServiceType.AUDIO
        assert service.provider_name == "xai"
        assert service.base_url == "https://api.x.ai/v1"
        assert service.endpoint == "/stt"
        assert service.stt_model == "grok-stt"

    @pytest.mark.asyncio
    async def test_speech_to_text_multipart_file_last(self, service):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_response(json={"text": "Transcribed"}))
        service.client = mock_client
        service.initialized = True

        wav_data = (
            b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
            b"\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        )

        result = await service.speech_to_text(
            wav_data,
            language="en-US",
            filename="voice.wav",
            format_text=True,
            diarize=True,
            keyterms=["Orbit", "Grok"],
        )

        assert result == "Transcribed"
        mock_client.post.assert_called_once()

        call_kwargs = mock_client.post.call_args.kwargs
        parts = call_kwargs["files"]
        assert parts[-1][0] == "file"
        assert parts[-1][1][0] == "voice.wav"
        assert parts[-1][1][1] == wav_data
        assert parts[-1][1][2] == "audio/wav"
        assert _field_values(parts, "language") == ["en"]
        assert _field_values(parts, "format") == ["true"]
        assert _field_values(parts, "diarize") == ["true"]
        assert _field_values(parts, "keyterm") == ["Orbit", "Grok"]

    @pytest.mark.asyncio
    async def test_speech_to_text_url_request(self, service):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_response(json={"text": "URL transcript"}))
        service.client = mock_client
        service.initialized = True

        result = await service.speech_to_text(
            "https://example.com/audio.mp3",
            language="en",
        )

        assert result == "URL transcript"
        parts = mock_client.post.call_args.kwargs["files"]
        assert "file" not in [part[0] for part in parts]
        assert _field_values(parts, "url") == ["https://example.com/audio.mp3"]

    @pytest.mark.asyncio
    async def test_speech_to_text_raw_audio_requires_sample_rate(self, service):
        service.client = MagicMock()
        service.initialized = True

        with pytest.raises(ValueError, match="raw audio requires sample_rate"):
            await service.speech_to_text(b"\x00\x00", audio_format="pcm")

    @pytest.mark.asyncio
    async def test_speech_to_text_raw_audio_sends_format_and_sample_rate(self, service):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_response(json={"text": "Raw transcript"}))
        service.client = mock_client
        service.initialized = True

        result = await service.speech_to_text(
            b"\x00\x00\x01\x00",
            audio_format="pcm",
            sample_rate=16000,
        )

        assert result == "Raw transcript"
        parts = mock_client.post.call_args.kwargs["files"]
        assert _field_values(parts, "audio_format") == ["pcm"]
        assert _field_values(parts, "sample_rate") == ["16000"]
        assert parts[-1][0] == "file"
        assert parts[-1][1][0] == "audio.pcm"

    @pytest.mark.asyncio
    async def test_format_text_requires_language(self, service):
        service.client = MagicMock()
        service.initialized = True

        with pytest.raises(ValueError, match="format=true requires a language"):
            await service.speech_to_text(b"audio", format_text=True)

    @pytest.mark.asyncio
    async def test_transcribe_alias(self, service):
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_response(json={"text": "Alias"}))
        service.client = mock_client
        service.initialized = True

        result = await service.transcribe(b"audio", format="wav")

        assert result == "Alias"

    @pytest.mark.asyncio
    async def test_unsupported_text_to_speech(self, service):
        with pytest.raises(NotImplementedError, match="speech-to-text only"):
            await service.text_to_speech("Hello")

    @pytest.mark.asyncio
    async def test_unsupported_translation(self, service):
        with pytest.raises(NotImplementedError, match="transcription only"):
            await service.translate(b"audio")
