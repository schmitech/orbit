"""
Sentence Transformers base class for embedding services.

This module provides a unified base class for Sentence Transformers embedding services,
supporting both local model inference and remote Hugging Face Inference API.
"""

from typing import Dict, Any, Optional
import logging

from ..base import ProviderAIService, ServiceType
from ..connection import RetryHandler



logger = logging.getLogger(__name__)
class SentenceTransformersBaseService(ProviderAIService):
    """
    Base class for Sentence Transformers embedding services.

    This class consolidates:
    - Model loading and initialization (local or remote)
    - GPU/CPU device detection and management
    - Model caching using Hugging Face defaults
    - Connection verification
    - Retry logic with exponential backoff
    - Support for both local inference and remote API

    Supports popular models like:
    - BAAI/bge-m3 (1024 dimensions)
    - BAAI/bge-large-en-v1.5 (1024 dimensions)
    - all-MiniLM-L6-v2 (384 dimensions)
    - And any sentence-transformers compatible model
    """

    def __init__(
        self,
        config: Dict[str, Any],
        service_type: ServiceType = None,
        provider_name: str = "sentence_transformers"
    ):
        """
        Initialize the Sentence Transformers base service.

        Args:
            config: Configuration dictionary
            service_type: Type of AI service
            provider_name: Provider name (defaults to "sentence_transformers")
        """
        # For cooperative multiple inheritance
        if service_type:
            super().__init__(config, service_type, provider_name)
        else:
            super().__init__(config, ServiceType.EMBEDDING, provider_name)
        self._setup_sentence_transformers_config()

    def _setup_sentence_transformers_config(self) -> None:
        """
        Set up Sentence Transformers-specific configuration.

        This method:
        1. Extracts model and device configuration
        2. Determines mode (local or remote)
        3. Sets up model caching
        4. Configures normalization settings
        5. Initializes retry handler
        """
        st_config = self._extract_provider_config()

        # Core configuration
        self.model = self._get_model()
        self.mode = st_config.get("mode", "local")  # "local" or "remote"

        # Device configuration
        device_config = st_config.get("device", "auto")
        self.device = self._detect_device(device_config)

        # Model caching
        self.cache_folder = st_config.get("cache_folder")

        # Embedding configuration
        self.normalize_embeddings = st_config.get("normalize_embeddings", True)
        self.dimensions = st_config.get("dimensions")

        # Remote API configuration (for Hugging Face Inference API)
        if self.mode == "remote":
            self.api_key = st_config.get("api_key") or self._resolve_api_key("HUGGINGFACE_API_KEY")
            self.base_url = st_config.get("base_url", "https://api-inference.huggingface.co/models")

        # Initialize model (will be set during initialize())
        self.model_instance = None

        # Setup retry handler
        retry_config = self._get_retry_config()
        self.retry_handler = RetryHandler(**retry_config)

        logger.info(
            f"Configured Sentence Transformers service: "
            f"model={self.model}, mode={self.mode}, device={self.device}"
        )

    def _detect_device(self, device_config: str) -> str:
        """
        Detect and configure the compute device.

        Args:
            device_config: Device configuration ("auto", "cuda", "cpu", "mps")

        Returns:
            Device string to use
        """
        if device_config != "auto":
            return device_config

        # Auto-detect device
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

    async def initialize(self) -> bool:
        """
        Initialize the Sentence Transformers service.

        For local mode: Loads the model into memory
        For remote mode: Verifies API connection

        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            if self.mode == "local":
                await self._initialize_local_model()
            else:
                await self._initialize_remote_api()

            if await self.verify_connection():
                self.initialized = True
                logger.info(
                    f"Initialized Sentence Transformers service "
                    f"(mode={self.mode}, model={self.model})"
                )
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to initialize Sentence Transformers service: {str(e)}")
            return False

    async def _initialize_local_model(self) -> None:
        """
        Initialize local model loading.

        Loads the sentence-transformers model into memory with the configured device.
        """
        try:
            from sentence_transformers import SentenceTransformer

            # Build kwargs for model loading
            model_kwargs = {}
            if self.device:
                model_kwargs['device'] = self.device
            if self.cache_folder:
                model_kwargs['cache_folder'] = self.cache_folder

            logger.info(f"Loading Sentence Transformers model: {self.model}")
            self.model_instance = SentenceTransformer(self.model, **model_kwargs)
            logger.info(f"Model loaded successfully on device: {self.device}")

        except ImportError as e:
            raise ImportError(
                "sentence-transformers library not found. "
                "Install with: pip install sentence-transformers"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to load model {self.model}: {str(e)}") from e

    async def _initialize_remote_api(self) -> None:
        """
        Initialize remote API connection.

        Sets up the session for Hugging Face Inference API calls.
        """
        if not self.api_key:
            raise ValueError("API key required for remote mode")

        # Use the connection manager from base class

        logger.info(f"Configured remote API for model: {self.model}")

    async def verify_connection(self) -> bool:
        """
        Verify the service connection.

        For local mode: Check if model is loaded
        For remote mode: Test API connection

        Returns:
            True if the connection is working, False otherwise
        """
        try:
            if self.mode == "local":
                return self.model_instance is not None
            else:
                # For remote, we'll verify on first actual embedding call
                return self.api_key is not None
        except Exception as e:
            logger.error(f"Connection verification failed: {str(e)}")
            return False

    async def close(self) -> None:
        """
        Close the service and release resources.
        """
        try:
            if self.mode == "local" and self.model_instance:
                # Clear model from memory
                del self.model_instance
                self.model_instance = None

                # Clear CUDA cache if available
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass

            self.initialized = False
            logger.debug("Closed Sentence Transformers service")
        except Exception as e:
            logger.error(f"Error closing Sentence Transformers service: {str(e)}")

    def _get_batch_size(self, default: int = 32) -> int:
        """
        Get batch size configuration.

        Args:
            default: Default batch size if not configured

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
        # Read from config if dimensions not already set
        if self.dimensions is None:
            provider_config = self._extract_provider_config()
            self.dimensions = provider_config.get("dimensions")
        return self.dimensions
