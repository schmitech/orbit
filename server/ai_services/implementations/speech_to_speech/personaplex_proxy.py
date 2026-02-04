"""
PersonaPlex Proxy Service

Connects to a remote PersonaPlex server via WebSocket for speech-to-speech
conversation. This mode is suitable for:
- Multi-server deployments
- Shared GPU resources
- Scaling PersonaPlex independently from ORBIT

The proxy translates ORBIT sessions to PersonaPlex WebSocket connections,
handling protocol conversion and session lifecycle.
"""

import asyncio
import logging
import ssl
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid

from ...services.speech_to_speech_service import SpeechToSpeechService

logger = logging.getLogger(__name__)

# Try to import aiohttp for WebSocket client
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.warning("aiohttp not available, PersonaPlex proxy mode disabled")


class PersonaPlexProxySession:
    """
    Manages a single PersonaPlex proxy session.

    Holds the WebSocket connection and state for one conversation session.
    """

    def __init__(
        self,
        session_id: str,
        ws: "aiohttp.ClientWebSocketResponse",
        http_session: "aiohttp.ClientSession"
    ):
        self.session_id = session_id
        self.ws = ws
        self.http_session = http_session
        self.is_active = True
        self._text_buffer: List[str] = []
        self._audio_queue: asyncio.Queue = asyncio.Queue()

    async def close(self):
        """Close the session and release resources."""
        self.is_active = False
        try:
            await self.ws.close()
        except Exception as e:
            logger.debug(f"Error closing WebSocket: {e}")
        try:
            await self.http_session.close()
        except Exception as e:
            logger.debug(f"Error closing HTTP session: {e}")


