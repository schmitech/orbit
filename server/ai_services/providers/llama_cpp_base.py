"""Llama.cpp base class."""

from typing import Dict, Any, Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler
import logging

# Configure logging to suppress Metal-related messages
logging.getLogger('ggml_metal').setLevel(logging.ERROR)


class LlamaCppBaseService(ProviderAIService):
    """
    Base class for Llama.cpp services.

    Supports two modes:
    1. API mode: Uses OpenAI-compatible llama.cpp server
    2. Direct mode: Loads GGUF models directly using llama-cpp-python
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "llama_cpp"):
        """
        Initialize the Llama.cpp base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "llama_cpp")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_llama_cpp_config()

    def _setup_llama_cpp_config(self) -> None:
        llama_config = self._extract_provider_config()

        # Determine mode: API or Direct
        # Default to "direct" for backward compatibility (previous version only supported direct mode)
        self.mode = llama_config.get("mode", "direct")
        self.model_path = llama_config.get("model_path")

        # If model_path is specified, force direct mode (backward compatibility)
        if self.model_path and self.mode != "direct":
            self.logger.warning("model_path specified but mode is not 'direct'. Forcing direct mode.")
            self.mode = "direct"

        if self.mode == "direct":
            # Direct mode: Load GGUF model directly
            self._setup_direct_mode(llama_config)
        else:
            # API mode: Use OpenAI-compatible server
            self._setup_api_mode(llama_config)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)

    def _setup_api_mode(self, llama_config: Dict[str, Any]) -> None:
        """Setup for API mode (OpenAI-compatible server)."""
        self.base_url = llama_config.get("base_url", "http://localhost:8080")
        self.model = self._get_model()

        # Llama.cpp server is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key="not-needed", base_url=self.base_url)

        self.llama_model = None
        self.executor = None

        self.logger.info(f"Configured Llama.cpp in API mode at {self.base_url}")

    def _setup_direct_mode(self, llama_config: Dict[str, Any]) -> None:
        """Setup for direct mode (GGUF model loading)."""
        # Support both model name and model_path for compatibility
        self.model = llama_config.get('model', '')

        # If both are provided, model_path takes precedence
        if not self.model_path and self.model:
            # Check if model already ends with .gguf
            if self.model.endswith('.gguf'):
                self.model_path = os.path.join('gguf', self.model)
            else:
                self.model_path = os.path.join('gguf', f"{self.model}.gguf")
        elif not self.model_path and not self.model:
            raise ValueError("Either 'model' or 'model_path' must be specified for llama.cpp direct mode")

        # If specified model_path doesn't exist but is a relative path, try to find it in the gguf directory
        if not os.path.exists(self.model_path) and not os.path.isabs(self.model_path):
            # Try to locate in gguf directory
            gguf_dir = os.path.join(os.getcwd(), 'gguf')
            if os.path.exists(gguf_dir):
                potential_path = os.path.join(gguf_dir, os.path.basename(self.model_path))
                if os.path.exists(potential_path):
                    self.model_path = potential_path

        # If the model path contains a variable reference like ${MODEL_PATH}, try to resolve it
        if isinstance(self.model_path, str) and self.model_path.startswith('${') and self.model_path.endswith('}'):
            env_var = self.model_path[2:-1]  # Remove ${ and }
            self.model_path = os.environ.get(env_var)
            if not self.model_path:
                raise ValueError(f"Environment variable {env_var} is not set")

        # Set the model name for logging purposes if not already set
        if not self.model:
            self.model = os.path.basename(self.model_path)

        # Set other config parameters
        self.n_ctx = llama_config.get('n_ctx', 4096)
        self.n_threads = llama_config.get('n_threads', 4)
        self.n_gpu_layers = llama_config.get('n_gpu_layers', -1)  # -1 means use all layers on GPU
        self.main_gpu = llama_config.get('main_gpu', 0)
        self.tensor_split = llama_config.get('tensor_split', None)
        self.embed_type = llama_config.get('embed_type', 'llama_embedding')  # Type of embedding to use

        # Initialize model
        self.llama_model = None
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)  # For running model inference in separate thread

        self.logger.info(f"Configured Llama.cpp in direct mode with model: {self.model}")

    async def initialize(self) -> bool:
        try:
            if self.mode == "direct" and not self.llama_model:
                # Load the model in direct mode
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._load_direct_model
                )
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize Llama.cpp: {str(e)}")
            return False

    def _load_direct_model(self):
        """
        Load the llama.cpp model directly.
        This runs in a separate thread.
        """
        try:
            # Import here to avoid dependency issues if not using llama.cpp
            from llama_cpp import Llama

            # Check if model path exists
            if not os.path.exists(self.model_path):
                error_msg = f"Model file not found at: {self.model_path}"
                self.logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            self.logger.info(f"Loading llama.cpp model from: {self.model_path}")

            # Initialize the model with specified parameters
            self.llama_model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                main_gpu=self.main_gpu,
                tensor_split=self.tensor_split,
                verbose=False,  # Disable verbose output during initialization
                embedding=True  # Enable embedding support
            )

            self.logger.info(f"llama.cpp model {self.model} loaded successfully")
        except ImportError:
            error_msg = "llama_cpp package not installed. Please install with: pip install llama-cpp-python"
            self.logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            self.logger.error(f"Error loading llama.cpp model: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        if self.mode == "api":
            return True
        else:
            # For direct mode, check if model is loaded
            if not self.llama_model:
                try:
                    await self.initialize()
                    return self.initialized
                except Exception as e:
                    self.logger.error(f"Failed to verify llama.cpp model: {str(e)}")
                    return False
            return True

    async def close(self) -> None:
        if self.client:
            await self.client.close()
        if self.executor:
            self.executor.shutdown(wait=True)
        self.llama_model = None
        self.initialized = False

    def _handle_llama_cpp_error(self, error: Exception, operation: str = "operation") -> None:
        self.logger.error(f"Llama.cpp error during {operation}: {str(error)}")

    def _get_batch_size(self, default: int = 8) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default value if not configured

        Returns:
            Batch size
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('batch_size', default)

    def _get_dimensions(self) -> Optional[int]:
        """
        Get embedding dimensions configuration.

        Returns:
            Dimensions or None if not configured
        """
        provider_config = self._extract_provider_config()
        return provider_config.get('dimensions')
