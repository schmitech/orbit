"""
Streaming Handler

Manages streaming response processing including chunk accumulation,
sentence detection, and streaming audio generation.
"""

import json
import asyncio
import base64
import logging
from typing import Dict, Any, Optional, AsyncIterator, Tuple, List
from collections import deque

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
        audio_handler: AudioHandler
    ):
        """
        Initialize the streaming handler.

        Args:
            config: Application configuration
            audio_handler: Audio handler for TTS generation
        """
        self.config = config
        self.audio_handler = audio_handler

        # Audio timeout settings
        # Increased for vLLM TTS which can take 5-10s per sentence with remote servers
        # With sentence batching (3 sentences), we need longer timeout for the combined text
        self.audio_timeout = 45.0  # 45 second timeout for batched sentences

        # Sentence batching for TTS (reduces number of API calls)
        self.sentence_batch_size = 3  # Batch up to 3 sentences together
        self._pending_sentences = []  # Accumulator for sentence batching
        
        # Parallel audio generation settings
        # Match vLLM server's max-num-seqs for optimal throughput
        # Can be increased if vLLM server has higher --max-num-seqs
        sounds_config = config.get('sounds', {})
        vllm_config = sounds_config.get('vllm', {})
        vllm_max_concurrent = vllm_config.get('max_concurrent_requests', 4)
        self.max_concurrent_audio_tasks = min(vllm_max_concurrent, 4)  # Cap at 4 to prevent overload
        self._audio_task_queue = deque()  # Queue for audio generation tasks
        self._audio_results = {}  # Cache for completed audio chunks
        self._next_chunk_index = 0  # Track expected chunk order

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
                # Use faster base64 encoding in executor to avoid blocking
                loop = asyncio.get_event_loop()
                audio_base64 = await loop.run_in_executor(
                    None,
                    lambda: base64.b64encode(audio_data).decode('utf-8')
                )
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

    async def _generate_audio_background(
        self,
        sentence: str,
        adapter_name: str,
        tts_voice: Optional[str],
        language: Optional[str],
        chunk_index: int
    ) -> None:
        """
        Generate audio in background and store result.

        Args:
            sentence: The sentence text
            adapter_name: Adapter for audio provider lookup
            tts_voice: TTS voice to use
            language: Language code
            chunk_index: Index of this audio chunk
        """
        try:
            audio_chunk = await self._generate_sentence_audio(
                sentence=sentence,
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language,
                chunk_index=chunk_index
            )
            if audio_chunk:
                self._audio_results[chunk_index] = audio_chunk
        except Exception as e:
            logger.warning(f"Background audio generation failed for chunk {chunk_index}: {str(e)}")
            self._audio_results[chunk_index] = None  # Mark as failed

    async def _yield_ready_audio_chunks(
        self, 
        state: StreamingState
    ) -> AsyncIterator[Tuple[str, StreamingState]]:
        """
        Yield any ready audio chunks in order.

        Args:
            state: Current streaming state

        Yields:
            Tuple of (audio_chunk_string, updated_state)
        """
        # Yield chunks in order as they become available
        while self._next_chunk_index in self._audio_results:
            chunk = self._audio_results.pop(self._next_chunk_index)
            # Only yield if chunk is not None and is a valid dictionary
            if chunk and isinstance(chunk, dict):
                state.audio_chunks_sent += 1
                audio_chunk_json = json.dumps(chunk)
                yield f"data: {audio_chunk_json}\n\n", state

                logger.debug(
                    f"Sent streaming audio chunk {state.audio_chunks_sent} "
                    f"({len(chunk.get('audio_chunk', ''))} chars base64)"
                )
            elif chunk is None:
                # Log but don't yield - chunk generation failed
                logger.debug(f"Skipping None chunk at index {self._next_chunk_index}")
            self._next_chunk_index += 1

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

        # Clear pending sentences and audio state to avoid state leakage between requests
        self._pending_sentences = []
        self._audio_results.clear()
        self._next_chunk_index = 0
        self._audio_task_queue.clear()
        
        # Track running audio tasks for parallel generation
        running_audio_tasks = []
        
        # Track remaining audio task (started early when stream nears end)
        remaining_audio_task = None
        remaining_audio_started = False

        # Validate pipeline_stream is not None
        if pipeline_stream is None:
            logger.error("pipeline_stream is None - cannot process stream")
            error_chunk = json.dumps({
                "error": "Pipeline stream is not available",
                "done": True
            })
            yield f"data: {error_chunk}\n\n", state
            return

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
                        logger.debug(f"Yielding first chunk to client: {repr(chunk_data['response'][:50])}")

                    # Handle done marker - DON'T yield it yet
                    if chunk_data.get("done", False):
                        # Accumulate any remaining content before breaking
                        if "response" in chunk_data:
                            new_text = chunk_data["response"]
                            state.accumulated_text += new_text
                            
                            # Process any remaining text for early audio generation
                            if return_audio and state.sentence_detector and new_text:
                                state.sentence_detector.add_text(new_text)
                                
                                # Start remaining audio generation EARLY (non-blocking)
                                if not remaining_audio_started:
                                    remaining_text = state.sentence_detector.get_remaining_text()
                                    if remaining_text.strip():
                                        remaining_audio_started = True
                                        chunk_index = state.audio_chunks_sent + len(running_audio_tasks)

                                        logger.debug(f"Starting early remaining audio generation: {len(remaining_text)} chars (chunk {chunk_index})")

                                        # Start in background immediately
                                        remaining_audio_task = asyncio.create_task(
                                            self._generate_audio_background(
                                                sentence=remaining_text.strip(),
                                                adapter_name=adapter_name,
                                                tts_voice=tts_voice,
                                                language=language,
                                                chunk_index=chunk_index
                                            )
                                        )
                                        running_audio_tasks.append(remaining_audio_task)
                                        
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

                            # Batch sentences for TTS to reduce API calls
                            for sentence in completed_sentences:
                                if sentence.strip():
                                    self._pending_sentences.append(sentence.strip())

                                    # Generate TTS when batch is full
                                    if len(self._pending_sentences) >= self.sentence_batch_size:
                                        batched_text = " ".join(self._pending_sentences)
                                        self._pending_sentences = []

                                        chunk_index = state.audio_chunks_sent + len(running_audio_tasks)

                                        logger.debug(f"Queueing TTS for batched sentences: {len(batched_text)} chars (chunk {chunk_index})")

                                        # Start audio generation in background (non-blocking)
                                        task = asyncio.create_task(
                                            self._generate_audio_background(
                                                sentence=batched_text,
                                                adapter_name=adapter_name,
                                                tts_voice=tts_voice,
                                                language=language,
                                                chunk_index=chunk_index
                                            )
                                        )
                                        running_audio_tasks.append(task)

                                        # Limit concurrent audio tasks
                                        if len(running_audio_tasks) >= self.max_concurrent_audio_tasks:
                                            # Wait for at least one task to complete
                                            done, pending = await asyncio.wait(
                                                running_audio_tasks,
                                                return_when=asyncio.FIRST_COMPLETED
                                            )
                                            running_audio_tasks = list(pending)
                                            
                                            # Yield any ready chunks immediately
                                            async for audio_chunk_str, updated_state in self._yield_ready_audio_chunks(state):
                                                yield audio_chunk_str, updated_state
                                        else:
                                            # Check for ready chunks even if not at limit
                                            async for audio_chunk_str, updated_state in self._yield_ready_audio_chunks(state):
                                                yield audio_chunk_str, updated_state

                    # Handle sources
                    if "sources" in chunk_data:
                        state.sources = chunk_data["sources"]

                except json.JSONDecodeError:
                    # Still yield the chunk even if we can't parse it
                    yield f"data: {chunk}\n\n", state
                    continue

            # Wait for all pending audio tasks to complete (including early-started remaining audio)
            if running_audio_tasks:
                logger.debug(f"Waiting for {len(running_audio_tasks)} pending audio tasks to complete")
                await asyncio.gather(*running_audio_tasks, return_exceptions=True)
                
                # Yield all remaining ready chunks (including early-started remaining audio)
                async for audio_chunk_str, updated_state in self._yield_ready_audio_chunks(state):
                    yield audio_chunk_str, updated_state

            # Flush any remaining batched sentences after stream completes
            if return_audio and self._pending_sentences:
                batched_text = " ".join(self._pending_sentences)
                self._pending_sentences = []

                chunk_index = state.audio_chunks_sent

                logger.debug(f"Flushing remaining batched sentences: {len(batched_text)} chars")

                # Generate final audio chunk
                audio_chunk = await self._generate_sentence_audio(
                    sentence=batched_text,
                    adapter_name=adapter_name,
                    tts_voice=tts_voice,
                    language=language,
                    chunk_index=chunk_index
                )

                if audio_chunk:
                    state.audio_chunks_sent += 1
                    audio_chunk_json = json.dumps(audio_chunk)
                    yield f"data: {audio_chunk_json}\n\n", state

                    logger.debug(
                        f"Sent final batched audio chunk {state.audio_chunks_sent} "
                        f"({len(audio_chunk['audio_chunk'])} chars base64)"
                    )

        except Exception as e:
            logger.error(f"Error in streaming handler: {str(e)}", exc_info=True)
            error_chunk = json.dumps({
                "error": f"Stream processing failed: {str(e)}",
                "done": True
            })
            yield f"data: {error_chunk}\n\n", state

    async def process_stream_raw(
        self,
        pipeline_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: bool = False
    ) -> AsyncIterator[Tuple[Dict[str, Any], StreamingState]]:
        """
        Process the pipeline stream, yielding structured data (no SSE formatting).

        This method is intended for internal/WebSocket use where SSE formatting
        is not needed. It yields raw dictionaries instead of formatted strings.

        Args:
            pipeline_stream: Async iterator of pipeline chunks
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code
            return_audio: Whether to generate streaming audio

        Yields:
            Tuple of (chunk_dict, streaming_state)
        """
        # Process through the existing method and parse the SSE format
        async for formatted_chunk, state in self.process_stream(
            pipeline_stream=pipeline_stream,
            adapter_name=adapter_name,
            tts_voice=tts_voice,
            language=language,
            return_audio=return_audio
        ):
            # Parse SSE format: "data: {...}\n\n"
            if formatted_chunk.startswith("data: "):
                chunk_json = formatted_chunk[6:].strip()
                try:
                    chunk_data = json.loads(chunk_json)
                    yield chunk_data, state
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse chunk JSON: {chunk_json[:100]}")
                    continue
            else:
                # Unexpected format, skip
                logger.warning(f"Unexpected chunk format: {formatted_chunk[:100]}")
                continue

    async def generate_remaining_audio(
        self,
        state: StreamingState,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate audio for remaining text after streaming completes.
        
        Note: This is now primarily a fallback. Remaining audio should be
        generated early during stream processing for better performance.

        Args:
            state: Current streaming state
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code

        Returns:
            Formatted audio chunk string if audio was generated
        """
        if not state.sentence_detector or state.audio_chunks_sent == 0:
            return None

        remaining_text = state.sentence_detector.get_remaining_text()
        if not remaining_text.strip():
            return None

        try:
            logger.debug(f"Generating audio for remaining text (fallback): {len(remaining_text)} chars")

            result = await self.audio_handler.generate_audio(
                text=remaining_text.strip(),
                adapter_name=adapter_name,
                tts_voice=tts_voice,
                language=language
            )

            # Properly handle None or tuple return
            audio_data = None
            audio_format_str = None
            if result is not None:
                audio_data, audio_format_str = result

            if audio_data:
                # Use async base64 encoding for better performance
                loop = asyncio.get_event_loop()
                audio_base64 = await loop.run_in_executor(
                    None,
                    lambda: base64.b64encode(audio_data).decode('utf-8')
                )
                
                audio_chunk = {
                    "audio_chunk": audio_base64,
                    "audioFormat": audio_format_str or "opus",
                    "chunk_index": state.audio_chunks_sent,
                    "done": False
                }
                state.audio_chunks_sent += 1

                logger.debug(
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
        audio_format_str: Optional[str] = None,
        threading_metadata: Optional[Dict[str, Any]] = None
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
        
        # Include threading metadata if available
        if threading_metadata:
            done_chunk["threading"] = threading_metadata
            logger.debug(f"Including threading metadata in done chunk: {threading_metadata}")

        logger.debug(
            f"Preparing done chunk: audio_data={audio_data is not None}, "
            f"audio_format_str={audio_format_str}, "
            f"total_audio_chunks={state.audio_chunks_sent if state.sentence_detector else 0}"
        )

        # Only include audio in done chunk for non-streaming mode
        if audio_data and not (state.sentence_detector and state.audio_chunks_sent > 0):
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            done_chunk["audio"] = audio_base64
            done_chunk["audioFormat"] = audio_format_str or "mp3"
            logger.debug(f"Including audio in done chunk: {len(audio_base64)} chars (base64)")

        done_json = json.dumps(done_chunk)

        logger.debug(f"Yielding done chunk: {len(done_json)} bytes total")
        logger.debug(f"Done chunk keys: {list(done_chunk.keys())}, has audio: {'audio' in done_chunk}")
        if 'audio' in done_chunk:
            logger.debug(
                f"Audio field present, length: {len(done_chunk['audio'])}, "
                f"format: {done_chunk.get('audioFormat')}"
            )
        logger.debug(f"Done chunk JSON preview: {done_json[:200]}...")

        return f"data: {done_json}\n\n"
