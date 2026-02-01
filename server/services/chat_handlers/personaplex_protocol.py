"""
PersonaPlex Protocol Translator

Translates between ORBIT's JSON/base64 WebSocket protocol and PersonaPlex's
binary Opus protocol.

PersonaPlex Binary Protocol:
- 0x00: Handshake (server -> client after connection)
- 0x01: Audio data (Opus codec, bidirectional)
- 0x02: Text tokens (UTF-8 encoded, server -> client)
- 0x03: Control messages (start, endTurn, pause, restart)
- 0x04: Metadata (JSON payload)
- 0x05: Error (UTF-8 error message)
- 0x06: Ping/Pong

ORBIT Protocol:
- JSON messages with base64-encoded audio
- Message types: audio_chunk, transcription, connected, done, interrupted, error
"""

import base64
import json
import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Try to import sphn for Opus codec support
try:
    import sphn
    HAS_SPHN = True
except ImportError:
    HAS_SPHN = False
    logger.warning("sphn not available, Opus codec support disabled")


class PersonaPlexMessageType(IntEnum):
    """PersonaPlex binary protocol message types."""
    HANDSHAKE = 0x00
    AUDIO = 0x01
    TEXT = 0x02
    CONTROL = 0x03
    METADATA = 0x04
    ERROR = 0x05
    PING = 0x06


class PersonaPlexControlCode(IntEnum):
    """PersonaPlex control message codes."""
    START = 0x00
    END_TURN = 0x01
    PAUSE = 0x02
    RESTART = 0x03


