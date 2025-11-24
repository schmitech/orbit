"""
Audio Input Processor

Buffers incoming audio chunks from WebSocket and detects speech segments
using Voice Activity Detection (VAD) for real-time voice conversations.
"""

import logging
import asyncio
from typing import Optional, List, Tuple
from collections import deque
import time
import struct
from io import BytesIO
import wave

logger = logging.getLogger(__name__)


class AudioInputProcessor:
    """Processes incoming audio chunks and detects speech segments."""

    def __init__(
        self,
        audio_service,
        chunk_size_ms: int = 100,
        silence_threshold: float = 0.01,
        min_speech_duration_ms: int = 300,
        max_speech_duration_ms: int = 10000,
        silence_duration_ms: int = 500,
        sample_rate_hz: int = 24000,
        sample_width_bytes: int = 2,
        channels: int = 1
    ):
        """
        Initialize the audio input processor.

        Args:
            audio_service: Audio service for STT processing
            chunk_size_ms: Expected audio chunk size in milliseconds
            silence_threshold: Threshold for silence detection (not used for simple buffering)
            min_speech_duration_ms: Minimum speech duration to process
            max_speech_duration_ms: Maximum speech duration before forced processing
            silence_duration_ms: Duration of silence to trigger speech end detection
        """
        self.audio_service = audio_service
        self.chunk_size_ms = chunk_size_ms
        self.silence_threshold = silence_threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.max_speech_duration_ms = max_speech_duration_ms
        self.silence_duration_ms = silence_duration_ms
        self.sample_rate_hz = sample_rate_hz
        self.sample_width_bytes = sample_width_bytes
        self.channels = channels

        # Audio buffer
        self.audio_buffer: deque = deque()
        self.buffer_duration_ms = 0
        self.last_chunk_time = 0

        # State tracking
        self.is_processing = False
        self.speech_started = False
        self.consecutive_silence_chunks = 0

    def _is_silence(self, audio_chunk: bytes) -> bool:
        """
        Detect if an audio chunk is silence based on amplitude.

        Args:
            audio_chunk: Raw audio bytes (16-bit PCM)

        Returns:
            True if the chunk is silence, False otherwise
        """
        if not audio_chunk or len(audio_chunk) < 2:
            return True

        try:
            # Convert bytes to 16-bit integers
            # Assuming 16-bit PCM audio
            num_samples = len(audio_chunk) // 2
            samples = struct.unpack(f'{num_samples}h', audio_chunk)

            # Calculate RMS (root mean square) amplitude
            sum_squares = sum(sample * sample for sample in samples)
            rms = (sum_squares / num_samples) ** 0.5

            # Normalize to 0-1 range (16-bit audio max value is 32767)
            normalized_rms = rms / 32767.0

            # Check if below silence threshold
            is_silent = normalized_rms < self.silence_threshold

            # Only log on state transitions to reduce noise
            # (Could add a state variable to track previous state if needed)

            return is_silent

        except Exception as e:
            logger.warning(f"Error detecting silence: {e}")
            # If we can't determine, assume it's not silence
            return False

    def reset(self):
        """Reset the processor state."""
        self.audio_buffer.clear()
        self.buffer_duration_ms = 0
        self.last_chunk_time = 0
        self.is_processing = False
        self.speech_started = False
        self.consecutive_silence_chunks = 0
        logger.debug("Audio input processor reset")

    def _looks_like_wav(self, audio_data: bytes) -> bool:
        """Simple RIFF header check for WAV data."""
        return (
            isinstance(audio_data, (bytes, bytearray))
            and len(audio_data) > 12
            and audio_data[:4] == b"RIFF"
            and audio_data[8:12] == b"WAVE"
        )

    def _convert_pcm_to_wav(self, audio_data: bytes) -> bytes:
        """Wrap raw PCM bytes in a WAV container for STT models."""
        buffer = BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(self.sample_width_bytes)
            wav_file.setframerate(self.sample_rate_hz)
            wav_file.writeframes(audio_data)
        return buffer.getvalue()

    def _prepare_audio_bytes(self, audio_data: bytes, audio_format: str) -> bytes:
        """
        Ensure audio bytes are in a WAV container before handing to STT services.
        Most STT libraries expect WAV input even if the raw data is PCM.
        """
        fmt = (audio_format or "wav").lower()

        if fmt in {"pcm", "pcm_s16le", "raw"}:
            logger.debug("Wrapping raw PCM audio in WAV container for STT processing")
            return self._convert_pcm_to_wav(audio_data)

        if fmt == "wav" and not self._looks_like_wav(audio_data):
            logger.debug("Audio labeled as WAV but missing RIFF header; auto-wrapping PCM data")
            return self._convert_pcm_to_wav(audio_data)

        return audio_data

    def add_chunk(self, audio_chunk: bytes, chunk_duration_ms: Optional[int] = None) -> None:
        """
        Add an audio chunk to the buffer (only if it contains speech).

        Args:
            audio_chunk: Raw audio bytes
            chunk_duration_ms: Duration of the chunk in milliseconds (defaults to chunk_size_ms)
        """
        if not audio_chunk:
            return

        duration = chunk_duration_ms or self.chunk_size_ms
        self.last_chunk_time = time.time()

        # Check if this chunk is silence
        is_silent = self._is_silence(audio_chunk)

        if is_silent:
            # Track consecutive silence chunks
            self.consecutive_silence_chunks += 1

            # Log only when we first start detecting silence after speech
            if self.audio_buffer and self.consecutive_silence_chunks == 1:
                logger.debug(
                    f"Silence detected after speech (buffer has {self.buffer_duration_ms}ms)"
                )
        else:
            # This chunk contains speech - add it to buffer
            was_silent = self.consecutive_silence_chunks > 0
            self.consecutive_silence_chunks = 0
            self.audio_buffer.append(audio_chunk)
            self.buffer_duration_ms += duration
            self.speech_started = True

            # Log when speech starts or resumes
            if not self.audio_buffer or was_silent:
                logger.debug(f"Speech detected, buffering started")
            elif len(self.audio_buffer) % 10 == 0:  # Log every 10 chunks to reduce spam
                logger.debug(
                    f"Buffering speech: {self.buffer_duration_ms}ms "
                    f"({len(self.audio_buffer)} chunks)"
                )

    def should_process_buffer(self) -> bool:
        """
        Determine if the buffer should be processed for STT.

        Returns:
            True if buffer is ready for processing
        """
        if not self.audio_buffer:
            return False

        # Check if we've exceeded max speech duration
        if self.buffer_duration_ms >= self.max_speech_duration_ms:
            logger.info(
                f"Buffer ready: Max duration reached ({self.buffer_duration_ms}ms)"
            )
            return True

        # Check if we've received minimum speech duration and then enough silence
        if self.buffer_duration_ms >= self.min_speech_duration_ms:
            # Calculate silence duration based on consecutive silence chunks
            silence_ms = self.consecutive_silence_chunks * self.chunk_size_ms

            if silence_ms >= self.silence_duration_ms:
                logger.info(
                    f"Buffer ready: Speech complete "
                    f"(duration: {self.buffer_duration_ms}ms, "
                    f"silence: {silence_ms}ms, "
                    f"silence_chunks: {self.consecutive_silence_chunks})"
                )
                return True

        return False

    def get_buffered_audio(self) -> Optional[bytes]:
        """
        Get the complete buffered audio and reset the buffer.

        Returns:
            Combined audio bytes or None if buffer is empty
        """
        if not self.audio_buffer:
            return None

        # Combine all chunks
        audio_data = b''.join(self.audio_buffer)

        logger.info(
            f"Retrieved buffered audio: {len(audio_data)} bytes, "
            f"duration: {self.buffer_duration_ms}ms"
        )

        # Reset buffer
        self.audio_buffer.clear()
        self.buffer_duration_ms = 0
        self.speech_started = False
        self.consecutive_silence_chunks = 0

        return audio_data

    async def process_speech_to_text(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Process buffered audio through STT.

        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format (wav, mp3, opus, etc.)
            language: Language code for STT

        Returns:
            Transcribed text or None if processing fails
        """
        if not audio_data:
            return None

        self.is_processing = True

        try:
            logger.debug(
                f"Starting STT processing: {len(audio_data)} bytes, "
                f"format: {audio_format}"
            )

            # Ensure audio chunk is in a format the STT service can consume
            prepared_audio = self._prepare_audio_bytes(audio_data, audio_format)

            # Call audio service STT
            transcription = await self.audio_service.speech_to_text(
                audio=prepared_audio,
                language=language
            )

            if transcription and transcription.strip():
                logger.info(f"STT result: {transcription}")
                return transcription.strip()
            else:
                logger.warning("STT returned empty transcription")
                return None

        except Exception as e:
            logger.error(f"STT processing error: {str(e)}", exc_info=True)
            return None
        finally:
            self.is_processing = False

    async def process_buffered_speech(
        self,
        audio_format: str = "wav",
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Process the current buffer through STT if ready.

        Args:
            audio_format: Audio format (wav, mp3, opus, etc.)
            language: Language code for STT

        Returns:
            Transcribed text or None if buffer not ready or processing fails
        """
        if not self.should_process_buffer():
            return None

        audio_data = self.get_buffered_audio()
        if not audio_data:
            return None

        return await self.process_speech_to_text(
            audio_data=audio_data,
            audio_format=audio_format,
            language=language
        )

    def get_buffer_stats(self) -> dict:
        """
        Get statistics about the current buffer state.

        Returns:
            Dictionary with buffer statistics
        """
        return {
            "chunk_count": len(self.audio_buffer),
            "buffer_duration_ms": self.buffer_duration_ms,
            "is_processing": self.is_processing,
            "speech_started": self.speech_started,
            "consecutive_silence_chunks": self.consecutive_silence_chunks,
            "time_since_last_chunk_ms": (
                (time.time() - self.last_chunk_time) * 1000
                if self.last_chunk_time > 0
                else 0
            )
        }
