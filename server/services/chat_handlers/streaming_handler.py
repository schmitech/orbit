"""
Streaming Handler

Manages streaming response processing including chunk accumulation,
sentence detection, and streaming audio generation.
"""

import json
import asyncio
import base64
import logging
import inspect
from typing import Any, Optional
from collections.abc import AsyncIterator
from collections import deque

from utils.sentence_detector import SentenceDetector
from .audio_handler import AudioHandler
from .streaming_events import (
    AudioChunkEvent,
    DoneEvent,
    ErrorEvent,
    RawEvent,
    ResponseEvent,
    StreamEvent,
    format_stream_event,
    stream_event_to_dict,
)

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
        config: dict[str, Any],
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

        # Sentence batching for TTS
        # batch_size=1 gives fastest time-to-first-audio (each sentence fires immediately)
        # Increase to 2-3 to reduce API calls at the cost of higher latency
        self.sentence_batch_size = 1
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
    ) -> Optional[dict[str, Any]]:
        """
        Generate audio for a single sentence with timeout.

        Uses provider-level streaming (with_streaming_response) when available
        so that audio bytes are collected as they arrive from the TTS API,
        reducing overall latency.

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
            async def _generate_audio() -> tuple[Optional[bytes], Optional[str]]:
                # Prefer provider-level streaming when available, then fall back
                # to the stable non-streaming AudioHandler contract.
                audio_chunks = []
                audio_format_str = None
                streaming_method = getattr(self.audio_handler, "generate_audio_streaming", None)

                if callable(streaming_method):
                    try:
                        stream = streaming_method(
                            text=sentence.strip(),
                            adapter_name=adapter_name,
                            tts_voice=tts_voice,
                            language=language
                        )

                        if inspect.isawaitable(stream):
                            stream = await stream

                        if hasattr(stream, "__aiter__"):
                            async for chunk_bytes, fmt in stream:
                                audio_chunks.append(chunk_bytes)
                                if audio_format_str is None:
                                    audio_format_str = fmt
                    except (AttributeError, TypeError) as e:
                        logger.debug(f"Streaming audio unavailable, falling back to generate_audio: {e!s}")

                if audio_chunks:
                    return b"".join(audio_chunks), audio_format_str

                result = await self.audio_handler.generate_audio(
                    text=sentence.strip(),
                    adapter_name=adapter_name,
                    tts_voice=tts_voice,
                    language=language
                )
                if result is None:
                    return None, None
                return result

            audio_data, audio_format_str = await asyncio.wait_for(
                _generate_audio(),
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
            logger.warning("TTS generation timeout for sentence, skipping audio chunk")
        except Exception as e:
            logger.warning(f"Failed to generate streaming audio for sentence: {e!s}", exc_info=True)

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
        except Exception as e:  # noqa: BLE001 - pluggable TTS provider boundary; background task must isolate its failure
            logger.warning(f"Background audio generation failed for chunk {chunk_index}: {e!s}")
            self._audio_results[chunk_index] = None  # Mark as failed

    async def _yield_ready_audio_chunks(
        self,
        state: StreamingState
    ) -> AsyncIterator[tuple[StreamEvent, StreamingState]]:
        """
        Yield any ready audio chunks in order.

        Args:
            state: Current streaming state

        Yields:
            Tuple of (AudioChunkEvent, updated_state)
        """
        # Yield chunks in order as they become available
        while self._next_chunk_index in self._audio_results:
            chunk = self._audio_results.pop(self._next_chunk_index)
            # Only yield if chunk is not None and is a valid dictionary
            if chunk and isinstance(chunk, dict):
                state.audio_chunks_sent += 1
                yield AudioChunkEvent(
                    audio_chunk=chunk["audio_chunk"],
                    audio_format=chunk.get("audioFormat", "opus"),
                    chunk_index=chunk["chunk_index"],
                ), state

                logger.debug(
                    f"Sent streaming audio chunk {state.audio_chunks_sent} "
                    f"({len(chunk.get('audio_chunk', ''))} chars base64)"
                )
            elif chunk is None:
                # Log but don't yield - chunk generation failed
                logger.debug(f"Skipping None chunk at index {self._next_chunk_index}")
            self._next_chunk_index += 1

    async def process_stream_events(
        self,
        pipeline_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: bool = False
    ) -> AsyncIterator[tuple[StreamEvent, StreamingState]]:
        """
        Process the pipeline stream, yielding structured events and managing
        state. This is the canonical producer — `process_stream` (SSE) and
        `process_stream_raw` (dicts) are both thin formatting wrappers
        around this method.

        Args:
            pipeline_stream: Async iterator of pipeline chunks
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code
            return_audio: Whether to generate streaming audio

        Yields:
            Tuple of (StreamEvent, streaming_state)
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
            yield ErrorEvent(error="Pipeline stream is not available", extra={"done": True}), state
            return

        try:
            async for chunk in pipeline_stream:
                try:
                    chunk_data = json.loads(chunk)

                    # Handle errors
                    if "error" in chunk_data:
                        yield ErrorEvent(
                            error=chunk_data["error"],
                            extra={k: v for k, v in chunk_data.items() if k != "error"},
                            raw=chunk,
                        ), state
                        return

                    # Debug: Log first chunk timing
                    if not state.first_chunk_yielded and "response" in chunk_data and chunk_data["response"]:
                        state.first_chunk_yielded = True
                        logger.debug(f"Yielding first chunk to client: {chunk_data['response'][:50]!r}")

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
                    yield ResponseEvent(
                        text=chunk_data.get("response", ""),
                        extra={k: v for k, v in chunk_data.items() if k != "response"},
                        raw=chunk,
                    ), state

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
                                            async for audio_event, updated_state in self._yield_ready_audio_chunks(state):
                                                yield audio_event, updated_state
                                        else:
                                            # Check for ready chunks even if not at limit
                                            async for audio_event, updated_state in self._yield_ready_audio_chunks(state):
                                                yield audio_event, updated_state

                    # Handle sources
                    if "sources" in chunk_data:
                        state.sources = chunk_data["sources"]

                except json.JSONDecodeError:
                    # Still yield the chunk even if we can't parse it
                    yield RawEvent(raw=chunk), state
                    continue

            # Wait for all pending audio tasks to complete (including early-started remaining audio)
            if running_audio_tasks:
                logger.debug(f"Waiting for {len(running_audio_tasks)} pending audio tasks to complete")
                await asyncio.gather(*running_audio_tasks, return_exceptions=True)

                # Yield all remaining ready chunks (including early-started remaining audio)
                async for audio_event, updated_state in self._yield_ready_audio_chunks(state):
                    yield audio_event, updated_state

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
                    yield AudioChunkEvent(
                        audio_chunk=audio_chunk["audio_chunk"],
                        audio_format=audio_chunk.get("audioFormat", "opus"),
                        chunk_index=audio_chunk["chunk_index"],
                    ), state

                    logger.debug(
                        f"Sent final batched audio chunk {state.audio_chunks_sent} "
                        f"({len(audio_chunk['audio_chunk'])} chars base64)"
                    )

        except Exception as e:
            logger.error(f"Error in streaming handler: {e!s}", exc_info=True)
            yield ErrorEvent(error=f"Stream processing failed: {e!s}", extra={"done": True}), state

    async def process_stream(
        self,
        pipeline_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: bool = False
    ) -> AsyncIterator[tuple[str, StreamingState]]:
        """
        Process the pipeline stream, yielding SSE-formatted chunks and
        managing state. Thin SSE-formatting wrapper around
        `process_stream_events`.

        Yields:
            Tuple of (formatted_chunk, streaming_state)
        """
        async for event, state in self.process_stream_events(
            pipeline_stream=pipeline_stream,
            adapter_name=adapter_name,
            tts_voice=tts_voice,
            language=language,
            return_audio=return_audio,
        ):
            yield format_stream_event(event), state

    async def process_stream_raw(
        self,
        pipeline_stream: AsyncIterator,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None,
        return_audio: bool = False
    ) -> AsyncIterator[tuple[dict[str, Any], StreamingState]]:
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
        # Thin dict-formatting wrapper around process_stream_events. A RawEvent
        # (a pipeline chunk that failed json.loads) has no dict form, matching
        # the legacy behavior of this method, which skipped such chunks with a
        # warning rather than yielding them.
        async for event, state in self.process_stream_events(
            pipeline_stream=pipeline_stream,
            adapter_name=adapter_name,
            tts_voice=tts_voice,
            language=language,
            return_audio=return_audio,
        ):
            if isinstance(event, RawEvent):
                logger.warning(f"Skipping unparseable chunk: {event.raw[:100]}")
                continue
            yield stream_event_to_dict(event), state

    async def generate_remaining_audio_event(
        self,
        state: StreamingState,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[AudioChunkEvent]:
        """
        Generate audio for remaining text after streaming completes.
        Canonical producer — `generate_remaining_audio` is a thin
        SSE-formatting wrapper around this.

        Note: This is now primarily a fallback. Remaining audio should be
        generated early during stream processing for better performance.

        Args:
            state: Current streaming state
            adapter_name: Adapter name for audio provider
            tts_voice: Optional TTS voice
            language: Optional language code

        Returns:
            The audio chunk event, if audio was generated
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

                event = AudioChunkEvent(
                    audio_chunk=audio_base64,
                    audio_format=audio_format_str or "opus",
                    chunk_index=state.audio_chunks_sent,
                )
                state.audio_chunks_sent += 1

                logger.debug(
                    f"Sent remaining audio chunk {state.audio_chunks_sent} "
                    f"({len(audio_base64)} chars base64)"
                )

                return event

        except Exception as e:
            logger.warning(f"Failed to generate audio for remaining text: {e!s}", exc_info=True)

        return None

    async def generate_remaining_audio(
        self,
        state: StreamingState,
        adapter_name: str,
        tts_voice: Optional[str] = None,
        language: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate audio for remaining text after streaming completes. Thin
        SSE-formatting wrapper around `generate_remaining_audio_event`.

        Returns:
            Formatted audio chunk string if audio was generated
        """
        event = await self.generate_remaining_audio_event(state, adapter_name, tts_voice, language)
        return format_stream_event(event) if event else None

    def build_done_event(
        self,
        state: StreamingState,
        audio_data: Optional[bytes] = None,
        audio_format_str: Optional[str] = None,
        threading_metadata: Optional[dict[str, Any]] = None,
        assistant_message_id: Optional[str] = None,
        model: Optional[str] = None,
        image: Optional[str] = None,
        image_format: Optional[str] = None,
        image_revised_prompt: Optional[str] = None,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        video_format: Optional[str] = None,
        video_revised_prompt: Optional[str] = None,
        document_url: Optional[str] = None,
        document_format: Optional[str] = None,
        document_revised_prompt: Optional[str] = None,
        generated_audio_url: Optional[str] = None,
        generated_audio_format: Optional[str] = None,
        generated_audio_revised_prompt: Optional[str] = None,
    ) -> DoneEvent:
        """
        Build the final done event with all metadata. Canonical producer —
        `build_done_chunk` is a thin SSE-formatting wrapper around this.

        Args:
            state: Current streaming state
            audio_data: Optional full audio data (for non-streaming audio)
            audio_format_str: Audio format string

        Returns:
            The done event
        """
        event = DoneEvent(
            sources=state.sources if state.sources else None,
            # Include total audio chunks count if streaming audio was used
            total_audio_chunks=(
                state.audio_chunks_sent if state.sentence_detector and state.audio_chunks_sent > 0 else None
            ),
            # Include assistant message ID for feedback support
            assistant_message_id=assistant_message_id or None,
            # Report the model that actually produced the response.
            model=model or None,
            threading=threading_metadata or None,
            # Only include audio for non-streaming mode
            audio=(
                base64.b64encode(audio_data).decode('utf-8')
                if audio_data and not (state.sentence_detector and state.audio_chunks_sent > 0)
                else None
            ),
            audio_format=audio_format_str or None,
            image=image or None,
            image_format=image_format or None,
            image_revised_prompt=image_revised_prompt or None,
            image_url=image_url or None,
            video_url=video_url or None,
            video_format=video_format or None,
            video_revised_prompt=video_revised_prompt or None,
            document_url=document_url or None,
            document_format=document_format or None,
            document_revised_prompt=document_revised_prompt or None,
            generated_audio_url=generated_audio_url or None,
            generated_audio_format=generated_audio_format or None,
            generated_audio_revised_prompt=generated_audio_revised_prompt or None,
        )

        if threading_metadata:
            logger.debug(f"Including threading metadata in done chunk: {threading_metadata}")
        logger.debug(
            f"Preparing done chunk: audio_data={audio_data is not None}, "
            f"audio_format_str={audio_format_str}, "
            f"total_audio_chunks={state.audio_chunks_sent if state.sentence_detector else 0}"
        )
        if event.audio:
            logger.debug(f"Including audio in done chunk: {len(event.audio)} chars (base64)")

        return event

    def build_done_chunk(
        self,
        state: StreamingState,
        audio_data: Optional[bytes] = None,
        audio_format_str: Optional[str] = None,
        threading_metadata: Optional[dict[str, Any]] = None,
        assistant_message_id: Optional[str] = None,
        model: Optional[str] = None,
        image: Optional[str] = None,
        image_format: Optional[str] = None,
        image_revised_prompt: Optional[str] = None,
        image_url: Optional[str] = None,
        video_url: Optional[str] = None,
        video_format: Optional[str] = None,
        video_revised_prompt: Optional[str] = None,
        document_url: Optional[str] = None,
        document_format: Optional[str] = None,
        document_revised_prompt: Optional[str] = None,
        generated_audio_url: Optional[str] = None,
        generated_audio_format: Optional[str] = None,
        generated_audio_revised_prompt: Optional[str] = None,
    ) -> str:
        """
        Build the final done chunk with all metadata. Thin SSE-formatting
        wrapper around `build_done_event`.

        Returns:
            Formatted done chunk string
        """
        event = self.build_done_event(
            state=state,
            audio_data=audio_data,
            audio_format_str=audio_format_str,
            threading_metadata=threading_metadata,
            assistant_message_id=assistant_message_id,
            model=model,
            image=image,
            image_format=image_format,
            image_revised_prompt=image_revised_prompt,
            image_url=image_url,
            video_url=video_url,
            video_format=video_format,
            video_revised_prompt=video_revised_prompt,
            document_url=document_url,
            document_format=document_format,
            document_revised_prompt=document_revised_prompt,
            generated_audio_url=generated_audio_url,
            generated_audio_format=generated_audio_format,
            generated_audio_revised_prompt=generated_audio_revised_prompt,
        )
        formatted = format_stream_event(event)

        logger.debug(f"Yielding done chunk: {len(formatted)} bytes total")
        logger.debug(f"Done chunk has audio: {event.audio is not None}")
        logger.debug(f"Done chunk JSON preview: {formatted[:200]}...")

        return formatted
