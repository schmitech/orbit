"""
PersonaPlex WebSocket Handler

Full-duplex WebSocket handler for PersonaPlex voice conversations.

Key differences from VoiceWebSocketHandler:
1. No STT -> LLM -> TTS cascade - PersonaPlex is speech-to-speech
2. Full-duplex: audio flows in both directions simultaneously
3. Protocol translation between ORBIT JSON/base64 and PersonaPlex binary/Opus
4. Sample rate conversion (24kHz ORBIT <-> 32kHz PersonaPlex)

Message Flow:
    Client (24kHz) -> [resample] -> [encode] -> PersonaPlex (32kHz)
    PersonaPlex (32kHz) -> [decode] -> [resample] -> Client (24kHz)
"""

import asyncio
import base64
import json
import logging
from typing import Any, Dict, Optional
import uuid

from fastapi import WebSocket, WebSocketDisconnect

from .audio_resampler import AudioResampler
from .personaplex_protocol import PersonaPlexProtocolTranslator

logger = logging.getLogger(__name__)


class PersonaPlexWebSocketHandler:
    """
    WebSocket handler for PersonaPlex full-duplex voice conversations.

    This handler manages bidirectional audio streaming between ORBIT clients
    and the PersonaPlex speech-to-speech model, handling:
    - Protocol translation (JSON/base64 <-> binary/Opus)
    - Sample rate conversion (24kHz <-> 32kHz)
    - Concurrent send/receive loops for full-duplex operation
    - Session lifecycle management
    """

    def __init__(
        self,
        websocket: WebSocket,
        personaplex_service: Any,
        adapter_name: str,
        adapter_config: Dict[str, Any],
        config: Dict[str, Any],
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """
        Initialize the handler.

        Args:
            websocket: FastAPI WebSocket connection
            personaplex_service: PersonaPlex service instance
            adapter_name: Name of the adapter
            adapter_config: Adapter-specific configuration
            config: Global configuration
            session_id: Optional ORBIT session ID
            user_id: Optional user ID
        """
        self.websocket = websocket
        self.personaplex_service = personaplex_service
        self.adapter_name = adapter_name
        self.adapter_config = adapter_config
        self.config = config
        self.orbit_session_id = session_id or str(uuid.uuid4())
        self.user_id = user_id

        # PersonaPlex session ID (created on initialize)
        self.pp_session_id: Optional[str] = None

        # Audio settings from adapter config
        handler_config = adapter_config.get('config', {})
        self.orbit_sample_rate = handler_config.get('orbit_sample_rate', 24000)
        self.pp_sample_rate = handler_config.get('personaplex_sample_rate', 32000)
        self.audio_chunk_size_ms = handler_config.get('audio_chunk_size_ms', 80)

        # Protocol translator
        self.protocol = PersonaPlexProtocolTranslator(sample_rate=self.pp_sample_rate)

        # Audio resampler
        self.resampler = AudioResampler(
            orbit_rate=self.orbit_sample_rate,
            personaplex_rate=self.pp_sample_rate,
            dtype="float32"
        )

        # State
        self.is_connected = False
        self.is_processing = False
        self._receive_task: Optional[asyncio.Task] = None
        self._send_task: Optional[asyncio.Task] = None
        self._output_queue: asyncio.Queue = asyncio.Queue()
        self._text_queue: asyncio.Queue = asyncio.Queue()

        # Statistics
        self._frames_sent = 0
        self._frames_received = 0

    async def initialize(self) -> bool:
        """
        Initialize PersonaPlex session with persona from adapter config.

        Returns:
            True if initialization successful
        """
        try:
            # Get persona configuration from adapter
            persona_config = self.adapter_config.get('persona', {})
            voice_prompt = persona_config.get('voice_prompt')
            text_prompt = persona_config.get('text_prompt')

            logger.info(
                f"Creating PersonaPlex session for adapter '{self.adapter_name}' "
                f"(voice: {voice_prompt})"
            )

            # Create PersonaPlex session
            self.pp_session_id = await self.personaplex_service.create_session(
                voice_prompt=voice_prompt,
                text_prompt=text_prompt
            )

            logger.debug(f"PersonaPlex session created: {self.pp_session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize PersonaPlex session: {e}")
            return False

    async def accept_connection(self):
        """Accept WebSocket connection and send confirmation."""
        await self.websocket.accept()
        self.is_connected = True

        # Send ORBIT-style connection message
        await self._send_message({
            "type": "connected",
            "adapter": self.adapter_name,
            "session_id": self.orbit_session_id,
            "mode": "full_duplex",
            "audio_format": "pcm",
            "sample_rate": self.orbit_sample_rate,
            "capabilities": {
                "full_duplex": True,
                "interruption": True,
                "backchannels": True
            }
        })

        logger.info(
            f"WebSocket connection accepted for PersonaPlex adapter '{self.adapter_name}' "
            f"(session: {self.orbit_session_id})"
        )

    async def run(self):
        """
        Main handler loop.

        Runs concurrent receive and send tasks for full-duplex operation.
        """
        try:
            # Initialize PersonaPlex session
            if not await self.initialize():
                await self._send_error("Failed to initialize PersonaPlex session")
                return

            # Accept WebSocket connection
            await self.accept_connection()

            # Start concurrent tasks for full-duplex
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._send_task = asyncio.create_task(self._send_loop())

            # Optional: task to forward text tokens
            text_task = asyncio.create_task(self._text_loop())

            # Wait for any task to complete (usually means disconnect)
            done, pending = await asyncio.wait(
                [self._receive_task, self._send_task, text_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: {self.orbit_session_id}")
        except Exception as e:
            logger.error(f"Handler error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()

    async def _receive_loop(self):
        """
        Receive audio from ORBIT client and forward to PersonaPlex.

        This loop handles incoming messages from the client, converting
        them to PersonaPlex format and processing through the model.
        """
        self.is_processing = True

        while self.is_connected:
            try:
                # Receive message from client
                data = await self.websocket.receive_text()
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "audio_chunk":
                    await self._handle_audio_chunk(message)

                elif msg_type == "interrupt":
                    await self._handle_interrupt()

                elif msg_type == "ping":
                    await self._send_message({"type": "pong"})

                elif msg_type == "end":
                    logger.info(f"Client ended session: {self.orbit_session_id}")
                    self.is_connected = False
                    break

                else:
                    logger.debug(f"Unknown message type: {msg_type}")

            except WebSocketDisconnect:
                self.is_connected = False
                break
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON received: {e}")
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")

        self.is_processing = False

    async def _handle_audio_chunk(self, message: Dict[str, Any]):
        """
        Handle incoming audio chunk from client.

        Args:
            message: Audio chunk message with base64-encoded data
        """
        audio_b64 = message.get("data", "")
        if not audio_b64:
            return

        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(audio_b64)

            # Convert from int16 to float32 if needed
            audio_format = message.get("format", "pcm")
            if audio_format == "int16" or audio_format == "wav":
                audio_bytes = self.resampler.convert_int16_to_float32(audio_bytes)

            # Opus encoder uses 24kHz (ORBIT client rate), so no resampling needed
            # PersonaPlex/Moshi server expects 24kHz Opus audio
            # Only encode to Opus - skip resampling
            opus_frame = self.protocol.encode_audio_to_opus(audio_bytes)

            self._frames_received += 1

            # Process through PersonaPlex
            async for output_opus in self.personaplex_service.process_audio_frame(
                self.pp_session_id,
                opus_frame,
                self.orbit_sample_rate  # Use ORBIT rate (24kHz) for Opus stream
            ):
                # Queue output for send loop
                await self._output_queue.put(output_opus)

        except Exception as e:
            logger.error(f"Error processing audio chunk: {e}")

    async def _handle_interrupt(self):
        """Handle interrupt request from client."""
        logger.info(f"Interrupt requested: {self.orbit_session_id}")

        try:
            # Signal interruption to PersonaPlex
            await self.personaplex_service.interrupt(self.pp_session_id)

            # Clear output queue
            while not self._output_queue.empty():
                try:
                    self._output_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Notify client
            await self._send_message({
                "type": "interrupted",
                "reason": "user_request"
            })

        except Exception as e:
            logger.error(f"Error handling interrupt: {e}")

    async def _send_loop(self):
        """
        Send PersonaPlex audio back to ORBIT client.

        This loop processes the output queue and sends audio chunks
        to the client, converting from PersonaPlex format.
        """
        while self.is_connected:
            try:
                # Wait for output from PersonaPlex
                opus_frame = await asyncio.wait_for(
                    self._output_queue.get(),
                    timeout=0.1
                )

                # Decode Opus to PCM (already at 24kHz from Opus decoder)
                pcm_orbit = self.protocol.decode_opus_to_pcm(opus_frame)

                # No resampling needed - Opus output is already at ORBIT rate (24kHz)

                # Skip empty audio
                if not pcm_orbit or len(pcm_orbit) == 0:
                    continue

                # Send to client as base64-encoded JSON
                await self._send_message({
                    "type": "audio_chunk",
                    "data": base64.b64encode(pcm_orbit).decode('utf-8'),
                    "format": "pcm",
                    "sample_rate": self.orbit_sample_rate,
                    "chunk_index": self._frames_sent
                })

                self._frames_sent += 1

                if self._frames_sent % 50 == 0:
                    logger.debug(f"Sent {self._frames_sent} audio frames to client")

            except asyncio.TimeoutError:
                # No output available, continue waiting
                continue
            except Exception as e:
                logger.error(f"Error in send loop: {e}")

    async def _text_loop(self):
        """
        Forward text tokens from PersonaPlex to client.

        Optional loop that sends transcription updates as the model generates text.
        """
        while self.is_connected:
            try:
                # Get text tokens from PersonaPlex
                async for token in self.personaplex_service.get_text_tokens(
                    self.pp_session_id
                ):
                    # Send transcription update
                    await self._send_message({
                        "type": "transcription",
                        "text": token,
                        "partial": True
                    })

                # Small delay between checks
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.debug(f"Text loop error: {e}")
                await asyncio.sleep(0.1)

    async def _send_message(self, message: Dict[str, Any]):
        """
        Send JSON message to client.

        Args:
            message: Message dictionary to send
        """
        try:
            await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.is_connected = False

    async def _send_error(self, error_message: str):
        """
        Send error message to client.

        Args:
            error_message: Error description
        """
        await self._send_message({
            "type": "error",
            "message": error_message
        })

    async def cleanup(self):
        """Clean up resources when connection closes."""
        self.is_connected = False

        # Close PersonaPlex session
        if self.pp_session_id:
            try:
                await self.personaplex_service.close_session(self.pp_session_id)
                logger.debug(f"PersonaPlex session closed: {self.pp_session_id}")
            except Exception as e:
                logger.error(f"Error closing PersonaPlex session: {e}")

        # Reset protocol state
        self.protocol.reset()

        logger.info(
            f"PersonaPlex handler cleanup complete "
            f"(sent: {self._frames_sent}, received: {self._frames_received})"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get handler statistics.

        Returns:
            Dictionary with handler statistics
        """
        return {
            "orbit_session_id": self.orbit_session_id,
            "pp_session_id": self.pp_session_id,
            "adapter_name": self.adapter_name,
            "is_connected": self.is_connected,
            "is_processing": self.is_processing,
            "frames_sent": self._frames_sent,
            "frames_received": self._frames_received,
            "output_queue_size": self._output_queue.qsize()
        }
