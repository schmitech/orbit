"""
Audio Output Streamer

Manages streaming audio chunks to WebSocket clients for real-time voice conversations.
Coordinates with StreamingHandler to process LLM text streams and generate audio.
"""

import logging
import asyncio
import json
import base64
from typing import Optional, AsyncIterator, Dict, Any

from .streaming_handler import StreamingHandler

logger = logging.getLogger(__name__)


class AudioOutputStreamer:
    """Streams audio chunks to WebSocket client."""

    def __init__(self, streaming_handler: StreamingHandler):
        """
        Initialize the audio output streamer.

        Args:
            streaming_handler: Handler for streaming LLM responses and audio generation
        """
        self.streaming_handler = streaming_handler

        # State tracking
        self.is_streaming = False
        self.interrupted = False

        # Track audio chunk index
        self.chunk_index = 0

    def reset(self):
        """Reset the streamer state."""
        self.is_streaming = False
        self.interrupted = False
        self.chunk_index = 0
        logger.debug("Audio output streamer reset")

    def interrupt(self):
        """Signal an interruption to stop current audio streaming."""
        self.interrupted = True
        logger.info("Audio output streamer interrupted")

    async def stream_audio_response(
        self,
        llm_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        default_audio_format: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream audio chunks from LLM text stream.

        This method processes the LLM text stream through the StreamingHandler
        which handles sentence detection, batching, and parallel TTS generation.

        Args:
            llm_stream: Async iterator of LLM response chunks
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code

        Yields:
            Audio chunk dictionaries ready for WebSocket transmission
        """
        self.is_streaming = True
        self.interrupted = False
        chunk_count = 0

        async def json_chunk_stream():
            """Convert SSE-formatted chunks into raw JSON strings."""
            async for chunk in llm_stream:
                if not chunk:
                    continue
                chunk_str = chunk.strip()
                if not chunk_str:
                    continue
                if chunk_str.startswith("data:"):
                    chunk_str = chunk_str[5:]
                chunk_str = chunk_str.lstrip()
                if not chunk_str:
                    continue
                yield chunk_str

        try:
            # Process stream through the streaming handler's raw output method
            # StreamingHandler already handles:
            # - Sentence detection and batching
            # - Parallel TTS generation
            # - Audio chunk ordering
            # Using process_stream_raw() to get structured data instead of SSE-formatted strings
            async for chunk_data, state in self.streaming_handler.process_stream_raw(
                pipeline_stream=json_chunk_stream(),
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language,
                return_audio=True
            ):
                # Check for interruption
                if self.interrupted:
                    logger.info("Audio streaming interrupted by user")
                    break

                # Yield audio chunks
                if "audio_chunk" in chunk_data:
                    audio_format = chunk_data.get("audioFormat") or default_audio_format or "mp3"
                    chunk_count += 1
                    logger.debug(
                        f"Yielding audio chunk {chunk_count} "
                        f"(index: {chunk_data.get('chunk_index', 'unknown')} "
                        f"format: {audio_format})"
                    )
                    yield {
                        "type": "audio_chunk",
                        "data": chunk_data["audio_chunk"],
                        "format": audio_format,
                        "chunk_index": chunk_data.get("chunk_index", chunk_count - 1),
                        "done": False
                    }

                # Also yield transcription text if available (optional)
                elif "response" in chunk_data and chunk_data["response"]:
                    yield {
                        "type": "transcription",
                        "text": chunk_data["response"]
                    }

                # Handle done marker
                elif chunk_data.get("done"):
                    logger.debug(
                        f"Stream completed, total audio chunks sent: {chunk_count}"
                    )
                    # Don't yield done here - will be sent after cleanup

            logger.info(
                f"Audio streaming completed successfully, "
                f"total chunks: {chunk_count}, "
                f"interrupted: {self.interrupted}"
            )

        except Exception as e:
            logger.error(f"Error during audio streaming: {str(e)}", exc_info=True)
            yield {
                "type": "error",
                "message": f"Audio streaming error: {str(e)}"
            }
        finally:
            self.is_streaming = False

    async def generate_single_audio_response(
        self,
        text: str,
        audio_handler,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a single audio response from text (non-streaming).

        This is useful for quick responses or when streaming is not needed.

        Args:
            text: Text to convert to speech
            audio_handler: Audio handler for TTS
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code

        Returns:
            Audio chunk dictionary or None if generation fails
        """
        try:
            logger.debug(f"Generating single audio response for text: {text[:100]}...")

            audio_data, audio_format = await audio_handler.generate_audio(
                text=text,
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language
            )

            if not audio_data:
                logger.warning("No audio data generated")
                return None

            # Encode to base64
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')

            return {
                "type": "audio_chunk",
                "data": audio_base64,
                "format": audio_format or "wav",
                "chunk_index": 0,
                "done": True
            }

        except Exception as e:
            logger.error(f"Error generating single audio response: {str(e)}", exc_info=True)
            return None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current streaming state.

        Returns:
            Dictionary with streaming statistics
        """
        return {
            "is_streaming": self.is_streaming,
            "interrupted": self.interrupted,
            "chunk_index": self.chunk_index
        }
