"""Transformers base class for local GPU/CPU inference with HuggingFace models.

This module provides a base class for loading models locally using
AutoModelForCausalLM + AutoTokenizer from the transformers library.
Supports CUDA, MPS, and CPU devices with automatic detection.
"""

from typing import Dict, Any, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
import logging

logger = logging.getLogger(__name__)


class TransformersBaseService(ProviderAIService):
    """
    Base class for local HuggingFace Transformers inference.

    Loads models in-process using AutoModelForCausalLM and AutoTokenizer.
    For serving models via API, use vLLM or TGI instead.
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "transformers"):
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_transformers_config()

    def _setup_transformers_config(self) -> None:
        """Setup transformers configuration from provider config."""
        tf_config = self._extract_provider_config()

        self.model = self._get_model()
        if not self.model:
            raise ValueError("'model' must be specified for transformers provider")

        # Device configuration
        device_config = tf_config.get("device", "auto")
        self.device = self._detect_device(device_config)
        self.device_map = tf_config.get("device_map", "auto")
        self.trust_remote_code = tf_config.get("trust_remote_code", False)
        self.max_memory = tf_config.get("max_memory", None)
        self.attn_implementation = tf_config.get("attn_implementation", None)

        # Dtype
        dtype_str = tf_config.get("dtype", "auto")
        self.dtype = self._resolve_torch_dtype(dtype_str)

        # Model / tokenizer instances (populated during initialize)
        self.tokenizer = None
        self.model_instance = None
        self.executor = ThreadPoolExecutor(max_workers=1)

        logger.info(
            f"Configured Transformers service: model={self.model}, "
            f"device={self.device}, device_map={self.device_map}, dtype={dtype_str}"
        )

    def _detect_device(self, device_config: str) -> str:
        """Auto-detect compute device: CUDA > MPS > CPU."""
        if device_config != "auto":
            return device_config

        try:
            import torch

            if torch.cuda.is_available():
                logger.info("GPU (CUDA) detected and will be used for inference")
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                logger.info("Apple Silicon GPU (MPS) detected and will be used for inference")
                return "mps"
            else:
                logger.info("No GPU detected, using CPU for inference")
                return "cpu"
        except ImportError:
            logger.warning("PyTorch not available, defaulting to CPU")
            return "cpu"

    def _resolve_torch_dtype(self, dtype_str: str):
        """Map string config to torch.dtype. Returns string 'auto' for auto-detection."""
        if dtype_str == "auto":
            return "auto"

        try:
            import torch
            dtype_map = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }
            resolved = dtype_map.get(dtype_str)
            if resolved is None:
                logger.warning(f"Unknown dtype '{dtype_str}', falling back to auto")
                return "auto"
            return resolved
        except ImportError:
            return "auto"

    def _load_model(self) -> None:
        """Load model and tokenizer. Runs in a thread via executor."""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM

            logger.info(f"Loading Transformers model: {self.model}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model,
                trust_remote_code=self.trust_remote_code,
            )

            # Pad token fallback
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
                logger.debug("Set pad_token = eos_token (was missing)")

            # Build model kwargs
            model_kwargs: Dict[str, Any] = {
                "trust_remote_code": self.trust_remote_code,
            }

            if self.device_map is not None:
                model_kwargs["device_map"] = self.device_map

            if self.dtype != "auto":
                model_kwargs["dtype"] = self.dtype
            else:
                model_kwargs["dtype"] = "auto"

            if self.max_memory is not None:
                model_kwargs["max_memory"] = self.max_memory

            if self.attn_implementation is not None:
                model_kwargs["attn_implementation"] = self.attn_implementation

            self.model_instance = AutoModelForCausalLM.from_pretrained(
                self.model,
                **model_kwargs,
            )

            logger.info(
                f"Model loaded successfully: {self.model} "
                f"(device_map={self.device_map}, dtype={self.model_instance.dtype})"
            )

        except ImportError:
            error_msg = (
                "transformers package not installed. "
                "Install with: pip install transformers torch accelerate"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading Transformers model: {e}")
            raise

    async def initialize(self) -> bool:
        """Initialize the service by loading the model in a background thread."""
        try:
            if self.model_instance is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(self.executor, self._load_model)
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Transformers service: {e}")
            return False

    async def verify_connection(self) -> bool:
        """Verify that the model is loaded."""
        return self.model_instance is not None and self.tokenizer is not None

    async def close(self) -> None:
        """Release model, tokenizer, and GPU memory."""
        try:
            if self.model_instance is not None:
                del self.model_instance
                self.model_instance = None
            if self.tokenizer is not None:
                del self.tokenizer
                self.tokenizer = None

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.debug("CUDA cache cleared")
            except ImportError:
                pass

            if self.executor:
                self.executor.shutdown(wait=False)

            self.initialized = False
            logger.info("Transformers service closed")
        except Exception as e:
            logger.error(f"Error closing Transformers service: {e}")

    def _handle_transformers_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle transformers errors with logging."""
        logger.error(f"Transformers error during {operation}: {error}")

    def _get_temperature(self, default: float = 0.7) -> float:
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 2048) -> int:
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 0.9) -> float:
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_top_k(self, default: int = -1) -> int:
        provider_config = self._extract_provider_config()
        return provider_config.get('top_k', default)

    def _get_stop_tokens(self) -> list:
        provider_config = self._extract_provider_config()
        return provider_config.get('stop', [])
