"""
Speech-to-Speech service interface and base implementations.

This module defines the common interface for full-duplex speech-to-speech services
like PersonaPlex, which handle conversation dynamics (listening + speaking)
simultaneously rather than using a cascade of STT -> LLM -> TTS.
"""

from abc import abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List
import logging

from ..base import ProviderAIService, ServiceType


class SpeechToSpeechService(ProviderAIService):
    """
    Base class for full-duplex speech-to-speech services.

    Unlike AudioService (which provides separate STT and TTS), speech-to-speech
    services handle the entire conversation loop internally:
    - Accept continuous audio input
    - Generate continuous audio output
    - Handle turn-taking, interruptions, and backchannels
    - Maintain conversation state and persona

    Key Differences from Cascade (STT -> LLM -> TTS):
    - Model listens and speaks simultaneously (full-duplex)
    - Natural conversation dynamics (backchannels like "mm-hmm", "oh!")
    - Built-in interruption handling
    - Unified latency (no separate STT/TTS delays)

    Implementations:
    - PersonaPlex: NVIDIA's full-duplex conversational model
    """

    service_type = ServiceType.SPEECH_TO_SPEECH

    def __init__(self, config: Dict[str, Any], provider_name: str, **kwargs):
        """
        Initialize the speech-to-speech service.

        Args:
            config: Configuration dictionary
            provider_name: Provider name (e.g., 'personaplex')
            **kwargs: Additional arguments (ignored, for compatibility with adapter loader)
        """
        # Speech-to-speech services don't use domain_adapter or datasource,
        # but the adapter loader may pass them. We accept and ignore them.
        super().__init__(config, ServiceType.SPEECH_TO_SPEECH, provider_name)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def create_session(
        self,
        voice_prompt: Optional[str] = None,
        text_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Create a new conversation session with persona configuration.

        Args:
            voice_prompt: Voice embedding file or path (e.g., "NATF2.pt")
                         Controls the voice timbre, style, and prosody
            text_prompt: Role/system prompt for the conversation
                        Controls the persona's behavior and knowledge
            **kwargs: Additional provider-specific parameters

        Returns:
            Session ID for subsequent calls

        Example:
            >>> service = PersonaPlexService(config)
            >>> await service.initialize()
            >>> session_id = await service.create_session(
            ...     voice_prompt="NATF2.pt",
            ...     text_prompt="You are a helpful customer service agent."
            ... )
        """
        pass

    @abstractmethod
    async def process_audio_frame(
        self,
        session_id: str,
        audio_frame: bytes,
        sample_rate: int = 32000
    ) -> AsyncIterator[bytes]:
        """
        Process an audio frame and yield response audio frames.

        This is the core full-duplex method. The model processes incoming
        audio while potentially generating output audio simultaneously.

        Args:
            session_id: Session ID from create_session()
            audio_frame: Input audio frame (PCM or Opus encoded)
            sample_rate: Sample rate of input audio (default: 32000 Hz)

        Yields:
            Output audio frames as bytes (same encoding as input)

        Note:
            - This method may yield multiple frames per input frame
            - Yields may occur even when user is speaking (backchannels)
            - Empty yields indicate the model is listening silently

        Example:
            >>> async for output_frame in service.process_audio_frame(
            ...     session_id, input_audio
            ... ):
            ...     play_audio(output_frame)
        """
        pass

    @abstractmethod
    async def get_text_tokens(
        self,
        session_id: str
    ) -> AsyncIterator[str]:
        """
        Yield text tokens as the model generates them.

        Useful for logging, analytics, or displaying transcripts.

        Args:
            session_id: Session ID from create_session()

        Yields:
            Text tokens (words or subwords) as strings
        """
        pass

    @abstractmethod
    async def close_session(self, session_id: str) -> None:
        """
        Close a session and release associated resources.

        Args:
            session_id: Session ID to close

        Note:
            - Releases GPU memory for embedded mode
            - Closes WebSocket for proxy mode
            - Session cannot be used after closing
        """
        pass

    @abstractmethod
    async def interrupt(self, session_id: str) -> None:
        """
        Signal an interruption to the model.

        Tells the model to stop speaking and listen. Useful when the
        user starts speaking while the model is still responding.

        Args:
            session_id: Session ID to interrupt

        Note:
            Many full-duplex models handle interruptions automatically
            by detecting user speech. This method provides explicit control.
        """
        pass

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """
        Get list of available voice prompts/embeddings.

        Returns:
            List of voice info dicts with 'id', 'name', 'category' keys

        Default implementation returns empty list; override in subclasses.
        """
        return []

    def get_supported_sample_rates(self) -> List[int]:
        """
        Get list of supported audio sample rates.

        Returns:
            List of sample rates in Hz (e.g., [16000, 24000, 32000])

        Default implementation returns common rates; override in subclasses.
        """
        return [16000, 24000, 32000]

    def get_native_sample_rate(self) -> int:
        """
        Get the native sample rate for this service.

        Returns:
            Sample rate in Hz that the model processes internally

        Default implementation returns 32000; override in subclasses.
        """
        return 32000


class SpeechToSpeechResult:
    """
    Structured result for speech-to-speech operations.

    Provides a standardized way to return results with metadata.
    """

    def __init__(
        self,
        session_id: str,
        audio: Optional[bytes] = None,
        text: Optional[str] = None,
        is_final: bool = False,
        interrupted: bool = False,
        provider: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize speech-to-speech result.

        Args:
            session_id: Session ID this result belongs to
            audio: Generated audio data (if any)
            text: Generated text tokens (if any)
            is_final: Whether this is the final result for this turn
            interrupted: Whether the turn was interrupted
            provider: Provider name
            metadata: Optional additional metadata
        """
        self.session_id = session_id
        self.audio = audio
        self.text = text
        self.is_final = is_final
        self.interrupted = interrupted
        self.provider = provider
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'session_id': self.session_id,
            'is_final': self.is_final,
            'interrupted': self.interrupted,
            'provider': self.provider,
            'metadata': self.metadata
        }
        if self.audio is not None:
            result['audio_size'] = len(self.audio)
        if self.text is not None:
            result['text'] = self.text
        return result


def create_speech_to_speech_service(
    provider: str,
    config: Dict[str, Any]
) -> SpeechToSpeechService:
    """
    Factory function to create a speech-to-speech service.

    Args:
        provider: Provider name (e.g., 'personaplex')
        config: Configuration dictionary

    Returns:
        Speech-to-speech service instance

    Example:
        >>> service = create_speech_to_speech_service('personaplex', config)
        >>> await service.initialize()
    """
    from ..factory import AIServiceFactory

    return AIServiceFactory.create_service(
        ServiceType.SPEECH_TO_SPEECH,
        provider,
        config
    )