@dataclass
class PersonaPlexMessage:
    """Parsed PersonaPlex binary message."""
    type: PersonaPlexMessageType
    payload: bytes
    text: Optional[str] = None
    control_code: Optional[PersonaPlexControlCode] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class OrbitMessage:
    """Parsed ORBIT JSON message."""
    type: str
    data: Optional[str] = None  # base64 encoded audio
    text: Optional[str] = None
    format: Optional[str] = None
    sample_rate: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class PersonaPlexProtocolTranslator:
    """
    Translates between ORBIT's JSON/base64 protocol and PersonaPlex's binary Opus protocol.

    This class handles:
    - Encoding PCM audio to Opus for PersonaPlex
    - Decoding Opus audio from PersonaPlex to PCM
    - Converting ORBIT JSON messages to PersonaPlex binary
    - Converting PersonaPlex binary messages to ORBIT JSON
    """

    def __init__(
        self,
        sample_rate: int = 32000,
        channels: int = 1
    ):
        """
        Initialize the protocol translator.

        Args:
            sample_rate: Audio sample rate (PersonaPlex uses 32000 Hz)
            channels: Number of audio channels (PersonaPlex uses mono)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        # Opus only supports: 8000, 12000, 16000, 24000, 48000 Hz
        # Use 24000 Hz for Opus codec (closest to 32000 that's supported)
        self.opus_sample_rate = 24000

        # Initialize Opus codec if available
        self._opus_encoder: Optional[Any] = None
        self._opus_decoder: Optional[Any] = None

        if HAS_SPHN:
            self._init_opus_codec()

    def _init_opus_codec(self):
        """Initialize Opus encoder and decoder."""
        try:
            # Use opus_sample_rate (24000 Hz) which is supported by Opus
            self._opus_encoder = sphn.OpusStreamWriter(self.opus_sample_rate)
            self._opus_decoder = sphn.OpusStreamReader(self.opus_sample_rate)
            logger.debug(f"Opus codec initialized at {self.opus_sample_rate} Hz")
        except Exception as e:
            logger.error(f"Failed to initialize Opus codec: {e}")
            self._opus_encoder = None
            self._opus_decoder = None

    def encode_audio_to_opus(self, pcm_data: bytes) -> bytes:
        """
        Encode PCM audio to Opus format for PersonaPlex.

        Args:
            pcm_data: PCM audio data (float32, mono)

        Returns:
            Opus-encoded audio data
        """
        if not HAS_SPHN or self._opus_encoder is None:
            # Return raw PCM if Opus not available
            logger.warning("Opus encoder not available, returning raw PCM")
            return pcm_data

        try:
            import numpy as np

            # Ensure alignment to float32 (4 bytes)
            aligned_len = (len(pcm_data) // 4) * 4
            if aligned_len == 0:
                return b''
            if aligned_len < len(pcm_data):
                pcm_data = pcm_data[:aligned_len]

            # Convert bytes to numpy array
            pcm_array = np.frombuffer(pcm_data, dtype=np.float32)

            # Encode to Opus - append_pcm returns the encoded bytes directly
            opus_data = self._opus_encoder.append_pcm(pcm_array)

            return opus_data if opus_data is not None else b''
        except Exception as e:
            logger.error(f"Opus encoding failed: {e}")
            return pcm_data

    def decode_opus_to_pcm(self, opus_data: bytes) -> bytes:
        """
        Decode Opus audio from PersonaPlex to PCM format.

        Args:
            opus_data: Opus-encoded audio data

        Returns:
            PCM audio data (float32, mono)
        """
        if not HAS_SPHN or self._opus_decoder is None:
            # Return raw data if Opus not available
            # Ensure alignment to float32 (4 bytes)
            logger.warning("Opus decoder not available, returning raw data")
            aligned_len = (len(opus_data) // 4) * 4
            if aligned_len > 0 and aligned_len < len(opus_data):
                return opus_data[:aligned_len]
            return opus_data if aligned_len > 0 else b''

        try:
            # Decode from Opus - append_bytes returns PCM numpy array directly
            pcm_array = self._opus_decoder.append_bytes(opus_data)

            if pcm_array is None or len(pcm_array) == 0:
                logger.debug(f"Opus decoder returned empty (input was {len(opus_data)} bytes)")
                return b''

            logger.debug(f"Opus decoded: {len(opus_data)} bytes -> {len(pcm_array)} samples")
            return pcm_array.astype('float32').tobytes()
        except Exception as e:
            logger.error(f"Opus decoding failed: {e}")
            # Return aligned data on error
            aligned_len = (len(opus_data) // 4) * 4
            return opus_data[:aligned_len] if aligned_len > 0 else b''

    def orbit_to_personaplex(self, orbit_message: Union[str, Dict]) -> bytes:
        """
        Convert an ORBIT JSON message to PersonaPlex binary format.

        Args:
            orbit_message: ORBIT message (JSON string or dict)

        Returns:
            PersonaPlex binary message
        """
        if isinstance(orbit_message, str):
            orbit_message = json.loads(orbit_message)

        msg_type = orbit_message.get("type", "")

        if msg_type == "audio_chunk":
            # Decode base64 audio and encode to Opus
            audio_b64 = orbit_message.get("data", "")
            if audio_b64:
                pcm_data = base64.b64decode(audio_b64)
                opus_data = self.encode_audio_to_opus(pcm_data)
                return bytes([PersonaPlexMessageType.AUDIO]) + opus_data
            return b''

        elif msg_type == "interrupt":
            # Send pause control message
            return bytes([
                PersonaPlexMessageType.CONTROL,
                PersonaPlexControlCode.PAUSE
            ])

        elif msg_type == "ping":
            return bytes([PersonaPlexMessageType.PING])

        else:
            logger.warning(f"Unknown ORBIT message type: {msg_type}")
            return b''

    def personaplex_to_orbit(self, pp_message: bytes) -> Dict[str, Any]:
        """
        Convert a PersonaPlex binary message to ORBIT JSON format.

        Args:
            pp_message: PersonaPlex binary message

        Returns:
            ORBIT message dictionary
        """
        if not pp_message:
            return {"type": "empty"}

        msg_type = pp_message[0]
        payload = pp_message[1:] if len(pp_message) > 1 else b''

        if msg_type == PersonaPlexMessageType.HANDSHAKE:
            return {
                "type": "connected",
                "mode": "full_duplex",
                "protocol": "personaplex"
            }

        elif msg_type == PersonaPlexMessageType.AUDIO:
            # Decode Opus to PCM and encode to base64
            pcm_data = self.decode_opus_to_pcm(payload)
            audio_b64 = base64.b64encode(pcm_data).decode('utf-8')
            return {
                "type": "audio_chunk",
                "data": audio_b64,
                "format": "pcm",
                "sample_rate": self.sample_rate
            }

        elif msg_type == PersonaPlexMessageType.TEXT:
            # Decode UTF-8 text
            text = payload.decode('utf-8')
            return {
                "type": "transcription",
                "text": text
            }

        elif msg_type == PersonaPlexMessageType.CONTROL:
            control_code = payload[0] if payload else 0
            if control_code == PersonaPlexControlCode.END_TURN:
                return {"type": "done"}
            elif control_code == PersonaPlexControlCode.PAUSE:
                return {"type": "interrupted", "reason": "model_pause"}
            else:
                return {"type": "control", "code": control_code}

        elif msg_type == PersonaPlexMessageType.METADATA:
            try:
                metadata = json.loads(payload.decode('utf-8'))
                return {"type": "metadata", "data": metadata}
            except json.JSONDecodeError:
                return {"type": "metadata", "data": {}}

        elif msg_type == PersonaPlexMessageType.ERROR:
            error_msg = payload.decode('utf-8')
            return {"type": "error", "message": error_msg}

        elif msg_type == PersonaPlexMessageType.PING:
            return {"type": "pong"}

        else:
            logger.warning(f"Unknown PersonaPlex message type: {msg_type}")
            return {"type": "unknown", "raw_type": msg_type}

    def parse_personaplex_message(self, data: bytes) -> PersonaPlexMessage:
        """
        Parse a PersonaPlex binary message into a structured format.

        Args:
            data: Raw binary message

        Returns:
            Parsed PersonaPlexMessage
        """
        if not data:
            return PersonaPlexMessage(
                type=PersonaPlexMessageType.ERROR,
                payload=b'',
                text="Empty message"
            )

        msg_type = PersonaPlexMessageType(data[0])
        payload = data[1:] if len(data) > 1 else b''

        message = PersonaPlexMessage(type=msg_type, payload=payload)

        if msg_type == PersonaPlexMessageType.TEXT:
            message.text = payload.decode('utf-8')
        elif msg_type == PersonaPlexMessageType.CONTROL and payload:
            message.control_code = PersonaPlexControlCode(payload[0])
        elif msg_type == PersonaPlexMessageType.METADATA:
            try:
                message.metadata = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                pass

        return message

    def create_handshake_response(
        self,
        adapter_name: str,
        session_id: str,
        audio_format: str = "opus"
    ) -> Dict[str, Any]:
        """
        Create ORBIT-style connection confirmation message.

        Args:
            adapter_name: Name of the adapter
            session_id: Session ID
            audio_format: Audio format being used

        Returns:
            ORBIT connection message
        """
        return {
            "type": "connected",
            "adapter": adapter_name,
            "session_id": session_id,
            "mode": "full_duplex",
            "audio_format": audio_format,
            "sample_rate": self.sample_rate,
            "capabilities": {
                "full_duplex": True,
                "interruption": True,
                "backchannels": True
            }
        }

    def reset(self):
        """Reset codec state for new session."""
        if HAS_SPHN:
            self._init_opus_codec()


class PersonaPlexURLBuilder:
    """Helper class to build PersonaPlex WebSocket URLs with query parameters."""

    @staticmethod
    def build_url(
        base_url: str,
        voice_prompt: Optional[str] = None,
        text_prompt: Optional[str] = None,
        seed: Optional[int] = None
    ) -> str:
        """
        Build PersonaPlex WebSocket URL with query parameters.

        Args:
            base_url: Base WebSocket URL (e.g., "wss://localhost:8998/api/chat")
            voice_prompt: Voice embedding file name
            text_prompt: System/role prompt
            seed: Optional random seed for reproducibility

        Returns:
            Full URL with query parameters
        """
        from urllib.parse import urlencode, urlparse, urlunparse

        parsed = urlparse(base_url)
        params = {}

        if voice_prompt:
            params['voice_prompt'] = voice_prompt
        if text_prompt:
            params['text_prompt'] = text_prompt
        if seed is not None:
            params['seed'] = str(seed)

        query_string = urlencode(params) if params else ''
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query_string,
            parsed.fragment
        ))

        return new_url
