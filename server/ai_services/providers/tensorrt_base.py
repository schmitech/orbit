"""TensorRT-LLM base class for dual-mode support (direct and API modes).

This module provides a base class for TensorRT-LLM services that supports:
1. Direct mode: Load models in-process using TensorRT-LLM's LLM class
2. API mode: Connect to a running trtllm-serve server via OpenAI-compatible API
"""

from typing import Dict, Any
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler
import logging

logger = logging.getLogger(__name__)


class TensorRTBaseService(ProviderAIService):
    """
    Base class for TensorRT-LLM services.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible trtllm-serve server
    2. Direct mode: Loads models directly using TensorRT-LLM's LLM class (requires GPU)
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "tensorrt"):
        """
        Initialize the TensorRT-LLM base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "tensorrt")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_tensorrt_config()

    def _setup_tensorrt_config(self) -> None:
        """Setup TensorRT-LLM configuration based on mode."""
        tensorrt_config = self._extract_provider_config()

        # Determine mode: API or Direct
        # Default to "direct" for TensorRT-LLM (primary use case is GPU inference)
        self.mode = tensorrt_config.get("mode", "direct")

        if self.mode == "direct":
            self._setup_direct_mode(tensorrt_config)
        else:
            self._setup_api_mode(tensorrt_config)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)

    def _setup_api_mode(self, tensorrt_config: Dict[str, Any]) -> None:
        """Setup for API mode (OpenAI-compatible trtllm-serve server)."""
        host = tensorrt_config.get("host", "localhost")
        port = tensorrt_config.get("port", 8000)
        self.base_url = tensorrt_config.get("base_url", f"http://{host}:{port}/v1")
        self.model = self._get_model()
        self.api_key = tensorrt_config.get("api_key", "not-needed")

        # trtllm-serve is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=self.api_key if self.api_key else "not-needed",
            base_url=self.base_url
        )

        self.trt_engine = None
        self.executor = None

        logger.info(f"Configured TensorRT-LLM in API mode at {self.base_url}")

    def _setup_direct_mode(self, tensorrt_config: Dict[str, Any]) -> None:
        """Setup for direct mode (in-process model loading with TensorRT-LLM)."""
        # Model configuration
        self.model = tensorrt_config.get("model") or tensorrt_config.get("model_path")
        if not self.model:
            raise ValueError("'model' or 'model_path' must be specified for TensorRT-LLM direct mode")

        # Resolve environment variables in model path
        if isinstance(self.model, str) and self.model.startswith('${') and self.model.endswith('}'):
            env_var = self.model[2:-1]
            self.model = os.environ.get(env_var)
            if not self.model:
                raise ValueError(f"Environment variable {env_var} not set for model path")

        # GPU and parallelism settings
        self.tensor_parallel_size = tensorrt_config.get("tensor_parallel_size", 1)
        self.pipeline_parallel_size = tensorrt_config.get("pipeline_parallel_size", 1)
        self.gpu_memory_utilization = tensorrt_config.get("gpu_memory_utilization", 0.90)
        self.max_model_len = tensorrt_config.get("max_model_len", 4096)

        # Quantization settings
        self.quantization = tensorrt_config.get("quantization")  # e.g., "fp8", "int8", "int4_awq", "int4_gptq"
        self.dtype = tensorrt_config.get("dtype", "auto")  # "auto", "float16", "bfloat16", "float32"

        # KV cache dtype
        self.kv_cache_dtype = tensorrt_config.get("kv_cache_dtype", "auto")

        # Initialize engine placeholders
        self.trt_engine = None
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)

        logger.info(f"Configured TensorRT-LLM in direct mode with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize TensorRT-LLM (load model in direct mode or verify API connection)."""
        try:
            if self.mode == "direct" and not self.trt_engine:
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._load_direct_model
                )
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize TensorRT-LLM: {str(e)}")
            return False

    def _load_direct_model(self):
        """
        Load the TensorRT-LLM model directly.
        This runs in a separate thread to avoid blocking.
        """
        try:
            from tensorrt_llm import LLM

            logger.info(f"Loading TensorRT-LLM model: {self.model}")

            # Build engine arguments
            engine_args = {
                "model": self.model,
                "tensor_parallel_size": self.tensor_parallel_size,
                "pipeline_parallel_size": self.pipeline_parallel_size,
            }

            # Add optional arguments based on what TensorRT-LLM supports
            # Note: The exact parameter names may vary by TensorRT-LLM version
            if self.gpu_memory_utilization != 0.90:
                engine_args["gpu_memory_utilization"] = self.gpu_memory_utilization
            if self.max_model_len:
                engine_args["max_model_len"] = self.max_model_len
            if self.dtype != "auto":
                engine_args["dtype"] = self.dtype

            self.trt_engine = LLM(**engine_args)

            logger.info(f"TensorRT-LLM model {self.model} loaded successfully")

        except ImportError:
            error_msg = "tensorrt-llm package not installed. Please install with: pip install tensorrt-llm"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading TensorRT-LLM model: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """Verify TensorRT-LLM connection/model is ready."""
        if self.mode == "api":
            try:
                # Try to list models to verify connection
                await self.client.models.list()
                return True
            except Exception as e:
                logger.error(f"Failed to verify TensorRT-LLM API connection: {str(e)}")
                return False
        else:
            # For direct mode, check if engine is loaded
            if not self.trt_engine:
                try:
                    await self.initialize()
                    return self.initialized
                except Exception as e:
                    logger.error(f"Failed to verify TensorRT-LLM model: {str(e)}")
                    return False
            return True

    async def close(self) -> None:
        """Close TensorRT-LLM resources."""
        if self.client:
            await self.client.close()
        if self.executor:
            self.executor.shutdown(wait=True)
        # TensorRT-LLM engine cleanup
        if self.trt_engine:
            del self.trt_engine
            self.trt_engine = None
        self.initialized = False

    def _handle_tensorrt_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle TensorRT-LLM errors with logging."""
        logger.error(f"TensorRT-LLM error during {operation}: {str(error)}")

    def _get_temperature(self, default: float = 0.1) -> float:
        """Get temperature configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('temperature', default)

    def _get_max_tokens(self, default: int = 2048) -> int:
        """Get max tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('max_tokens', default)

    def _get_top_p(self, default: float = 0.8) -> float:
        """Get top_p configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_p', default)

    def _get_top_k(self, default: int = 20) -> int:
        """Get top_k configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('top_k', default)

    def _get_stop_tokens(self) -> list:
        """Get stop tokens configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('stop', [])
