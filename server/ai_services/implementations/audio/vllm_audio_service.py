"""
vLLM audio service implementation using unified architecture.

vLLM provides an OpenAI-compatible API for serving audio models like Orpheus.
This service supports text-to-speech through vLLM-served audio models.

Compare with: server/ai_services/implementations/vllm_inference_service.py
"""

import logging
from typing import Dict, Any, Optional, Union, List
from io import BytesIO
import base64
import asyncio
import re
import wave

from openai import AsyncOpenAI
import httpx

from ...services import AudioService
from ...connection import ConnectionManager, RetryHandler

logger = logging.getLogger(__name__)

# Optional SNAC import for audio token decoding
try:
    import torch
    import numpy as np
    from snac import SNAC
    SNAC_AVAILABLE = True
except ImportError:
    SNAC_AVAILABLE = False
    torch = None
    np = None
    SNAC = None

# Global SNAC model cache (singleton pattern for efficiency)
_global_snac_model = None
_global_snac_device = None


class VLLMAudioService(AudioService):
    """
    vLLM audio service using unified architecture.

    Supports:
    - Text-to-speech using vLLM-served TTS models (e.g., Orpheus)
    - Speech-to-text (if STT model is served)
    - Audio transcription
    - Audio translation

    Uses vLLM's OpenAI-compatible API for audio model inference.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize the vLLM audio service."""
        # Initialize via AudioService base class
        AudioService.__init__(self, config, "vllm")

        # Get audio-specific configuration
        provider_config = self._extract_provider_config()

        # vLLM connection settings
        self.host = provider_config.get('host', 'localhost')
        self.port = provider_config.get('port', 8000)
        self.base_url = provider_config.get('base_url', f"http://{self.host}:{self.port}/v1")

        # Model configuration
        self.tts_model = provider_config.get('tts_model', 'canopylabs/orpheus-3b-0.1-ft')
        self.stt_model = provider_config.get('stt_model', None)  # STT may not be supported
        self.tts_voice = provider_config.get('tts_voice', 'tara')
        self.tts_format = provider_config.get('tts_format', 'wav')

        # Generation parameters
        self.temperature = provider_config.get('temperature', 0.6)
        self.top_p = provider_config.get('top_p', 0.95)
        self.max_tokens = provider_config.get('max_tokens', 1200)  # Conservative default for 4096 context
        self.repetition_penalty = provider_config.get('repetition_penalty', 1.1)

        # Streaming configuration
        self.stream = provider_config.get('stream', False)
        
        # vLLM-specific optimizations
        self.max_concurrent_requests = provider_config.get('max_concurrent_requests', 4)  # Parallel requests to vLLM
        self.request_queue_size = provider_config.get('request_queue_size', 10)  # Queue size for pending requests

        # Initialize AsyncOpenAI client pointing to local vLLM server
        # vLLM local deployment doesn't require API key
        # Optimized for high concurrency and low latency
        http_client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(
                max_keepalive_connections=50,  # Increased for better connection reuse
                max_connections=200,  # Higher limit for parallel requests
                keepalive_expiry=600.0  # Longer keepalive for connection reuse
            ),
            timeout=httpx.Timeout(120.0, connect=15.0),  # Longer timeout for audio generation
            follow_redirects=True
        )
        
        # Semaphore to limit concurrent requests to vLLM (prevents overwhelming server)
        self._request_semaphore = asyncio.Semaphore(self.max_concurrent_requests)

        # Use dummy API key for local vLLM (OpenAI client requires one)
        self.api_key = provider_config.get('api_key', 'EMPTY')

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=http_client
        )

        # Setup connection manager
        timeout_config = self._get_timeout_config()
        self.connection_manager = ConnectionManager(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=timeout_config['total']
        )

        self.connection_verified = False
        self._verification_attempted = False
        self._verification_inflight = False

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(
            max_retries=retry_config['max_retries'],
            initial_wait_ms=retry_config['initial_wait_ms'],
            max_wait_ms=retry_config['max_wait_ms'],
            exponential_base=retry_config['exponential_base'],
            enabled=retry_config['enabled']
        )

        # SNAC decoder for Orpheus-style models
        self.snac_model = None
        # Auto-detect CUDA if available, otherwise use CPU
        if SNAC_AVAILABLE and torch is not None and torch.cuda.is_available():
            default_device = 'cuda'
            logger.debug(f"CUDA available: {torch.cuda.get_device_name(0)}")
        else:
            default_device = 'cpu'
        self.snac_device = provider_config.get('snac_device', default_device)
        self._snac_initialized = False

        logger.info(
            f"Configured vLLM audio service with TTS model: {self.tts_model} "
            f"at {self.base_url} (max_concurrent_requests: {self.max_concurrent_requests})"
        )
        
        # vLLM Server-side optimization recommendations:
        # For better performance with FP8 quantization and chunked prefill, use:
        # vllm serve canopylabs/orpheus-3b-0.1-ft \
        #   --dtype auto \
        #   --quantization fp8 \
        #   --enable-chunked-prefill \
        #   --max_model_len 4096 \
        #   --gpu-memory-utilization 0.85 \
        #   --max-num-seqs 8
        # 
        # Key parameters:
        # - --max-num-seqs: CRITICAL for parallel processing (default is 1, causing sequential delays)
        #   With FP8 quantization, you can typically run 8-12 concurrent sequences
        # - --gpu-memory-utilization: Increase from 0.7 to 0.85-0.9 for better throughput
        # - FP8 quantization reduces memory by ~50%, allowing more concurrent requests
        logger.debug(
                f"vLLM optimization: Add --max-num-seqs {self.max_concurrent_requests}+ to your vLLM server command "
                f"to enable parallel audio generation (currently missing, causing sequential processing)"
            )

    def _extract_provider_config(self) -> Dict[str, Any]:
        """
        Extract provider-specific configuration from the config dictionary.

        Override base method to look for 'sounds' (the actual key in sound.yaml)
        instead of 'audios' (the default plural form).
        """
        # Try 'sounds' first (as used in config/sound.yaml)
        sounds_config = self.config.get('sounds', {})
        provider_config = sounds_config.get(self.provider_name, {})

        if provider_config:
            return provider_config

        # Fallback to base class logic
        return super()._extract_provider_config()

    def _initialize_snac(self) -> bool:
        """Initialize SNAC decoder for audio token decoding."""
        global _global_snac_model, _global_snac_device

        if not SNAC_AVAILABLE:
            logger.warning(
                "SNAC library not available. Install with: pip install snac torch numpy"
            )
            return False

        if self._snac_initialized:
            return True

        # Use global cached model if available and on same device
        if _global_snac_model is not None and _global_snac_device == self.snac_device:
            self.snac_model = _global_snac_model
            self._snac_initialized = True
            logger.debug(f"Using cached SNAC model on device: {self.snac_device}")
            return True

        try:
            logger.debug(f"Loading SNAC model on device: {self.snac_device}")
            if self.snac_device.startswith('cuda') and torch.cuda.is_available():
                logger.debug(f"GPU: {torch.cuda.get_device_name(0)}, "
                                   f"Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
            
            self.snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
            self.snac_model = self.snac_model.to(self.snac_device)
            
            # Set model to inference mode for better GPU performance
            self.snac_model.eval()
            
            # Warm up GPU with a dummy inference if on CUDA (reduces first inference latency)
            if self.snac_device.startswith('cuda') and torch.cuda.is_available():
                with torch.inference_mode():
                    dummy_codes = [
                        torch.zeros((1, 1), device=self.snac_device, dtype=torch.int32),
                        torch.zeros((1, 2), device=self.snac_device, dtype=torch.int32),
                        torch.zeros((1, 4), device=self.snac_device, dtype=torch.int32)
                    ]
                    _ = self.snac_model.decode(dummy_codes)
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                logger.debug("GPU warm-up completed")
            
            self._snac_initialized = True

            # Cache globally for reuse
            _global_snac_model = self.snac_model
            _global_snac_device = self.snac_device

            logger.debug("SNAC model loaded and cached successfully")
            if self.snac_device.startswith('cuda'):
                allocated = torch.cuda.memory_allocated(0) / 1024**2
                reserved = torch.cuda.memory_reserved(0) / 1024**2
                logger.debug(f"GPU memory - Allocated: {allocated:.2f} MB, Reserved: {reserved:.2f} MB")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SNAC model: {str(e)}")
            return False

    def _turn_token_into_id(self, token_string: str, index: int) -> int:
        """
        Convert Orpheus token string to SNAC token ID.

        Args:
            token_string: Token string like "<custom_token_XXXXX>"
            index: Token index (0-6 within each frame)

        Returns:
            SNAC token ID
        """
        token_string = token_string.strip()

        # Find the last token in the string
        last_token_start = token_string.rfind("<custom_token_")

        if last_token_start == -1:
            raise ValueError(f"No custom token found in string: '{token_string}'")

        # Extract the last token
        last_token = token_string[last_token_start:]

        if last_token.startswith("<custom_token_") and last_token.endswith(">"):
            number_str = last_token[14:-1]
            token_id = int(number_str) - 10 - ((index % 7) * 4096)
            return token_id
        else:
            raise ValueError(f"Token not in expected format: '{last_token}'")

    def _extract_audio_tokens(self, response_text: str) -> List[str]:
        """
        Extract audio tokens from model response.

        Args:
            response_text: Generated text from model

        Returns:
            List of token strings
        """
        # Find all custom tokens in the response
        pattern = r'<custom_token_\d+>'
        tokens = re.findall(pattern, response_text)
        return tokens

    def _convert_tokens_to_audio(self, tokens: List[str]) -> bytes:
        """
        Convert audio tokens to audio bytes using SNAC decoder.

        Args:
            tokens: List of token strings from model

        Returns:
            Audio data as bytes (16-bit PCM, 24kHz)
        """
        if not self._snac_initialized:
            if not self._initialize_snac():
                raise RuntimeError("SNAC decoder not available")

        if len(tokens) < 7:
            raise ValueError(f"Not enough tokens to decode audio: {len(tokens)} < 7")

        # Convert token strings to IDs
        token_ids = []
        for i, token_str in enumerate(tokens):
            try:
                token_id = self._turn_token_into_id(token_str, i)
                if 0 <= token_id <= 4096:
                    token_ids.append(token_id)
            except Exception as e:
                logger.warning(f"Failed to parse token {i}: {str(e)}")
                continue

        if len(token_ids) < 7:
            raise ValueError(f"Not enough valid token IDs: {len(token_ids)} < 7")

        # Process frames (7 tokens per frame)
        num_frames = len(token_ids) // 7
        frame = token_ids[:num_frames * 7]

        # Pre-allocate tensors for better GPU performance (vectorized operations)
        # Code 0: 1 token per frame (indices: 0, 7, 14, ...)
        # Code 1: 2 tokens per frame (indices: 1,4, 8,11, 15,18, ...)
        # Code 2: 4 tokens per frame (indices: 2,3,5,6, 9,10,12,13, ...)
        
        # Pre-allocate lists for efficient collection
        codes_0_list = []
        codes_1_list = []
        codes_2_list = []
        
        for j in range(num_frames):
            i = 7 * j
            codes_0_list.append(frame[i])
            codes_1_list.extend([frame[i+1], frame[i+4]])
            codes_2_list.extend([frame[i+2], frame[i+3], frame[i+5], frame[i+6]])
        
        # Create tensors in one operation (much faster on GPU)
        codes_0 = torch.tensor(codes_0_list, device=self.snac_device, dtype=torch.int32)
        codes_1 = torch.tensor(codes_1_list, device=self.snac_device, dtype=torch.int32)
        codes_2 = torch.tensor(codes_2_list, device=self.snac_device, dtype=torch.int32)

        codes = [codes_0.unsqueeze(0), codes_1.unsqueeze(0), codes_2.unsqueeze(0)]

        # Validate token ranges
        for idx, code_tensor in enumerate(codes):
            if torch.any(code_tensor < 0) or torch.any(code_tensor > 4096):
                invalid_mask = (code_tensor < 0) | (code_tensor > 4096)
                invalid_values = code_tensor[invalid_mask].tolist()
                raise ValueError(f"Tokens out of range (0-4096) in codes_{idx}: {invalid_values}")

        # Decode with SNAC (GPU-optimized)
        with torch.inference_mode():
            # Use torch.cuda.synchronize() if on GPU for accurate timing
            if self.snac_device.startswith('cuda'):
                torch.cuda.synchronize()
            
            audio_hat = self.snac_model.decode(codes)
            
            # Keep operations on GPU as long as possible
            if self.snac_device.startswith('cuda'):
                torch.cuda.synchronize()

        # Convert to audio bytes
        # audio_hat shape: [1, 1, num_samples]
        # Don't slice - use all decoded audio
        detached_audio = audio_hat.detach().cpu().squeeze()  # Remove batch and channel dims
        
        # Clear GPU cache after moving to CPU
        if self.snac_device.startswith('cuda'):
            del audio_hat, codes
            torch.cuda.empty_cache()
        
        audio_np = detached_audio.numpy()
        audio_int16 = (audio_np * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        logger.debug(f"Generated {len(audio_bytes)} bytes from {num_frames} frames ({len(audio_bytes) // 2 / 24000:.2f}s)")

        return audio_bytes

    def _wrap_in_wav(self, pcm_bytes: bytes) -> bytes:
        """
        Wrap raw PCM bytes in WAV format.

        Args:
            pcm_bytes: Raw 16-bit PCM audio data

        Returns:
            WAV file as bytes
        """
        # SNAC produces 24kHz, 16-bit mono audio
        sample_rate = 24000
        num_channels = 1
        sample_width = 2  # 16-bit = 2 bytes

        wav_buffer = BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(num_channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        wav_buffer.seek(0)
        return wav_buffer.read()

    async def initialize(self) -> bool:
        """Initialize the vLLM audio service."""
        try:
            if self.initialized:
                return True

            self.initialized = True

            if not self._verification_attempted:
                self._verification_attempted = True
                self._verification_inflight = True
                try:
                    asyncio.create_task(self._run_connection_verification())
                except RuntimeError:
                    await self._run_connection_verification()
            else:
                logger.debug(
                    "Skipping vLLM audio verification; already attempted during this lifecycle"
                )

            if self.connection_verified:
                logger.info(
                    f"Initialized vLLM audio service with model {self.tts_model}"
                )
            elif self._verification_inflight:
                logger.info(
                    f"Initialized vLLM audio service with model {self.tts_model} "
                    f"(verification running asynchronously)"
                )
            else:
                logger.info(
                    f"Initialized vLLM audio service with model {self.tts_model} "
                    f"(verification skipped or failed)"
                )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize vLLM audio service: {str(e)}")
            return False

    async def verify_connection(self) -> bool:
        """Verify connection to the vLLM server."""
        try:
            if not self.client:
                logger.error("vLLM client is not initialized")
                return False

            # Try to list models
            try:
                await self.client.models.list()
                logger.debug("vLLM audio connection verified successfully")
                return True
            except Exception:
                # Fallback: make a minimal test request
                logger.debug("vLLM models endpoint not available, trying test request")
                response = await self.client.chat.completions.create(
                    model=self.tts_model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1,
                    temperature=0
                )

                if response and response.choices:
                    logger.debug("vLLM audio connection verified via test request")
                    return True

                return False

        except Exception as e:
            logger.error(f"vLLM audio connection verification failed: {str(e)}")
            return False

    async def _run_connection_verification(self) -> None:
        """Run connection verification without blocking the caller."""
        try:
            self.connection_verified = await self.verify_connection()
            if self.connection_verified:
                logger.debug("vLLM audio verification completed successfully (async)")
            else:
                logger.debug("vLLM audio verification completed with negative result (async)")
        except Exception as verify_error:
            self.connection_verified = False
            logger.warning(
                f"vLLM audio verification raised an exception; continuing without health check: {str(verify_error)}"
            )
        finally:
            self._verification_inflight = False

    async def close(self) -> None:
        """Close the vLLM audio service and release resources."""
        if self.client:
            await self.client.close()
            self.client = None

        if self.connection_manager:
            await self.connection_manager.close()

        # Clean up GPU memory if using CUDA
        if self.snac_device.startswith('cuda') and SNAC_AVAILABLE and torch is not None:
            if torch.cuda.is_available():
                # Clear model from GPU
                if self.snac_model is not None:
                    del self.snac_model
                    self.snac_model = None
                torch.cuda.empty_cache()
                logger.debug("GPU memory cleared")

        self.initialized = False
        self._verification_attempted = False
        self.connection_verified = False
        self._verification_inflight = False
        self._snac_initialized = False
        logger.debug("Closed vLLM audio service")

    async def text_to_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        format: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """
        Convert text to speech audio using vLLM-served TTS model.

        For Orpheus models, this generates audio tokens that need to be decoded.
        The vLLM server may return audio directly or as encoded data depending
        on the model configuration.

        Args:
            text: Text to convert to speech
            voice: Optional voice identifier (model-specific)
            format: Optional audio format (e.g., 'wav', 'mp3')
            **kwargs: Additional generation parameters

        Returns:
            Audio data as bytes
        """
        if not self.initialized:
            await self.initialize()

        try:
            # Validate and set voice
            # Orpheus supported voices: tara, leah, jess, leo, dan, mia, zac, zoe
            ORPHEUS_VOICES = {'tara', 'leah', 'jess', 'leo', 'dan', 'mia', 'zac', 'zoe'}
            # Common OpenAI voices that clients might pass by default
            OPENAI_VOICES = {'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx', 'nova', 'sage', 'shimmer', 'verse'}

            if voice and voice.lower() in ORPHEUS_VOICES:
                tts_voice = voice.lower()
            elif voice and voice.lower() in OPENAI_VOICES:
                # Silently use configured default for OpenAI voices (common client default)
                tts_voice = self.tts_voice
                logger.debug(
                    f"Using configured Orpheus voice '{self.tts_voice}' instead of OpenAI voice '{voice}'"
                )
            elif voice and voice.lower() not in ORPHEUS_VOICES:
                logger.warning(
                    f"Voice '{voice}' is not a valid Orpheus voice. "
                    f"Using configured default: {self.tts_voice}"
                )
                tts_voice = self.tts_voice
            else:
                tts_voice = self.tts_voice

            audio_format = format or self.tts_format

            # For Orpheus-style models, construct the prompt with voice specification
            # The model expects a specific format for TTS
            text_prompt = f"{tts_voice}: {text}"

            # Orpheus requires special token IDs to trigger audio generation
            # Based on Orpheus source code:
            # - Token 128259: Start audio generation marker
            # - Token 128009: End of turn ID (from Llama 3)
            # - Token 128260: Audio end marker
            # - Token 128261: Audio generation marker
            # - Token 128257: Control token
            #
            # The prompt format is:
            # [128259] + tokenized("voice: text") + [128009, 128260, 128261, 128257]

            # Use completions API with prompt_token_ids for precise control
            # First, we need to get the tokenized version
            # Since we can't tokenize directly, we'll construct the prompt with special token strings

            # The special tokens in Orpheus vocabulary (confirmed via vLLM tokenizer):
            # Token 128259 = <custom_token_3> (start audio generation)
            # Token 128009 = <|eot_id|> (end of turn)
            # Token 128260 = <custom_token_4> (audio end)
            # Token 128261 = <custom_token_5> (generate audio)
            # Token 128257 = <custom_token_1> (control token)
            START_AUDIO_TOKEN = "<custom_token_3>"
            END_AUDIO_TOKENS = "<|eot_id|><custom_token_4><custom_token_5><custom_token_1>"

            prompt = f"{START_AUDIO_TOKEN}{text_prompt}{END_AUDIO_TOKENS}"

            # Use completions API (not chat) to avoid chat template interference
            # Orpheus models expect raw prompts without chat template wrapping
            # Use semaphore to limit concurrent requests and prevent server overload
            async with self._request_semaphore:
                response = await self.client.completions.create(
                    model=self.tts_model,
                    prompt=prompt,
                    temperature=kwargs.get('temperature', self.temperature),
                    top_p=kwargs.get('top_p', self.top_p),
                    max_tokens=kwargs.get('max_tokens', self.max_tokens),
                    extra_body={
                        "repetition_penalty": kwargs.get('repetition_penalty', self.repetition_penalty),
                        "skip_special_tokens": False,  # CRITICAL: Keep audio tokens in output
                    }
                )

            # Extract generated content from completions response
            generated_text = response.choices[0].text

            # Process the response based on model output type
            audio_data = self._process_tts_response(generated_text, audio_format)

            return audio_data

        except Exception as e:
            logger.error(f"vLLM TTS error: {str(e)}")
            raise

    def _construct_tts_prompt(self, text: str, voice: str) -> str:
        """
        Construct TTS prompt for Orpheus-style models.

        Args:
            text: Text to convert to speech
            voice: Voice identifier

        Returns:
            Formatted prompt for TTS generation
        """
        # Orpheus models use special tokens for TTS
        # Based on Orpheus source code, the format uses specific token IDs:
        # - Start token: 128259 (decodes to a special audio start marker)
        # - End tokens: 128009, 128260, 128261, 128257
        #
        # The actual prompt format is: <special_start>voice: text<special_end>
        # When using vLLM's tokenizer, these become special tokens.

        # Check for Orpheus model pattern
        if 'orpheus' in self.tts_model.lower():
            # Orpheus 3B uses this format (based on their _format_prompt code):
            # The special tokens are part of the Llama-3 extended vocabulary
            # Token 128259 = start of audio generation
            # Token 128257 = audio generation control token
            # Format: voice: text (the tokenizer adds special tokens)

            # For vLLM, we need to use the special token strings
            # These are typically: <|reserved_special_token_XXX|> in Llama-3
            # Or custom tokens added by Orpheus

            # The key is to trigger audio token generation mode
            # Based on Orpheus examples, the format is:
            # <|begin_of_text|>voice: text
            # And let the model generate audio tokens after

            # Simplified format that should work with vLLM
            prompt = f"{voice}: {text}"
        else:
            # Generic TTS prompt
            prompt = f"[Voice: {voice}] {text}"

        return prompt

    def _process_tts_response(self, response_text: str, audio_format: str) -> bytes:
        """
        Process TTS model response to extract audio data.

        The response may contain:
        - Audio tokens (e.g., <custom_token_XXXXX>) that need SNAC decoding
        - Base64-encoded audio data
        - Direct audio bytes

        Args:
            response_text: Generated text from model
            audio_format: Expected audio format

        Returns:
            Audio data as bytes
        """
        # First, check if response contains Orpheus-style audio tokens
        tokens = self._extract_audio_tokens(response_text)

        if tokens:
            logger.debug(f"Extracted {len(tokens)} audio tokens from model response")

            if not SNAC_AVAILABLE:
                raise RuntimeError(
                    "SNAC library required for audio token decoding. "
                    "Install with: pip install snac torch numpy"
                )

            try:
                # Decode tokens to raw PCM audio
                pcm_audio = self._convert_tokens_to_audio(tokens)
                logger.debug(f"Decoded {len(pcm_audio)} bytes of PCM audio")

                # Wrap in WAV format if requested
                if audio_format.lower() in ['wav', 'wave']:
                    return self._wrap_in_wav(pcm_audio)
                else:
                    # Return raw PCM for other formats
                    # In production, you'd convert to mp3/ogg etc.
                    return pcm_audio

            except Exception as e:
                logger.error(f"Failed to decode audio tokens: {str(e)}")
                raise

        # Try to decode as base64 (for models that return encoded audio)
        try:
            # Check if response is base64-encoded audio
            if response_text.startswith('data:audio'):
                # Extract base64 data from data URL
                base64_data = response_text.split(',')[1]
                return base64.b64decode(base64_data)

            # Try direct base64 decode
            audio_bytes = base64.b64decode(response_text)
            return audio_bytes
        except Exception:
            pass

        # If no audio tokens and not base64, raise an error
        logger.error(
            f"TTS response does not contain audio tokens or valid audio data. "
            f"Response preview: {response_text[:200]}..."
        )
        raise ValueError("Unable to extract audio from model response")

    async def speech_to_text(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Convert speech audio to text using vLLM-served STT model.

        Note: STT support depends on whether an STT model is configured
        and served by vLLM.

        Args:
            audio: Audio data (file path or bytes)
            language: Optional language code

        Returns:
            Transcribed text
        """
        if not self.initialized:
            await self.initialize()

        if not self.stt_model:
            raise NotImplementedError(
                "Speech-to-text is not configured for this vLLM audio service. "
                "Set 'stt_model' in configuration to enable STT."
            )

        try:
            # Prepare audio data
            audio_data = self._prepare_audio(audio)
            audio_base64 = base64.b64encode(audio_data).decode('utf-8')

            # Construct STT prompt with audio data
            prompt = f"Transcribe this audio: <|audio|>{audio_base64}<|/audio|>"
            if language:
                prompt = f"[Language: {language}] {prompt}"

            response = await self.client.chat.completions.create(
                model=self.stt_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic for transcription
                max_tokens=kwargs.get('max_tokens', 2048)
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"vLLM STT error: {str(e)}")
            raise

    async def transcribe(
        self,
        audio: Union[str, bytes],
        language: Optional[str] = None,
        **kwargs
    ) -> str:
        """Transcribe audio to text (alias for speech_to_text)."""
        return await self.speech_to_text(audio, language, **kwargs)

    async def translate(
        self,
        audio: Union[str, bytes],
        source_language: Optional[str] = None,
        target_language: str = "en",
        **kwargs
    ) -> str:
        """
        Translate audio from one language to another using vLLM.

        This first transcribes the audio, then translates the text.

        Args:
            audio: Audio data (file path or bytes)
            source_language: Optional source language code
            target_language: Target language code (default: 'en')

        Returns:
            Translated text in target language
        """
        if not self.initialized:
            await self.initialize()

        try:
            # First transcribe the audio
            transcript = await self.speech_to_text(audio, source_language, **kwargs)

            # Then translate using the same model's text capabilities
            translation_prompt = (
                f"Translate the following text to {target_language}: {transcript}"
            )

            response = await self.client.chat.completions.create(
                model=self.tts_model,  # Use TTS model for translation if no separate model
                messages=[{"role": "user", "content": translation_prompt}],
                temperature=0.3,
                max_tokens=kwargs.get('max_tokens', 2048)
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"vLLM translation error: {str(e)}")
            # Fallback: return transcript if translation fails
            try:
                return await self.speech_to_text(audio, source_language, **kwargs)
            except Exception:
                raise

    def _get_timeout_config(self) -> Dict[str, int]:
        """Get timeout configuration."""
        provider_config = self._extract_provider_config()
        timeout_config = provider_config.get('timeout', {})
        return {
            'connect': timeout_config.get('connect', 15000),
            'total': timeout_config.get('total', 120000)  # Longer for audio processing
        }

    def _get_retry_config(self) -> Dict[str, Any]:
        """Get retry configuration."""
        provider_config = self._extract_provider_config()
        retry_config = provider_config.get('retry', {})
        return {
            'enabled': retry_config.get('enabled', True),
            'max_retries': retry_config.get('max_retries', 3),
            'initial_wait_ms': retry_config.get('initial_wait_ms', 1000),
            'max_wait_ms': retry_config.get('max_wait_ms', 30000),
            'exponential_base': retry_config.get('exponential_base', 2)
        }
