"""BitNet base class for 1.58-bit LLM inference."""

from typing import Dict, Any, Optional
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler
import logging

# Configure logging to suppress BitNet-related messages

logger = logging.getLogger(__name__)
logging.getLogger('bitnet').setLevel(logging.ERROR)


class BitNetBaseService(ProviderAIService):
    """
    Base class for BitNet services.
    
    Supports two modes:
    1. Direct mode: Load 1.58-bit quantized models directly using BitNet's Python bindings
    2. API mode: Connect to BitNet inference server via HTTP/REST
    """

    def __init__(self, config: Dict[str, Any], service_type: ServiceType = None, provider_name: str = "bitnet"):
        """
        Initialize the BitNet base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "bitnet")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.INFERENCE, provider_name)
        self._setup_bitnet_config()

    def _setup_bitnet_config(self) -> None:
        """Setup BitNet configuration based on mode."""
        bitnet_config = self._extract_provider_config()

        # Determine mode: API or Direct
        self.mode = bitnet_config.get("mode", "direct")  # Default to direct mode
        self.model_path = bitnet_config.get("model_path")

        if self.mode == "direct" or self.model_path:
            # Direct mode: Load 1.58-bit quantized model directly
            self.mode = "direct"
            self._setup_direct_mode(bitnet_config)
        else:
            # API mode: Use BitNet inference server
            self._setup_api_mode(bitnet_config)

        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)

    def _setup_api_mode(self, bitnet_config: Dict[str, Any]) -> None:
        """Setup for API mode (BitNet inference server)."""
        self.base_url = bitnet_config.get("base_url", "http://localhost:8080")
        self.model = self._get_model()
        self.api_key = bitnet_config.get("api_key")

        # BitNet server is OpenAI-compatible
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=self.api_key or "not-needed", 
            base_url=self.base_url
        )

        self.bitnet_model = None
        self.executor = None

        logger.info(f"Configured BitNet in API mode at {self.base_url}")

    def _setup_direct_mode(self, bitnet_config: Dict[str, Any]) -> None:
        """Setup for direct mode (1.58-bit quantized model loading)."""
        # Support both model name and model_path for compatibility
        self.model = bitnet_config.get('model', '')

        # If both are provided, model_path takes precedence
        if not self.model_path and self.model:
            # Check if model already ends with .gguf
            if self.model.endswith('.gguf'):
                self.model_path = os.path.join('models', self.model)
            else:
                self.model_path = os.path.join('models', f"{self.model}.gguf")
        elif not self.model_path and not self.model:
            raise ValueError("Either 'model' or 'model_path' must be specified for BitNet direct mode")

        # If specified model_path doesn't exist but is a relative path, try to find it
        if not os.path.exists(self.model_path) and not os.path.isabs(self.model_path):
            # Try to locate in models directory
            models_dir = os.path.join(os.getcwd(), 'models')
            if os.path.exists(models_dir):
                potential_path = os.path.join(models_dir, os.path.basename(self.model_path))
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

        # BitNet-specific configuration
        self.quant_type = bitnet_config.get('quant_type', 'i2_s')  # i2_s or tl1
        self.use_pretuned = bitnet_config.get('use_pretuned', True)
        self.quant_embd = bitnet_config.get('quant_embd', False)
        
        # Context and threading
        self.n_ctx = bitnet_config.get('n_ctx', 2048)
        self.n_threads = bitnet_config.get('n_threads', 8)
        self.n_batch = bitnet_config.get('n_batch', 2)
        
        # GPU settings
        self.n_gpu_layers = bitnet_config.get('n_gpu_layers', 0)  # 0 = CPU only, -1 = all layers
        self.main_gpu = bitnet_config.get('main_gpu', 0)
        self.low_vram = bitnet_config.get('low_vram', False)
        
        # Memory management
        self.use_mmap = bitnet_config.get('use_mmap', True)
        self.use_mlock = bitnet_config.get('use_mlock', False)
        
        # Kernel parameters
        self.kernel_params = bitnet_config.get('kernel_params', {})
        
        # Generation parameters
        self.temperature = bitnet_config.get('temperature', 0.7)
        self.top_p = bitnet_config.get('top_p', 0.9)
        self.top_k = bitnet_config.get('top_k', 40)
        self.max_tokens = bitnet_config.get('max_tokens', 1024)
        
        # Stop sequences
        self.stop_sequences = bitnet_config.get('stop', [])

        # Initialize model
        self.bitnet_model = None
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)  # For running model inference in separate thread

        logger.info(f"Configured BitNet in direct mode with model: {self.model}")

    async def initialize(self) -> bool:
        """Initialize the BitNet service."""
        try:
            if self.mode == "direct" and not self.bitnet_model:
                # Load the model in direct mode
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._load_direct_model
                )
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize BitNet: {str(e)}")
            return False

    def _load_direct_model(self):
        """
        Load the BitNet model directly.
        This runs in a separate thread.
        """
        try:
            # Import here to avoid dependency issues if not using BitNet
            from bitnet import BitNetInference

            # Check if model path exists
            if not os.path.exists(self.model_path):
                error_msg = f"Model file not found at: {self.model_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)

            logger.info(f"Loading BitNet model from: {self.model_path}")

            # Initialize the BitNet model with specified parameters
            self.bitnet_model = BitNetInference(
                model_path=self.model_path,
                quant_type=self.quant_type,
                use_pretuned=self.use_pretuned,
                quant_embd=self.quant_embd,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                n_gpu_layers=self.n_gpu_layers,
                main_gpu=self.main_gpu,
                low_vram=self.low_vram,
                use_mmap=self.use_mmap,
                use_mlock=self.use_mlock,
                kernel_params=self.kernel_params,
                verbose=False  # Disable verbose output during initialization
            )

            logger.info(f"BitNet model {self.model} loaded successfully")
        except ImportError:
            error_msg = "BitNet package not installed. Please install with: pip install bitnet-cpp"
            logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            logger.error(f"Error loading BitNet model: {str(e)}")
            raise

    async def verify_connection(self) -> bool:
        """Verify connection to BitNet service."""
        if self.mode == "api":
            # For API mode, check if server is reachable
            try:
                if self.client:
                    # Try to list models or make a simple request
                    await self.client.models.list()
                    return True
            except Exception as e:
                logger.error(f"Failed to verify BitNet API connection: {str(e)}")
                return False
        else:
            # For direct mode, check if model is loaded
            if not self.bitnet_model:
                try:
                    await self.initialize()
                    return self.initialized
                except Exception as e:
                    logger.error(f"Failed to verify BitNet model: {str(e)}")
                    return False
            return True

    async def close(self) -> None:
        """Close the BitNet service and release resources."""
        if self.client:
            await self.client.close()
        if self.executor:
            self.executor.shutdown(wait=True)
        self.bitnet_model = None
        self.initialized = False

    def _handle_bitnet_error(self, error: Exception, operation: str = "operation") -> None:
        """Handle BitNet-specific errors."""
        logger.error(f"BitNet error during {operation}: {str(error)}")

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

    def _get_quantization_type(self) -> str:
        """Get quantization type configuration."""
        provider_config = self._extract_provider_config()
        return provider_config.get('quant_type', 'i2_s')

    def _get_use_pretuned(self) -> bool:
        """Get pretuned kernel parameters setting."""
        provider_config = self._extract_provider_config()
        return provider_config.get('use_pretuned', True)

    def _get_quant_embd(self) -> bool:
        """Get embedding quantization setting."""
        provider_config = self._extract_provider_config()
        return provider_config.get('quant_embd', False)
