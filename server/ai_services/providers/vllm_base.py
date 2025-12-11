"""vLLM base class for dual-mode support (direct and API modes).

This module provides a base class for vLLM services that supports:
1. Direct mode: Load models in-process using vLLM engine
2. API mode: Connect to a running vLLM server via OpenAI-compatible API
"""

from typing import Dict, Any, Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler
import logging

logger = logging.getLogger(__name__)


class VLLMBaseService(ProviderAIService):
    """
    Base class for vLLM services.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible vLLM server
    2. Direct mode: Loads models directly using vLLM engine (requires GPU)
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "vllm"):
        """
        Initialize the vLLM base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "vllm")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_vllm_config()

    def _setup_vllm_config(self) -> None:
        """Setup vLLM configuration based on mode."""
        vllm_config = self._extract_provider_config()

        # Determine mode: API or Direct
        # Default to "api" for backward compatibility (previous version only supported API mode)
        self.mode = vllm_config.get("mode", "api")

        if self.mode == "direct":
            self._setup_direct_mode(vllm_config)
        else:
            self._setup_api_mode(vllm_config)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)

    def _setup_api_mode(self, vllm_config: Dict[str, Any]) -> None:
        """Setup for API mode (OpenAI-compatible server)."""
        host = vllm_config.get("host", "localhost")
        port = vllm_config.get("port", 8000)
        self.base_url = vllm_config.get("base_url", f"http://{host}:{port}/v1")
        self.model = self._get_model()
        self.api_key = vllm_config.get("api_key", "not-needed")

        # vLLM server is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=self.api_key if self.api_key else "not-needed",
            base_url=self.base_url
        )

        self.vllm_engine = None
        self.executor = None

        logger.info(f"Configured vLLM in API mode at {self.base_url}")

    def _setup_direct_mode(self, vllm_config: Dict[str, Any]) -> None:
        """Setup for direct mode (in-process model loading with vLLM engine)."""
        # Model configuration
        self.model = vllm_config.get("model") or vllm_config.get("model_path")
        if not self.model:
            raise ValueError("'model' or 'model_path' must be specified for vLLM direct mode")

        # GPU and parallelism settings
        self.tensor_parallel_size = vllm_config.get("tensor_parallel_size", 1)
        self.pipeline_parallel_size = vllm_config.get("pipeline_parallel_size", 1)
        self.gpu_memory_utilization = vllm_config.get("gpu_memory_utilization", 0.90)
        self.max_model_len = vllm_config.get("max_model_len", 4096)

        # Quantization settings
        self.quantization = vllm_config.get("quantization")  # e.g., "awq", "gptq", "squeezellm"
        self.dtype = vllm_config.get("dtype", "auto")  # "auto", "half", "float16", "bfloat16", "float32"

        # Trust remote code (for custom models)
        self.trust_remote_code = vllm_config.get("trust_remote_code", False)

        # Seed for reproducibility
        self.seed = vllm_config.get("seed")

        # Enforce eager mode (disable CUDA graphs for debugging)
        self.enforce_eager = vllm_config.get("enforce_eager", False)

        # Swap space (CPU offloading)
        self.swap_space = vllm_config.get("swap_space", 4)  # GB

        # KV cache dtype
        self.kv_cache_dtype = vllm_config.get("kv_cache_dtype", "auto")

        # Initialize engine
        self.vllm_engine = None
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)

        logger.info(f"Configured vLLM in direct mode with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize vLLM (load model in direct mode or verify API connection)."""
        try:
            if self.mode == "direct" and not self.vllm_engine:
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._load_direct_model
                )
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize vLLM: {str(e)}")
            return False

    def _load_direct_model(self):
        """
        Load the vLLM model directly.
        This runs in a separate thread to avoid blocking.
        """
        try:
            from vllm import LLM

            logger.info(f"Loading vLLM model: {self.model}")

            # Build engine arguments
            engine_args = {
                "model": self.model,
                "tensor_parallel_size": self.tensor_parallel_size,
                "pipeline_parallel_size": self.pipeline_parallel_size,
                "gpu_memory_utilization": self.gpu_memory_utilization,
                "max_model_len": self.max_model_len,
                "trust_remote_code": self.trust_remote_code,
                "enforce_eager": self.enforce_eager,
                "swap_space": self.swap_space,
                "dtype": self.dtype,
                "kv_cache_dtype": self.kv_cache_dtype,
            }

            # Add optional arguments
            if self.quantization:
                engine_args["quantization"] = self.quantization
            if self.seed is not None:
                engine_args["seed"] = self.seed

            self.vllm_engine = LLM(**engine_args)

            logger.info(f"vLLM model {self.model} loaded successfully")

        except ImportError:
            error_msg = "vllm package not installed. Please install with: pip install vllm"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading vLLM model: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """Verify vLLM connection/model is ready."""
        if self.mode == "api":
            try:
                # Try to list models to verify connection
                await self.client.models.list()
                return True
            except Exception as e:
                logger.error(f"Failed to verify vLLM API connection: {str(e)}")
                return False
        else:
            # For direct mode, check if engine is loaded
            if not self.vllm_engine:
                try:
                    await self.initialize()
                    return self.initialized
                except Exception as e:
                    logger.error(f"Failed to verify vLLM model: {str(e)}")
                    return False
            return True

    async def close(self) -> None:
        """Close vLLM resources."""
        if self.client:
            await self.client.close()
        if self.executor:
            self.executor.shutdown(wait=True)
        # vLLM engine cleanup
        if self.vllm_engine:
            del self.vllm_engine
            self.vllm_engine = None
        self.initialized = False

    def _handle_vllm_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle vLLM errors with logging."""
        logger.error(f"vLLM error during {operation}: {str(error)}")

    def _get_temperature(self, default: float = 0.7) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 1024) -> int:
        """Get max tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 1.0) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_top_k(self, default: int = -1) -> int:
        """Get top_k configuration (-1 means disabled)."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_k', default)

    def _get_stop_tokens(self) -> list:
        """Get stop tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('stop', [])
