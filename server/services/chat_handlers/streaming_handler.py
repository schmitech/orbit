"""
Streaming Handler

Manages streaming response processing including chunk accumulation,
sentence detection, and streaming audio generation.
"""

import json
import asyncio
import base64
import logging
from typing import Dict, Any, Optional, AsyncIterator, Tuple

from utils.sentence_detector import SentenceDetector
from .audio_handler import AudioHandler

logger = logging.getLogger(__name__)


class StreamingState:
    """Holds state for streaming response processing."""

    def __init__(self, return_audio: bool = False):
        """
        Initialize streaming state.

        Args:
            return_audio: Whether audio generation is enabled
        """
        self.accumulated_text = ""
        self.sources = []
        self.stream_completed = False
        self.first_chunk_yielded = False
        self.chunk_count = 0
        self.sentence_detector = SentenceDetector() if return_audio else None
        self.audio_chunks_sent = 0
        self.return_audio = return_audio


class StreamingHandler:
    """Handles streaming response processing and audio generation."""

    def __init__(
        self,
        config: Dict[str, Any],
        audio_handler: AudioHandler,
        verbose: bool = False
    ):
        """
        Initialize the streaming handler.

        Args:
            config: Application configuration
            audio_handler: Audio handler for TTS generation
            verbose: Enable verbose logging
        """
        self.config = config
        self.audio_handler = audio_handler
        self.verbose = verbose

        # Audio timeout settings
        self.audio_timeout = 5.0  # 5 second timeout per sentence

    async def _generate_sentence_audio(
        self,
        sentence: str,
        adapter_name: str,
        tts_voice: Optional[str],
        language: Optional[str],
        chunk_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        Generate audio for a single sentence with timeout.

        Args:
            sentence: The sentence text
            adapter_name: Adapter for audio provider lookup
            tts_voice: TTS voice to use
            language: Language code
            chunk_index: Index of this audio chunk

        Returns:
            Audio chunk dictionary or None if generation fails
        """
        try:
            audio_data, audio_format_str = await asyncio.wait_for(
                self.audio_handler.generate_audio(
                    text=sentence.strip(),
                    adapter_name=adapter_name,
                    tts_voice=tts_voice,
                    language=language
                ),
                timeout=self.audio_timeout
            )

            if audio_data:
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                return {
                    "audio_chunk": audio_base64,
                    "audioFormat": audio_format_str or "opus",
                    "chunk_index": chunk_index,
                    "done": False
                }

        except asyncio.TimeoutError:
            logger.warning(f"TTS generation timeout for sentence, skipping audio chunk")
        except Exception as e:
            logger.warning(f"Failed to generate streaming audio for sentence: {str(e)}", exc_info=True)

        return None

    async def process_stream(
        self,
        pipeline_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: bool = False
    ) -> AsyncIterator[Tuple[str, StreamingState]]:
        """
        Process the pipeline stream, yielding chunks and managing state.

        Args:
            pipeline_stream: Async iterator of pipeline chunks
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code
            return_audio: Whether to generate streaming audio

        Yields:
            Tuple of (formatted_chunk, streaming_state)
        """
        state = StreamingState(return_audio=return_audio)

        try:
            async for chunk in pipeline_stream:
                try:
                    chunk_data = json.loads(chunk)

                    # Handle errors
                    if "error" in chunk_data:
                        yield f"data: {chunk}\n\n", state
                        return

                    # Debug: Log first chunk timing
                    if not state.first_chunk_yielded and "response" in chunk_data and chunk_data["response"]:
                        state.first_chunk_yielded = True
                        if self.verbose:
                            logger.info(f"Yielding first chunk to client: {repr(chunk_data['response'][:50])}")

                    # Handle done marker - DON'T yield it yet
                    if chunk_data.get("done", False):
                        # Accumulate any remaining content before breaking
                        if "response" in chunk_data:
                            state.accumulated_text += chunk_data["response"]
                        if "sources" in chunk_data:
                            state.sources = chunk_data["sources"]
                        state.stream_completed = True
                        break

                    # Stream text chunk immediately
                    yield f"data: {chunk}\n\n", state

                    state.chunk_count += 1

                    # Accumulate content
                    if "response" in chunk_data:
                        new_text = chunk_data["response"]
                        state.accumulated_text += new_text

                        # Generate streaming audio if enabled
                        if return_audio and state.sentence_detector and new_text:
                            completed_sentences = state.sentence_detector.add_text(new_text)

                            # Generate TTS for each completed sentence
                            for sentence in completed_sentences:
                                if sentence.strip():
                                    audio_chunk = await self._generate_sentence_audio(
                                        sentence=sentence,
                                        adapter_name=adapter_name,
                                        tts_voice=tts_voice,
                                        language=language,
                                        chunk_index=state.audio_chunks_sent
                                    )

                                    if audio_chunk:
                                        state.audio_chunks_sent += 1
                                        audio_chunk_json = json.dumps(audio_chunk)
                                        yield f"data: {audio_chunk_json}\n\n", state

                                        # Small pause every 5 chunks to prevent overwhelming client
                                        if state.audio_chunks_sent % 5 == 0:
                                            await asyncio.sleep(0.01)

                                        if self.verbose:
                                            logger.info(
                                                f"Sent streaming audio chunk {state.audio_chunks_sent} "
                                                f"({len(audio_chunk['audio_chunk'])} chars base64)"
                                            )

                    # Handle sources
                    if "sources" in chunk_data:
                        state.sources = chunk_data["sources"]

                except json.JSONDecodeError:
                    # Still yield the chunk even if we can't parse it
                    yield f"data: {chunk}\n\n", state
                    continue

        except Exception as e:
            logger.error(f"Error in streaming handler: {str(e)}", exc_info=True)
            error_chunk = json.dumps({
                "error": f"Stream processing failed: {str(e)}",
                "done": True
            })
            yield f"data: {error_chunk}\n\n", state

    async def generate_remaining_audio(
        self,
        state: StreamingState,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate audio for remaining text after streaming completes.

        Args:
            state: Current streaming state
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code

        Yields:
            Formatted audio chunk string if audio was generated
        """
        if not state.sentence_detector or state.audio_chunks_sent == 0:
            return None

        remaining_text = state.sentence_detector.get_remaining_text()
        if not remaining_text.strip():
            return None

        try:
            if self.verbose:
                logger.info(f"Generating audio for remaining text: {len(remaining_text)} chars")

            audio_data, audio_format_str = await self.audio_handler.generate_audio(
                text=remaining_text.strip(),
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language
            )

            if audio_data:
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
                audio_chunk = {
                    "audio_chunk": audio_base64,
                    "audioFormat": audio_format_str or "opus",
                    "chunk_index": state.audio_chunks_sent,
                    "done": False
                }
                state.audio_chunks_sent += 1

                if self.verbose:
                    logger.info(
                        f"Sent remaining audio chunk {state.audio_chunks_sent} "
                        f"({len(audio_base64)} chars base64)"
                    )

                return f"data: {json.dumps(audio_chunk)}\n\n"

        except Exception as e:
            logger.warning(f"Failed to generate audio for remaining text: {str(e)}", exc_info=True)

        return None

    def build_done_chunk(
        self,
        state: StreamingState,
        audio_data: Optional[bytes] = None,
        audio_format_str: Optional[str] = None
    ) -> str:
        """
        Build the final done chunk with all metadata.

        Args:
            state: Current streaming state
            audio_data: Optional full audio data (for non-streaming audio)
            audio_format_str: Audio format string

        Returns:
            Formatted done chunk string
        """
        done_chunk = {"done": True}

        if state.sources:
            done_chunk["sources"] = state.sources

        # Include total audio chunks count if streaming audio was used
        if state.sentence_detector and state.audio_chunks_sent > 0:
            done_chunk["total_audio_chunks"] = state.audio_chunks_sent

        if self.verbose:
            logger.info(
                f"Preparing done chunk: audio_data={audio_data is not None}, "
                f"audio_format_str={audio_format_str}, "
                f"total_audio_chunks={state.audio_chunks_sent if state.sentence_detector else 0}"
            )

        # Only include audio in done chunk for non-streaming mode
        if audio_data and not (state.sentence_detector and state.audio_chunks_sent > 0):
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            done_chunk["audio"] = audio_base64
            done_chunk["audioFormat"] = audio_format_str or "mp3"
            if self.verbose:
                logger.info(f"Including audio in done chunk: {len(audio_base64)} chars (base64)")

        done_json = json.dumps(done_chunk)

        if self.verbose:
            logger.info(f"Yielding done chunk: {len(done_json)} bytes total")
            logger.info(f"Done chunk keys: {list(done_chunk.keys())}, has audio: {'audio' in done_chunk}")
            if 'audio' in done_chunk:
                logger.info(
                    f"Audio field present, length: {len(done_chunk['audio'])}, "
                    f"format: {done_chunk.get('audioFormat')}"
                )
            logger.info(f"Done chunk JSON preview: {done_json[:200]}...")

        return f"data: {done_json}\n\n"