class PersonaPlexProxyService(SpeechToSpeechService):
    """
    PersonaPlex service that proxies to a remote PersonaPlex server.

    This service connects to PersonaPlex's native WebSocket API at /api/chat
    and translates between ORBIT's session model and PersonaPlex's connection model.

    Configuration (from config/personaplex.yaml):
        personaplex:
          mode: "proxy"
          proxy:
            server_url: "wss://localhost:8998/api/chat"
            ssl_verify: true
            connection_timeout: 30
    """

    def __init__(self, config: Dict[str, Any], **kwargs):
        """
        Initialize the proxy service.

        Args:
            config: Configuration dictionary containing personaplex settings
            **kwargs: Additional arguments (passed to parent, ignored)
        """
        super().__init__(config, "personaplex_proxy", **kwargs)

        # Extract PersonaPlex config
        pp_config = config.get('personaplex', {})
        proxy_config = pp_config.get('proxy', {})

        self.server_url = proxy_config.get('server_url', 'wss://localhost:8998/api/chat')
        self.ssl_verify = proxy_config.get('ssl_verify', True)
        self.connection_timeout = proxy_config.get('connection_timeout', 30)
        # Handshake timeout should be longer than connection timeout since
        # PersonaPlex server processes system prompts BEFORE sending handshake.
        # Large text_prompts can take 30+ seconds to tokenize and initialize.
        self.handshake_timeout = proxy_config.get('handshake_timeout', 60)
        self.reconnect_attempts = proxy_config.get('reconnect_attempts', 3)
        self.reconnect_delay = proxy_config.get('reconnect_delay', 1.0)
        # Some PersonaPlex servers (e.g., moshi) do not implement control frames.
        # Only send 0x03 control packets when explicitly enabled.
        self.supports_control_messages = proxy_config.get('supports_control_messages', False)

        # Default persona settings
        defaults = pp_config.get('defaults', {})
        self.default_voice = defaults.get('voice_prompt', 'NATF2.pt')
        self.default_text_prompt = defaults.get('text_prompt', '')

        # Active sessions
        self._sessions: Dict[str, PersonaPlexProxySession] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """
        Initialize the proxy service.

        Verifies connectivity to the PersonaPlex server.

        Returns:
            True if initialization successful
        """
        if not HAS_AIOHTTP:
            self.logger.error("aiohttp not installed, cannot use proxy mode")
            return False

        try:
            # Test connection to server
            async with aiohttp.ClientSession() as session:
                # Try to parse the WebSocket URL to get HTTP endpoint
                test_url = self.server_url.replace('wss://', 'https://').replace('ws://', 'http://')
                test_url = test_url.split('/api/chat')[0] + '/health'

                try:
                    async with session.get(
                        test_url,
                        timeout=aiohttp.ClientTimeout(total=5),
                        ssl=self.ssl_verify if self.ssl_verify else False
                    ) as resp:
                        if resp.status == 200:
                            self.logger.info(f"PersonaPlex server reachable at {self.server_url}")
                except aiohttp.ClientError:
                    # Health endpoint might not exist, that's OK
                    self.logger.info(f"PersonaPlex server URL configured: {self.server_url}")

            self.initialized = True
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize PersonaPlex proxy: {e}")
            return False

    async def create_session(
        self,
        voice_prompt: Optional[str] = None,
        text_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Create a new session by establishing WebSocket to PersonaPlex server.

        Args:
            voice_prompt: Voice embedding file (e.g., "NATF2.pt")
            text_prompt: Role/system prompt
            **kwargs: Additional parameters (seed, etc.)

        Returns:
            Session ID for subsequent calls
        """
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp not installed")

        session_id = str(uuid.uuid4())
        voice = voice_prompt or self.default_voice
        text = text_prompt or self.default_text_prompt
        seed = kwargs.get('seed')

        # Build connection URL with query parameters
        from urllib.parse import urlencode
        params = {'voice_prompt': voice}
        if text:
            params['text_prompt'] = text
        if seed is not None:
            params['seed'] = str(seed)

        url = f"{self.server_url}?{urlencode(params)}"

        self.logger.info(f"Creating PersonaPlex session: {session_id}")
        self.logger.debug(f"Connection URL: {url[:100]}...")
        if text:
            prompt_len = len(text)
            self.logger.debug(f"Text prompt length: {prompt_len} chars (handshake timeout: {self.handshake_timeout}s)")

        # Establish WebSocket connection with retries
        for attempt in range(self.reconnect_attempts):
            try:
                http_session = aiohttp.ClientSession()

                # Determine SSL context based on URL scheme and ssl_verify setting
                is_secure = self.server_url.startswith('wss://')
                if is_secure:
                    if self.ssl_verify:
                        # Use default SSL verification
                        ssl_context = None
                    else:
                        # Create SSL context that doesn't verify certificates
                        # (for self-signed certs in development)
                        ssl_context = ssl.create_default_context()
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                else:
                    # Non-secure WebSocket (ws://), no SSL needed
                    ssl_context = False

                ws = await http_session.ws_connect(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.connection_timeout),
                    ssl=ssl_context
                )

                # Wait for handshake (0x00 byte)
                # PersonaPlex processes system prompts before sending handshake,
                # so large text_prompts need a longer timeout here
                msg = await asyncio.wait_for(ws.receive(), timeout=self.handshake_timeout)

                if msg.type == aiohttp.WSMsgType.BINARY:
                    if msg.data and msg.data[0] == 0x00:
                        self.logger.info(f"PersonaPlex handshake received for session {session_id}")

                        # Create session object
                        async with self._lock:
                            self._sessions[session_id] = PersonaPlexProxySession(
                                session_id=session_id,
                                ws=ws,
                                http_session=http_session
                            )

                        return session_id
                    else:
                        self.logger.warning(f"Unexpected message type: {msg.data[0] if msg.data else 'empty'}")
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    self.logger.warning(f"Received text instead of binary: {msg.data[:100]}")
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    self.logger.warning("Connection closed during handshake")

                await ws.close()
                await http_session.close()

            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Handshake timeout after {self.handshake_timeout}s (attempt {attempt + 1}/{self.reconnect_attempts}). "
                    f"If using a large text_prompt, consider increasing handshake_timeout in config."
                )
            except aiohttp.ClientError as e:
                self.logger.warning(f"Connection error (attempt {attempt + 1}): {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error creating session: {e}")

            if attempt < self.reconnect_attempts - 1:
                await asyncio.sleep(self.reconnect_delay)

        raise ConnectionError(f"Failed to connect to PersonaPlex server after {self.reconnect_attempts} attempts")

    async def process_audio_frame(
        self,
        session_id: str,
        audio_frame: bytes,
        sample_rate: int = 32000
    ) -> AsyncIterator[bytes]:
        """
        Send audio to PersonaPlex and yield response audio frames.

        Args:
            session_id: Session ID
            audio_frame: Input audio (Opus or PCM)
            sample_rate: Sample rate (should be 32000 for PersonaPlex)

        Yields:
            Output audio frames from PersonaPlex
        """
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            self.logger.error(f"Session not found or inactive: {session_id}")
            return

        try:
            # Send audio (0x01 prefix for audio)
            await session.ws.send_bytes(b'\x01' + audio_frame)

            # Non-blocking receive of any available responses
            # Use longer timeout to catch audio responses from PersonaPlex
            messages_received = 0
            while True:
                try:
                    # Use 10ms timeout - balance between latency and catching responses
                    msg = await asyncio.wait_for(session.ws.receive(), timeout=0.01)

                    if msg.type == aiohttp.WSMsgType.BINARY:
                        if not msg.data:
                            continue

                        msg_type = msg.data[0]
                        payload = msg.data[1:] if len(msg.data) > 1 else b''

                        if msg_type == 0x01:  # Audio
                            messages_received += 1
                            if messages_received == 1:
                                # Log first audio payload details for debugging
                                self.logger.debug(f"First audio payload: {len(payload)} bytes, starts with: {payload[:20].hex() if len(payload) >= 20 else payload.hex()}")
                            yield payload
                        elif msg_type == 0x02:  # Text token
                            text = payload.decode('utf-8')
                            session._text_buffer.append(text)
                        elif msg_type == 0x03:  # Control
                            # Handle control messages
                            pass

                    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                        session.is_active = False
                        break

                except asyncio.TimeoutError:
                    # No more messages available right now
                    break

            if messages_received > 0:
                self.logger.debug(f"Received {messages_received} audio frames from PersonaPlex")

        except Exception as e:
            self.logger.error(f"Error processing audio frame: {e}")
            session.is_active = False

    async def get_text_tokens(self, session_id: str) -> AsyncIterator[str]:
        """
        Yield accumulated text tokens for a session.

        Args:
            session_id: Session ID

        Yields:
            Text tokens as strings
        """
        session = self._sessions.get(session_id)
        if not session:
            return

        while session._text_buffer:
            yield session._text_buffer.pop(0)

    async def close_session(self, session_id: str) -> None:
        """
        Close a session and its WebSocket connection.

        Args:
            session_id: Session ID to close
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session:
            self.logger.debug(f"Closing PersonaPlex session: {session_id}")
            await session.close()

    async def interrupt(self, session_id: str) -> None:
        """
        Send interrupt/pause signal to PersonaPlex.

        Args:
            session_id: Session ID to interrupt
        """
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            return

        if not self.supports_control_messages:
            self.logger.debug("Skipping interrupt; remote server does not support control messages")
            return

        try:
            # Send pause control message (0x03 = control, 0x02 = pause)
            await session.ws.send_bytes(bytes([0x03, 0x02]))
            self.logger.debug(f"Sent interrupt to session {session_id}")
        except Exception as e:
            self.logger.error(f"Error sending interrupt: {e}")

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """
        Get list of available voice prompts.

        Returns:
            List of voice info dictionaries
        """
        # Return from config
        pp_config = self.config.get('personaplex', {})
        voices_config = pp_config.get('voices', {})

        voices = []
        for category, voice_list in voices_config.items():
            for voice in voice_list:
                voices.append({
                    'id': voice.get('id'),
                    'name': voice.get('name'),
                    'category': category,
                    'description': voice.get('description', '')
                })

        return voices

    def get_native_sample_rate(self) -> int:
        """Get PersonaPlex native sample rate."""
        return 32000

    async def close(self) -> None:
        """Close all sessions and clean up."""
        async with self._lock:
            session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            await self.close_session(session_id)

        self.initialized = False
        self.logger.info("PersonaPlex proxy service closed")

    async def verify_connection(self) -> bool:
        """Verify connection to PersonaPlex server."""
        if not self.initialized:
            return False

        try:
            # Try to create and immediately close a test session
            session_id = await self.create_session()
            await self.close_session(session_id)
            return True
        except Exception as e:
            self.logger.error(f"Connection verification failed: {e}")
            return False
