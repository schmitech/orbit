"""AirLLM base class for running large models on limited GPU memory.

This module provides a base class for loading models locally using AirLLM's
layer-by-layer inference (https://github.com/lyogavin/airllm), which streams
model layers from disk so multi-billion-parameter models can run on a single
consumer GPU (or CPU) at the cost of generation speed.
"""

from typing import Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
from ..errors import raise_sanitized
import logging

logger = logging.getLogger(__name__)


class AirLLMBaseService(ProviderAIService):
    """
    Base class for local AirLLM inference.

    Loads models in-process using airllm.AutoModel, which offloads model
    layers to run large models under tight memory budgets.
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "airllm"):
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_airllm_config()

    def _setup_airllm_config(self) -> None:
        """Setup AirLLM configuration from provider config."""
        airllm_config = self._extract_provider_config()

        self.model = self._get_model()
        if not self.model:
            raise ValueError("'model' must be specified for airllm provider")

        self.compression = airllm_config.get("compression")  # None, "4bit", "8bit"
        self.max_seq_len = airllm_config.get("max_seq_len", 4096)
        self.hf_token = airllm_config.get("hf_token")
        self.device = airllm_config.get("device", "cuda:0")
        self.layer_shards_saving_path = airllm_config.get("layer_shards_saving_path")
        self.delete_original = airllm_config.get("delete_original", False)
        self.profiling_mode = airllm_config.get("profiling_mode", False)

        # Model / tokenizer populated during initialize
        self.model_instance = None
        self.tokenizer = None
        self.executor = ThreadPoolExecutor(max_workers=1)

        logger.debug(
            f"Configured AirLLM service: model={self.model}, "
            f"compression={self.compression}, max_seq_len={self.max_seq_len}"
        )

    def _load_model(self) -> None:
        """Load model via AirLLM's AutoModel. Runs in a thread via executor."""
        try:
            from airllm import AutoModel

            logger.info(f"Loading AirLLM model: {self.model}")

            kwargs: Dict[str, Any] = {
                "max_seq_len": self.max_seq_len,
                "delete_original": self.delete_original,
                "profiling_mode": self.profiling_mode,
                "device": self.device,
            }
            if self.compression:
                kwargs["compression"] = self.compression
            if self.hf_token:
                kwargs["hf_token"] = self.hf_token
            if self.layer_shards_saving_path:
                kwargs["layer_shards_saving_path"] = self.layer_shards_saving_path

            self.model_instance = AutoModel.from_pretrained(self.model, **kwargs)
            self.tokenizer = self.model_instance.tokenizer

            # On macOS, airllm.AutoModel always returns its MLX-only Llama backend
            # (AirLLMLlamaMlx), which exposes a different generate() signature than
            # the CUDA/GenerationMixin backend this service is built against.
            if type(self.model_instance).__name__ == "AirLLMLlamaMlx":
                raise RuntimeError(
                    "AirLLM's macOS (MLX) backend uses a different generation API "
                    "than this integration supports. Run this provider on Linux with "
                    "a CUDA GPU, where airllm uses its standard transformers-compatible backend."
                )

            logger.info(f"AirLLM model loaded successfully: {self.model}")

        except ImportError:
            error_msg = (
                "airllm package not installed. "
                "Install with: pip install airllm"
            )
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading AirLLM model: {e}")
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
            logger.error(f"Failed to initialize AirLLM service: {e}")
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
            logger.info("AirLLM service closed")
        except Exception as e:
            logger.error(f"Error closing AirLLM service: {e}")

    def _handle_airllm_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle AirLLM errors with logging."""
        logger.error(f"AirLLM error during {operation}: {error}")
        raise_sanitized(error, provider=self.provider_name, operation=operation)

    def _get_temperature(self, default: float = 0.7) -> float:
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 512) -> int:
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
