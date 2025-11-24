"""
Voice WebSocket Handler

Orchestrates real-time voice conversations via WebSocket.
Manages audio input/output, coordinates with chat service, and handles interruptions.
"""

import logging
import asyncio
import json
import base64
from typing import Optional, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from .audio_input_processor import AudioInputProcessor
from .audio_output_streamer import AudioOutputStreamer
from .streaming_handler import StreamingHandler
from .audio_handler import AudioHandler

logger = logging.getLogger(__name__)


class VoiceWebSocketHandler:
    """Handles WebSocket-based voice conversation sessions."""

    def __init__(
        self,
        websocket: WebSocket,
        chat_service,
        adapter_name: str,
        config: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Initialize the voice WebSocket handler.

        Args:
            websocket: FastAPI WebSocket connection
            chat_service: PipelineChatService for LLM interactions
            adapter_name: Name of the adapter to use
            config: Application configuration
            session_id: Optional session ID for conversation history
            user_id: Optional user ID
        """
        self.websocket = websocket
        self.chat_service = chat_service
        self.adapter_name = adapter_name
        self.config = config
        self.session_id = session_id
        self.user_id = user_id

        # Get adapter config
        self.adapter_config = self._get_adapter_config()

        # Audio configuration from adapter
        self.config_settings = self.adapter_config.get("config", {})
        self.audio_format = self.config_settings.get("tts_format", "wav")
        self.tts_voice = self.config_settings.get("tts_voice")
        self.language = self.config_settings.get("stt_language", "en")
        self.chunk_size_ms = self.config_settings.get("audio_chunk_size_ms", 100)
        self.silence_threshold = self.config_settings.get("silence_threshold", 0.01)
        self.min_speech_duration_ms = self.config_settings.get("min_speech_duration_ms", 300)
        self.max_speech_duration_ms = self.config_settings.get("max_speech_duration_ms", 10000)
        self.silence_duration_ms = self.config_settings.get("silence_duration_ms", 500)
        self.auto_interrupt_enabled = self.config_settings.get("enable_interruption", False)
        self.sample_rate_hz = self.config_settings.get("stt_sample_rate", 24000)
        self.audio_sample_width_bytes = self.config_settings.get("audio_sample_width_bytes", 2)
        self.audio_input_channels = self.config_settings.get("audio_input_channels", 1)

        # Get audio providers - support separate STT and TTS providers
        # For backward compatibility, default to audio_provider for both
        self.audio_provider = self.adapter_config.get("audio_provider", "gemini")
        self.stt_provider = self.adapter_config.get("stt_provider", self.audio_provider)
        self.tts_provider = self.adapter_config.get("tts_provider", self.audio_provider)

        # Initialize audio services
        self.stt_service = None  # For speech-to-text
        self.tts_service = None  # For text-to-speech (if needed separately)

        # Initialize processors
        self.input_processor = None  # Will be initialized after audio service is ready
        self.output_streamer = None  # Will be initialized after streaming handler is ready

        # State management
        self.is_connected = False
        self.is_processing = False
        self.llm_task: Optional[asyncio.Task] = None
        self.interruption_event = asyncio.Event()

        # Connection stats
        self.messages_received = 0
        self.messages_sent = 0
        self.errors = 0

    def _get_adapter_config(self) -> Dict[str, Any]:
        """
        Get adapter configuration.

        Returns:
            Adapter configuration dictionary
        """
        if hasattr(self.chat_service, 'context_builder') and self.chat_service.context_builder:
            adapter_manager = self.chat_service.context_builder.adapter_manager
            if adapter_manager:
                config = adapter_manager.get_adapter_config(self.adapter_name)
                if config:
                    return config

        logger.warning(f"No adapter config found for {self.adapter_name}, using defaults")
        return {}

    async def _initialize_audio_service(self):
        """Initialize the audio services for STT and TTS."""
        try:
            from ai_services.factory import AIServiceFactory
            from ai_services.base import ServiceType
            from ai_services.registry import register_all_services

            # Ensure services are registered
            register_all_services(self.config)

            # Create STT audio service
            self.stt_service = AIServiceFactory.create_service(
                ServiceType.AUDIO,
                self.stt_provider,
                self.config
            )

            if not self.stt_service:
                raise ValueError(f"Failed to create STT audio service for provider: {self.stt_provider}")

            # Initialize STT service
            if hasattr(self.stt_service, 'initialize'):
                await self.stt_service.initialize()

            logger.info(f"STT service initialized: {self.stt_provider}")

            # TTS is handled by StreamingHandler which uses the adapter's audio_provider
            # No need to initialize separate TTS service here

        except Exception as e:
            logger.error(f"Failed to initialize audio services: {str(e)}", exc_info=True)
            raise

    async def initialize(self):
        """Initialize the handler and its components."""
        try:
            # Initialize audio service
            await self._initialize_audio_service()

            # Initialize audio input processor with STT service
            self.input_processor = AudioInputProcessor(
                audio_service=self.stt_service,
                chunk_size_ms=self.chunk_size_ms,
                silence_threshold=self.silence_threshold,
                min_speech_duration_ms=self.min_speech_duration_ms,
                max_speech_duration_ms=self.max_speech_duration_ms,
                silence_duration_ms=self.silence_duration_ms,
                sample_rate_hz=self.sample_rate_hz,
                sample_width_bytes=self.audio_sample_width_bytes,
                channels=self.audio_input_channels
            )

            # Initialize audio output streamer
            # Use existing streaming handler from chat service
            self.output_streamer = AudioOutputStreamer(
                streaming_handler=self.chat_service.streaming_handler
            )

            logger.info(
                f"Voice WebSocket handler initialized for adapter: {self.adapter_name}, "
                f"STT provider: {self.stt_provider}, TTS provider: {self.tts_provider}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize voice handler: {str(e)}", exc_info=True)
            raise

    async def accept_connection(self):
        """Accept the WebSocket connection."""
        try:
            await self.websocket.accept()
            self.is_connected = True
            logger.info(
                f"WebSocket connection accepted for session: {self.session_id or 'new'}, "
                f"adapter: {self.adapter_name}"
            )

            # Send connection confirmation
            await self.send_message({
                "type": "connected",
                "adapter": self.adapter_name,
                "session_id": self.session_id,
                "audio_format": self.audio_format
            })

        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {str(e)}")
            raise

    async def send_message(self, message: Dict[str, Any]):
        """
        Send a message to the WebSocket client.

        Args:
            message: Message dictionary to send
        """
        if not self.is_connected:
            logger.debug("Skipping send_message; WebSocket already disconnected")
            return

        try:
            await self.websocket.send_json(message)
            self.messages_sent += 1
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected while sending message")
            self.is_connected = False
            self.errors += 1
            raise
        except RuntimeError as e:
            # Happens if we try to send after close
            logger.info(f"WebSocket runtime error while sending message: {str(e)}")
            self.is_connected = False
            self.errors += 1
            raise
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {str(e)}")
            self.errors += 1
            raise

    async def send_error(self, error_message: str):
        """
        Send an error message to the client.

        Args:
            error_message: Error message string
        """
        if not self.is_connected:
            logger.debug(f"Cannot send error message (disconnected): {error_message}")
            return

        try:
            await self.send_message({
                "type": "error",
                "message": error_message
            })
        except Exception:
            logger.error(f"Failed to send error message: {error_message}")

    async def handle_audio_chunk(self, message: Dict[str, Any]):
        """
        Handle incoming audio chunk from client.

        Args:
            message: Message containing audio chunk
        """
        try:
            # Extract audio data
            audio_data_b64 = message.get("data")
            audio_format = message.get("format", self.audio_format)

            if not audio_data_b64:
                logger.warning("Received empty audio chunk")
                return

            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_data_b64)

            # If the assistant is speaking and auto interruption is disabled,
            # ignore microphone input to prevent feedback loops
            if self.is_processing and not self.interruption_event.is_set():
                if not self.auto_interrupt_enabled:
                    logger.debug(
                        "Ignoring audio chunk while assistant is speaking "
                        "(auto interruption disabled)"
                    )
                    return

                logger.info("User interrupted LLM response")
                await self.interrupt_llm()

            # Add chunk to buffer
            self.input_processor.add_chunk(audio_bytes)

            # Check if buffer is ready for STT processing
            if self.input_processor.should_process_buffer():
                # Process speech to text
                transcription = await self.input_processor.process_buffered_speech(
                    audio_format=audio_format,
                    language=self.language
                )

                if transcription:
                    logger.info(f"User said: {transcription}")

                    # Send transcription to client (optional)
                    await self.send_message({
                        "type": "transcription",
                        "text": transcription
                    })

                    # Process through LLM and generate audio response
                    await self.process_user_message(transcription)

        except Exception as e:
            logger.error(f"Error handling audio chunk: {str(e)}", exc_info=True)
            await self.send_error(f"Audio processing error: {str(e)}")

    async def handle_interrupt(self):
        """Handle interruption signal from client."""
        try:
            logger.info("Received explicit interrupt signal from client")
            await self.interrupt_llm()
        except Exception as e:
            logger.error(f"Error handling interrupt: {str(e)}", exc_info=True)

    async def interrupt_llm(self):
        """Interrupt the current LLM processing and audio generation."""
        try:
            # Set interruption flag
            self.interruption_event.set()

            # Cancel LLM task if running
            if self.llm_task and not self.llm_task.done():
                self.llm_task.cancel()
                try:
                    await self.llm_task
                except asyncio.CancelledError:
                    logger.debug("LLM task cancelled successfully")

            # Interrupt audio output streamer
            if self.output_streamer:
                self.output_streamer.interrupt()

            # Reset input processor buffer
            if self.input_processor:
                self.input_processor.reset()

            logger.info("LLM and audio generation interrupted")

            # Notify client that interruption was successful
            await self.send_message({
                "type": "interrupted",
                "reason": "user_speech"
            })

        except Exception as e:
            logger.error(f"Error during interruption: {str(e)}", exc_info=True)

    async def process_user_message(self, message_text: str):
        """
        Process user message through LLM and generate audio response.

        Args:
            message_text: Transcribed user message
        """
        try:
            # Mark as processing
            self.is_processing = True
            self.interruption_event.clear()

            # Reset output streamer
            self.output_streamer.reset()

            # Create LLM processing task
            self.llm_task = asyncio.create_task(
                self._process_and_stream_response(message_text)
            )

            # Wait for completion or cancellation
            try:
                await self.llm_task
            except asyncio.CancelledError:
                logger.info("LLM processing cancelled by interruption")

        except Exception as e:
            logger.error(f"Error processing user message: {str(e)}", exc_info=True)
            await self.send_error(f"Message processing error: {str(e)}")
        finally:
            self.is_processing = False
            self.llm_task = None

    async def _process_and_stream_response(self, message_text: str):
        """
        Process message through LLM and stream audio response.

        Args:
            message_text: User message text
        """
        try:
            # Process through chat service with streaming
            logger.debug(f"Processing message: {message_text}")

            # Call pipeline chat service to get LLM stream
            llm_stream = self.chat_service.process_chat_stream(
                message=message_text,
                client_ip="websocket",
                adapter_name=self.adapter_name,
                session_id=self.session_id,
                user_id=self.user_id,
                # Request text-only stream; audio will be generated by the WebSocket path
                return_audio=False,
                tts_voice=self.tts_voice,
                language=self.language
            )

            if not llm_stream:
                logger.error("No LLM stream received from chat service")
                await self.send_error("Failed to get LLM response")
                return

            # Stream audio response to client
            async for audio_chunk in self.output_streamer.stream_audio_response(
                llm_stream=llm_stream,
                adapter_name=self.adapter_name,
                tts_voice=self.tts_voice,
                language=self.language,
                default_audio_format=self.audio_format
            ):
                # Check for interruption
                if self.interruption_event.is_set():
                    logger.info("Streaming interrupted")
                    break

                if not self.is_connected:
                    logger.info("Stopping audio stream because WebSocket disconnected")
                    break

                # Send audio chunk to client
                await self.send_message(audio_chunk)

            # Send done marker if not interrupted and still connected
            if not self.interruption_event.is_set() and self.is_connected:
                await self.send_message({
                    "type": "done",
                    "session_id": self.session_id
                })

        except asyncio.CancelledError:
            logger.info("Response streaming cancelled")
            raise
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected during response streaming")
            self.is_connected = False
        except Exception as e:
            logger.error(f"Error streaming response: {str(e)}", exc_info=True)
            await self.send_error(f"Response streaming error: {str(e)}")

    async def handle_message(self, message: Dict[str, Any]):
        """
        Handle incoming WebSocket message.

        Args:
            message: Parsed message dictionary
        """
        self.messages_received += 1
        message_type = message.get("type")

        try:
            if message_type == "audio_chunk":
                await self.handle_audio_chunk(message)
            elif message_type == "interrupt":
                await self.handle_interrupt()
            elif message_type == "ping":
                await self.send_message({"type": "pong"})
            else:
                logger.warning(f"Unknown message type: {message_type}")

        except Exception as e:
            logger.error(f"Error handling message: {str(e)}", exc_info=True)
            self.errors += 1

    async def run(self):
        """Main WebSocket message loop."""
        try:
            while self.is_connected:
                # Receive message
                data = await self.websocket.receive_text()

                try:
                    message = json.loads(data)
                    await self.handle_message(message)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received: {data[:100]}")
                    await self.send_error("Invalid message format")

        except WebSocketDisconnect:
            logger.info(
                f"WebSocket disconnected. Stats: "
                f"received={self.messages_received}, "
                f"sent={self.messages_sent}, "
                f"errors={self.errors}"
            )
        except Exception as e:
            logger.error(f"Error in WebSocket message loop: {str(e)}", exc_info=True)
        finally:
            self.is_connected = False
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        try:
            logger.debug("Cleaning up voice WebSocket handler")

            # Cancel any running LLM task
            if self.llm_task and not self.llm_task.done():
                self.llm_task.cancel()
                try:
                    await self.llm_task
                except asyncio.CancelledError:
                    pass

            # Clean up input processor
            if self.input_processor:
                self.input_processor.reset()

            # Clean up output streamer
            if self.output_streamer:
                self.output_streamer.reset()

            # Clean up STT audio service
            if self.stt_service and hasattr(self.stt_service, 'close'):
                try:
                    await self.stt_service.close()
                except Exception as e:
                    logger.warning(f"Error closing STT audio service: {str(e)}")

            # TTS service cleanup is handled by StreamingHandler

            logger.info("Voice WebSocket handler cleanup completed")

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True)
