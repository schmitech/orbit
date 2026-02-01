"""
PersonaPlex Embedded Service

Runs PersonaPlex locally in the same process as ORBIT, loading the model
directly into GPU memory. This mode is suitable for:
- Single-server deployments with dedicated GPU
- Lowest latency requirements
- Complete control over model configuration

Requirements:
- NVIDIA GPU with sufficient VRAM (16GB+ recommended)
- CUDA toolkit installed
- HuggingFace token for model download
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid

from ...services.speech_to_speech_service import SpeechToSpeechService

logger = logging.getLogger(__name__)

# Try to import torch and model dependencies
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("torch not available, PersonaPlex embedded mode disabled")


class PersonaPlexEmbeddedSession:
    """
    Manages a single PersonaPlex embedded session.

    Holds the LMGen instance and streaming state for one conversation.
    """

    def __init__(
        self,
        session_id: str,
        lm_gen: Any,
        mimi: Any,
        other_mimi: Any,
        sample_rate: int,
        frame_size: int
    ):
        self.session_id = session_id
        self.lm_gen = lm_gen
        self.mimi = mimi
        self.other_mimi = other_mimi
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.is_active = True
        self._text_buffer: List[str] = []
        self._initialized = False

    async def initialize(self):
        """Initialize streaming state."""
        if self._initialized:
            return

        # Run initialization in thread to avoid blocking event loop
        await asyncio.to_thread(self._init_streaming)
        self._initialized = True

    def _init_streaming(self):
        """Initialize LMGen streaming state (runs in thread)."""
        self.lm_gen.streaming_forever(1)  # 1 stream
        self.lm_gen.reset_streaming()

    async def process_frame(self, audio_frame: bytes) -> AsyncIterator[bytes]:
        """
        Process an audio frame through PersonaPlex.

        Args:
            audio_frame: Input audio frame

        Yields:
            Output audio frames
        """
        if not self.is_active:
            return

        # Process in thread to avoid blocking
        results = await asyncio.to_thread(
            self._process_frame_sync,
            audio_frame
        )

        for audio, text in results:
            if text:
                self._text_buffer.append(text)
            if audio:
                yield audio

    def _process_frame_sync(self, audio_frame: bytes) -> List[tuple]:
        """
        Synchronous frame processing (runs in thread).

        Returns:
            List of (audio_bytes, text_token) tuples
        """
        import numpy as np

        results = []

        try:
            # Convert bytes to tensor
            pcm_array = np.frombuffer(audio_frame, dtype=np.float32)
            pcm_tensor = torch.from_numpy(pcm_array).unsqueeze(0).unsqueeze(0)

            if torch.cuda.is_available():
                pcm_tensor = pcm_tensor.cuda()

            # Encode with Mimi
            with torch.no_grad():
                codes = self.mimi.encode(pcm_tensor)

                # Process through LMGen
                output_codes = self.lm_gen.step(codes)

                # Extract text tokens (channel 0)
                text_token = None
                if output_codes is not None and output_codes.shape[-1] > 0:
                    text_idx = output_codes[0, 0, 0].item()
                    if hasattr(self, 'text_tokenizer') and self.text_tokenizer:
                        text_token = self.text_tokenizer.id_to_piece(text_idx)

                # Decode audio (channels 1-8)
                if output_codes is not None:
                    audio_codes = output_codes[:, 1:, :]
                    decoded = self.other_mimi.decode(audio_codes)
                    audio_bytes = decoded.cpu().numpy().tobytes()
                    results.append((audio_bytes, text_token))

        except Exception as e:
            logger.error(f"Error processing frame: {e}")

        return results

    def close(self):
        """Close the session and release resources."""
        self.is_active = False
        # LMGen cleanup happens at service level


class PersonaPlexEmbeddedService(SpeechToSpeechService):
    """
    PersonaPlex service running in the same process as ORBIT.

    Loads the PersonaPlex model directly into GPU memory for lowest latency.

    Configuration (from config/personaplex.yaml):
        personaplex:
          mode: "embedded"
          embedded:
            hf_repo: "nvidia/personaplex-7b-v1"
            device: "cuda"
            cpu_offload: false
            warmup_on_start: true
    """

    def __init__(self, config: Dict[str, Any], **kwargs):
        """
        Initialize the embedded service.

        Args:
            config: Configuration dictionary
            **kwargs: Additional arguments (passed to parent, ignored)
        """
        super().__init__(config, "personaplex_embedded", **kwargs)

        # Extract PersonaPlex config
        pp_config = config.get('personaplex', {})
        embedded_config = pp_config.get('embedded', {})

        self.hf_repo = embedded_config.get('hf_repo', 'nvidia/personaplex-7b-v1')
        self.device = embedded_config.get('device', 'cuda')
        self.cpu_offload = embedded_config.get('cpu_offload', False)
        self.voice_prompt_dir = embedded_config.get('voice_prompt_dir')
        self.warmup_on_start = embedded_config.get('warmup_on_start', True)
        self.warmup_iterations = embedded_config.get('warmup_iterations', 4)

        # Default persona settings
        defaults = pp_config.get('defaults', {})
        self.default_voice = defaults.get('voice_prompt', 'NATF2.pt')
        self.default_text_prompt = defaults.get('text_prompt', '')
        self.temperature = defaults.get('temperature', 0.8)
        self.temperature_text = defaults.get('temperature_text', 0.7)
        self.top_k = defaults.get('top_k', 250)
        self.top_k_text = defaults.get('top_k_text', 25)

        # Model components (loaded on initialize)
        self.mimi = None
        self.other_mimi = None
        self.lm = None
        self.text_tokenizer = None
        self.sample_rate = 32000
        self.frame_rate = 12.5
        self.frame_size = int(self.sample_rate / self.frame_rate)

        # Session management
        self._sessions: Dict[str, PersonaPlexEmbeddedSession] = {}
        self._lock = asyncio.Lock()
        self._max_concurrent = pp_config.get('session', {}).get('max_concurrent_sessions', 4)

    async def initialize(self) -> bool:
        """
        Initialize the embedded service and load models.

        This loads the PersonaPlex models into GPU memory.

        Returns:
            True if initialization successful
        """
        if not HAS_TORCH:
            self.logger.error("torch not installed, cannot use embedded mode")
            return False

        try:
            self.logger.info("Loading PersonaPlex models...")

            # Run model loading in thread to avoid blocking
            await asyncio.to_thread(self._load_models)

            if self.warmup_on_start:
                self.logger.info("Warming up PersonaPlex...")
                await asyncio.to_thread(self._warmup)

            self.initialized = True
            self.logger.info("PersonaPlex embedded service initialized")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize PersonaPlex: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_models(self):
        """Load PersonaPlex models (runs in thread)."""
        try:
            # Import PersonaPlex modules
            from moshi.models import loaders

            # Check HuggingFace token
            hf_token = os.environ.get('HF_TOKEN')
            if not hf_token:
                self.logger.warning("HF_TOKEN not set, model download may fail")

            # Download and load Mimi (audio codec)
            from huggingface_hub import hf_hub_download

            self.logger.info("Loading Mimi codec...")
            mimi_weight = hf_hub_download(self.hf_repo, loaders.MIMI_NAME)
            self.mimi = loaders.get_mimi(mimi_weight, self.device)
            self.other_mimi = loaders.get_mimi(mimi_weight, self.device)

            # Update sample rate and frame size from Mimi
            self.sample_rate = self.mimi.sample_rate
            self.frame_rate = self.mimi.frame_rate
            self.frame_size = int(self.sample_rate / self.frame_rate)

            # Load text tokenizer
            self.logger.info("Loading text tokenizer...")
            import sentencepiece
            tokenizer_path = hf_hub_download(self.hf_repo, loaders.TEXT_TOKENIZER_NAME)
            self.text_tokenizer = sentencepiece.SentencePieceProcessor(tokenizer_path)

            # Load LM
            self.logger.info("Loading PersonaPlex LM...")
            moshi_weight = hf_hub_download(self.hf_repo, loaders.MOSHI_NAME)
            self.lm = loaders.get_moshi_lm(
                moshi_weight,
                device=self.device,
                cpu_offload=self.cpu_offload
            )
            self.lm.eval()

            # Download voice prompts if needed
            if self.voice_prompt_dir is None:
                self.logger.info("Downloading voice prompts...")
                voices_tgz = hf_hub_download(self.hf_repo, "voices.tgz")
                voices_dir = Path(voices_tgz).parent / "voices"
                if not voices_dir.exists():
                    import tarfile
                    with tarfile.open(voices_tgz, 'r:gz') as tar:
                        tar.extractall(voices_dir.parent)
                self.voice_prompt_dir = str(voices_dir)

            self.logger.info("PersonaPlex models loaded successfully")

        except ImportError as e:
            raise ImportError(
                f"PersonaPlex dependencies not installed: {e}. "
                f"Install with: pip install moshi huggingface_hub sentencepiece"
            )

    def _warmup(self):
        """Warm up the model with dummy inference (runs in thread)."""
        import numpy as np

        try:
            from moshi.models import LMGen

            # Create temporary LMGen for warmup
            lm_gen = LMGen(
                self.lm,
                audio_silence_frame_cnt=int(0.5 * self.frame_rate),
                sample_rate=self.sample_rate,
                device=self.device,
                frame_rate=self.frame_rate,
            )

            lm_gen.streaming_forever(1)

            # Run warmup iterations
            dummy_audio = np.zeros(self.frame_size, dtype=np.float32)
            dummy_tensor = torch.from_numpy(dummy_audio).unsqueeze(0).unsqueeze(0)

            if torch.cuda.is_available():
                dummy_tensor = dummy_tensor.cuda()

            with torch.no_grad():
                for i in range(self.warmup_iterations):
                    codes = self.mimi.encode(dummy_tensor)
                    _ = lm_gen.step(codes)

            self.logger.info(f"Warmup completed ({self.warmup_iterations} iterations)")

        except Exception as e:
            self.logger.warning(f"Warmup failed: {e}")

    async def create_session(
        self,
        voice_prompt: Optional[str] = None,
        text_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Create a new PersonaPlex session with persona configuration.

        Args:
            voice_prompt: Voice embedding file (e.g., "NATF2.pt")
            text_prompt: Role/system prompt
            **kwargs: Additional parameters

        Returns:
            Session ID
        """
        if not self.initialized:
            raise RuntimeError("Service not initialized")

        async with self._lock:
            if len(self._sessions) >= self._max_concurrent:
                raise RuntimeError(
                    f"Maximum concurrent sessions ({self._max_concurrent}) reached"
                )

        session_id = str(uuid.uuid4())
        voice = voice_prompt or self.default_voice
        text = text_prompt or self.default_text_prompt

        self.logger.info(f"Creating PersonaPlex session: {session_id}")
        self.logger.debug(f"Voice: {voice}, Text prompt length: {len(text)}")

        # Create session in thread
        session = await asyncio.to_thread(
            self._create_session_sync,
            session_id,
            voice,
            text,
            kwargs.get('seed')
        )

        async with self._lock:
            self._sessions[session_id] = session

        # Initialize streaming state
        await session.initialize()

        return session_id

    def _create_session_sync(
        self,
        session_id: str,
        voice_prompt: str,
        text_prompt: str,
        seed: Optional[int]
    ) -> PersonaPlexEmbeddedSession:
        """Create session synchronously (runs in thread)."""
        from moshi.models import LMGen

        # Create LMGen instance for this session
        lm_gen = LMGen(
            self.lm,
            audio_silence_frame_cnt=int(0.5 * self.frame_rate),
            sample_rate=self.sample_rate,
            device=self.device,
            frame_rate=self.frame_rate,
            temp=self.temperature,
            temp_text=self.temperature_text,
            top_k=self.top_k,
            top_k_text=self.top_k_text,
        )

        # Load voice prompt
        voice_path = os.path.join(self.voice_prompt_dir, voice_prompt)
        if voice_path.endswith('.pt'):
            lm_gen.load_voice_prompt_embeddings(voice_path)
        else:
            lm_gen.load_voice_prompt(voice_path)

        # Set text prompt
        if text_prompt:
            wrapped_prompt = f"<system> {text_prompt.strip()} <system>"
            lm_gen.text_prompt_tokens = self.text_tokenizer.encode(wrapped_prompt)

        # Set seed if provided
        if seed is not None:
            torch.manual_seed(seed)

        # Create session object
        session = PersonaPlexEmbeddedSession(
            session_id=session_id,
            lm_gen=lm_gen,
            mimi=self.mimi,
            other_mimi=self.other_mimi,
            sample_rate=self.sample_rate,
            frame_size=self.frame_size
        )
        session.text_tokenizer = self.text_tokenizer

        return session

    async def process_audio_frame(
        self,
        session_id: str,
        audio_frame: bytes,
        sample_rate: int = 32000
    ) -> AsyncIterator[bytes]:
        """
        Process an audio frame through PersonaPlex.

        Args:
            session_id: Session ID
            audio_frame: Input audio frame (PCM float32)
            sample_rate: Sample rate (should be 32000)

        Yields:
            Output audio frames
        """
        session = self._sessions.get(session_id)
        if not session or not session.is_active:
            self.logger.error(f"Session not found or inactive: {session_id}")
            return

        async for output_frame in session.process_frame(audio_frame):
            yield output_frame

    async def get_text_tokens(self, session_id: str) -> AsyncIterator[str]:
        """
        Yield accumulated text tokens for a session.

        Args:
            session_id: Session ID

        Yields:
            Text tokens
        """
        session = self._sessions.get(session_id)
        if not session:
            return

        while session._text_buffer:
            yield session._text_buffer.pop(0)

    async def close_session(self, session_id: str) -> None:
        """
        Close a session and release resources.

        Args:
            session_id: Session ID to close
        """
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if session:
            self.logger.info(f"Closing PersonaPlex session: {session_id}")
            session.close()

    async def interrupt(self, session_id: str) -> None:
        """
        Interrupt the current generation.

        For embedded mode, this resets the streaming state.

        Args:
            session_id: Session ID to interrupt
        """
        session = self._sessions.get(session_id)
        if session and session.is_active:
            try:
                await asyncio.to_thread(session.lm_gen.reset_streaming)
                self.logger.debug(f"Session {session_id} interrupted")
            except Exception as e:
                self.logger.error(f"Error interrupting session: {e}")

    async def get_available_voices(self) -> List[Dict[str, Any]]:
        """Get list of available voice prompts."""
        pp_config = self.config.get('personaplex', {})
        voices_config = pp_config.get('voices', {})

        voices = []
        for category, voice_list in voices_config.items():
            for voice in voice_list:
                voice_path = os.path.join(self.voice_prompt_dir or '', voice.get('id', ''))
                exists = os.path.exists(voice_path) if self.voice_prompt_dir else False
                voices.append({
                    'id': voice.get('id'),
                    'name': voice.get('name'),
                    'category': category,
                    'description': voice.get('description', ''),
                    'available': exists
                })

        return voices

    def get_native_sample_rate(self) -> int:
        """Get PersonaPlex native sample rate."""
        return self.sample_rate

    async def close(self) -> None:
        """Close all sessions and unload models."""
        # Close all sessions
        async with self._lock:
            session_ids = list(self._sessions.keys())

        for session_id in session_ids:
            await self.close_session(session_id)

        # Unload models
        self.mimi = None
        self.other_mimi = None
        self.lm = None
        self.text_tokenizer = None

        # Clear CUDA cache
        if HAS_TORCH and torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.initialized = False
        self.logger.info("PersonaPlex embedded service closed")

    async def verify_connection(self) -> bool:
        """Verify the service is operational."""
        return self.initialized and self.lm is not None
