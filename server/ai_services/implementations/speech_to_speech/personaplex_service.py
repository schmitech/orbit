"""
PersonaPlex Service

Main entry point for PersonaPlex speech-to-speech service.
Automatically selects between embedded (local GPU) and proxy (remote server)
modes based on configuration.

Configuration (from config/personaplex.yaml):
    personaplex:
      enabled: true
      mode: "embedded"  # or "proxy"

Usage:
    service = PersonaPlexService(config)
    await service.initialize()
    session_id = await service.create_session(
        voice_prompt="NATF2.pt",
        text_prompt="You are a helpful assistant."
    )
    async for audio in service.process_audio_frame(session_id, input_audio):
        play_audio(audio)
"""

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from ...services.speech_to_speech_service import SpeechToSpeechService

logger = logging.getLogger(__name__)


class PersonaPlexService(SpeechToSpeechService):
    """
    PersonaPlex speech-to-speech service.

    This is the main entry point for PersonaPlex integration. It automatically
    delegates to either PersonaPlexEmbeddedService or PersonaPlexProxyService
    based on the configuration.

    Modes:
    - embedded: Loads model into local GPU memory (lowest latency)
    - proxy: Connects to remote PersonaPlex server (GPU sharing)

    The mode is determined by the 'personaplex.mode' config value.
    """

    def __init__(self, config: Dict[str, Any], **kwargs):
        """
        Initialize the PersonaPlex service.

        Args:
            config: Configuration dictionary
            **kwargs: Additional arguments (passed to parent, ignored)
        """
        super().__init__(config, "personaplex", **kwargs)

        # Get PersonaPlex configuration
        pp_config = config.get('personaplex', {})

        if not pp_config.get('enabled', False):
            self.logger.warning("PersonaPlex is disabled in configuration")

        # Determine mode
        self.mode = pp_config.get('mode', 'proxy')
        self.logger.info(f"PersonaPlex mode: {self.mode}")

        # Create delegate service based on mode
        self._delegate: Optional[SpeechToSpeechService] = None

    async def initialize(self) -> bool:
        """
        Initialize the PersonaPlex service.

        Creates and initializes the appropriate delegate service based on mode.

        Returns:
            True if initialization successful
        """
        pp_config = self.config.get('personaplex', {})

        if not pp_config.get('enabled', False):
            self.logger.error("PersonaPlex is disabled in configuration")
            return False

        try:
            if self.mode == "embedded":
                self.logger.info("Initializing PersonaPlex in embedded mode...")
                from .personaplex_embedded import PersonaPlexEmbeddedService
                self._delegate = PersonaPlexEmbeddedService(self.config)
            else:  # proxy mode
                self.logger.info("Initializing PersonaPlex in proxy mode...")
                from .personaplex_proxy import PersonaPlexProxyService
                self._delegate = PersonaPlexProxyService(self.config)

            success = await self._delegate.initialize()

            if success:
                self.initialized = True
                self.logger.info(f"PersonaPlex service initialized ({self.mode} mode)")
            else:
                self.logger.error("PersonaPlex delegate initialization failed")

            return success

        except ImportError as e:
            self.logger.error(f"Failed to import PersonaPlex {self.mode} service: {e}")
            return False
        except Exception as e:
            self.logger.error(f"PersonaPlex initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def create_session(
        self,
        voice_prompt: Optional[str] = None,
        text_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Create a new conversation session.

        Args:
            voice_prompt: Voice embedding file (e.g., "NATF2.pt")
            text_prompt: Role/system prompt
            **kwargs: Additional parameters

        Returns:
            Session ID
        """
        if not self._delegate:
            raise RuntimeError("Service not initialized")

        return await self._delegate.create_session(
            voice_prompt=voice_prompt,
            text_prompt=text_prompt,
            **kwargs
        )

    async def process_audio_frame(
        self,
        session_id: str,
        audio_frame: bytes,
        sample_rate: int = 32000
    ) -> AsyncIterator[bytes]:
        """
        Process an audio frame and yield response audio frames.

        Args:
            session_id: Session ID
            audio_frame: Input audio frame
            sample_rate: Sample rate

        Yields:
            Output audio frames
        """
        if not self._delegate:
            self.logger.error("Service not initialized")
            return

        async for frame in self._delegate.process_audio_frame(
            session_id, audio_frame, sample_rate
        ):
            yield frame

    async def get_text_tokens(self, session_id: str) -> AsyncIterator[str]:
        """
        Yield text tokens as the model generates them.

        Args:
            session_id: Session ID

        Yields:
            Text tokens
        """
        if not self._delegate:
            return

        async for token in self._delegate.get_text_tokens(session_id):
            yield token

    async def close_session(self, session_id: str) -> None:
        """
        Close a session.

        Args:
            session_id: Session ID to close
        """
        if self._delegate:
            await self._delegate.close_session(session_id)

    async def interrupt(self, session_id: str) -> None:
        """
        Signal an interruption.

        Args:
            session_id: Session ID to interrupt
        """
        if self._delegate:
            await self._delegate.interrupt(session_id)

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voice prompts."""
        if self._delegate:
            return await self._delegate.get_available_voices()
        return []

    def get_supported_sample_rates(self) -> List[int]:
        """Get supported sample rates."""
        if self._delegate:
            return self._delegate.get_supported_sample_rates()
        return [32000]

    def get_native_sample_rate(self) -> int:
        """Get native sample rate."""
        if self._delegate:
            return self._delegate.get_native_sample_rate()
        return 32000

    async def close(self) -> None:
        """Close the service and release resources."""
        if self._delegate:
            await self._delegate.close()
            self._delegate = None

        self.initialized = False
        self.logger.info("PersonaPlex service closed")

    async def verify_connection(self) -> bool:
        """Verify the service is operational."""
        if self._delegate:
            return await self._delegate.verify_connection()
        return False

    def get_mode(self) -> str:
        """Get the current operation mode."""
        return self.mode

    def is_embedded(self) -> bool:
        """Check if running in embedded mode."""
        return self.mode == "embedded"

    def is_proxy(self) -> bool:
        """Check if running in proxy mode."""
        return self.mode == "proxy"
