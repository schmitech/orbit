"""
Shared utilities for Ollama services.

This module provides common functionality used across all Ollama-based services
including embeddings, inference, moderation, and reranking.
"""

import logging
import asyncio
import aiohttp
from typing import Dict, Any, Optional, Callable, TypeVar, Union
from functools import wraps

T = TypeVar('T')

class OllamaConfig:
    """Configuration parser for Ollama services."""
    
    def __init__(self, config: Dict[str, Any], service_type: str = ""):
        """
        Initialize Ollama configuration.
        
        Args:
            config: Configuration dictionary
            service_type: Type of service (embeddings, inference, moderators, rerankers)
        """
        # Extract service-specific config if available
        if service_type:
            service_config = config.get(service_type, {}).get('ollama', {})
        else:
            service_config = config.get('ollama', {})
        
        # Check if enabled (for rerankers, embeddings, moderators)
        # Inference doesn't use enabled flag as it's a core service
        if service_type and service_type in ['rerankers', 'embeddings', 'moderators']:
            enabled = service_config.get('enabled', True)
            if enabled is False:
                from server.utils import is_true_value
                if not is_true_value(enabled):
                    raise ValueError(f"Ollama provider is disabled for {service_type}")
        
        # Base configuration
        self.base_url = service_config.get('base_url', 'http://localhost:11434')
        self.model = service_config.get('model', self._get_default_model(service_type))
        
        # Retry configuration
        retry_config = service_config.get('retry', {})
        self.retry_enabled = retry_config.get('enabled', True)
        self.max_retries = retry_config.get('max_retries', 5)
        self.initial_wait_ms = retry_config.get('initial_wait_ms', 2000)
        self.max_wait_ms = retry_config.get('max_wait_ms', 30000)
        self.exponential_base = retry_config.get('exponential_base', 2)
        
        # Timeout configuration
        timeout_config = service_config.get('timeout', {})
        self.connect_timeout = timeout_config.get('connect', 10000) / 1000  # Convert to seconds
        self.total_timeout = timeout_config.get('total', 60000) / 1000  # Convert to seconds
        self.warmup_timeout = timeout_config.get('warmup', 45000) / 1000  # Convert to seconds
        
        # Additional parameters
        self.temperature = service_config.get('temperature', 0.1)
        self.dimensions = service_config.get('dimensions')
    
    def _get_default_model(self, service_type: str) -> str:
        """Get default model based on service type."""
        defaults = {
            'embeddings': 'nomic-embed-text',
            'inference': 'gemma3:1b',
            'moderators': 'gemma3:12b',
            'rerankers': 'xitao/bge-reranker-v2-m3:'
        }
        return defaults.get(service_type, 'gemma3:1b')


class OllamaSessionManager:
    """Manages aiohttp session lifecycle for Ollama services."""
    
    def __init__(self, total_timeout: float = 60.0, 
                 connection_limit: int = 10,
                 per_host_limit: int = 5):
        """
        Initialize session manager.
        
        Args:
            total_timeout: Total timeout in seconds
            connection_limit: Total connection limit
            per_host_limit: Per-host connection limit
        """
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self.total_timeout = total_timeout
        self.connection_limit = connection_limit
        self.per_host_limit = per_host_limit
        self.logger = logging.getLogger(__name__)
    
    async def get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp client session.
        Uses a lock to prevent multiple session creations.
        
        Returns:
            An aiohttp ClientSession
        """
        async with self._session_lock:
            if self.session is None or self.session.closed:
                # Configure TCP connector with limits
                connector = aiohttp.TCPConnector(
                    limit=self.connection_limit,
                    limit_per_host=self.per_host_limit,
                    ttl_dns_cache=300,  # Cache DNS results for 5 minutes
                )
                timeout = aiohttp.ClientTimeout(total=self.total_timeout)
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
            return self.session
    
    async def close(self) -> None:
        """Close the session and release resources."""
        try:
            if self.session and not self.session.closed:
                await self.session.close()
                self.logger.debug("Closed aiohttp session")
        except Exception as e:
            self.logger.error(f"Error closing session: {str(e)}")
        finally:
            self.session = None


class OllamaRetryHandler:
    """Handles retry logic with exponential backoff for Ollama services."""
    
    def __init__(self, config: OllamaConfig, logger: Optional[logging.Logger] = None):
        """
        Initialize retry handler.
        
        Args:
            config: OllamaConfig instance
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
    
    async def execute_with_retry(self, func: Callable, *args, **kwargs) -> T:
        """
        Execute a function with exponential backoff retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func
            
        Raises:
            Last exception if all retries fail
        """
        if not self.config.retry_enabled:
            return await func(*args, **kwargs)
        
        last_exception = None
        for attempt in range(self.config.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                # Check if it's a connection/timeout error that warrants retry
                error_msg = str(e).lower()
                retryable_errors = ['timeout', 'connection', 'refused', 'reset', 'unavailable']
                
                if any(x in error_msg for x in retryable_errors):
                    wait_time = min(
                        self.config.initial_wait_ms * (self.config.exponential_base ** attempt),
                        self.config.max_wait_ms
                    ) / 1000  # Convert to seconds
                    
                    if attempt < self.config.max_retries - 1:
                        self.logger.warning(
                            f"Request attempt {attempt + 1}/{self.config.max_retries} failed: {str(e)}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        self.logger.error(f"Request failed after {self.config.max_retries} attempts")
                        raise last_exception
                else:
                    # Non-retryable error
                    raise
        
        if last_exception:
            raise last_exception


class OllamaModelWarmer:
    """Handles model warm-up for Ollama services."""
    
    def __init__(self, base_url: str, model: str, 
                 session_manager: OllamaSessionManager,
                 retry_handler: OllamaRetryHandler,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize model warmer.
        
        Args:
            base_url: Ollama base URL
            model: Model name
            session_manager: Session manager instance
            retry_handler: Retry handler instance
            logger: Optional logger instance
        """
        self.base_url = base_url
        self.model = model
        self.session_manager = session_manager
        self.retry_handler = retry_handler
        self.logger = logger or logging.getLogger(__name__)
    
    async def warmup_model(self, endpoint: str = "generate", 
                          warmup_prompt: str = "warmup test",
                          timeout: float = 45.0) -> bool:
        """
        Warm up the model by sending a test request.
        
        Args:
            endpoint: API endpoint to use (generate, embeddings, chat)
            warmup_prompt: Test prompt to send
            timeout: Warmup timeout in seconds
            
        Returns:
            True if warmup successful, False otherwise
        """
        if not self.retry_handler.config.retry_enabled:
            return True
        
        self.logger.info(f"Warming up Ollama model {self.model}...")
        
        for attempt in range(self.retry_handler.config.max_retries):
            try:
                session = await self.session_manager.get_session()
                
                # Build appropriate payload based on endpoint
                if endpoint == "embeddings":
                    url = f"{self.base_url}/api/embeddings"
                    payload = {
                        "model": self.model,
                        "prompt": warmup_prompt
                    }
                elif endpoint == "chat":
                    url = f"{self.base_url}/api/chat"
                    payload = {
                        "model": self.model,
                        "messages": [{"role": "user", "content": warmup_prompt}],
                        "stream": False,
                        "max_tokens": 1
                    }
                else:  # generate
                    url = f"{self.base_url}/api/generate"
                    payload = {
                        "model": self.model,
                        "prompt": warmup_prompt,
                        "stream": False,
                        "num_predict": 1
                    }
                
                timeout_obj = aiohttp.ClientTimeout(total=timeout)
                async with session.post(url, json=payload, timeout=timeout_obj) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Verify we got a valid response
                        if endpoint == "embeddings" and data.get('embedding'):
                            self.logger.info(f"Model {self.model} warmed up successfully")
                            return True
                        elif endpoint in ["generate", "chat"] and (data.get('response') or data.get('message')):
                            self.logger.info(f"Model {self.model} warmed up successfully")
                            return True
                    else:
                        raise Exception(f"Warmup failed with status {response.status}")
                        
            except Exception as e:
                wait_time = min(
                    self.retry_handler.config.initial_wait_ms * (self.retry_handler.config.exponential_base ** attempt),
                    self.retry_handler.config.max_wait_ms
                ) / 1000  # Convert to seconds
                
                if attempt < self.retry_handler.config.max_retries - 1:
                    self.logger.warning(
                        f"Model warmup attempt {attempt + 1}/{self.retry_handler.config.max_retries} failed: {str(e)}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.warning(f"Model warmup failed after {self.retry_handler.config.max_retries} attempts")
                    return False
        
        return False


class OllamaConnectionVerifier:
    """Verifies connectivity to Ollama services."""
    
    def __init__(self, base_url: str, model: str,
                 session_manager: OllamaSessionManager,
                 logger: Optional[logging.Logger] = None):
        """
        Initialize connection verifier.
        
        Args:
            base_url: Ollama base URL
            model: Model name
            session_manager: Session manager instance
            logger: Optional logger instance
        """
        self.base_url = base_url
        self.model = model
        self.session_manager = session_manager
        self.logger = logger or logging.getLogger(__name__)
    
    async def verify_connection(self, check_model: bool = True) -> bool:
        """
        Verify the connection to Ollama.
        
        Args:
            check_model: Whether to check if the model exists
            
        Returns:
            True if connection is working, False otherwise
        """
        try:
            session = await self.session_manager.get_session()
            url = f"{self.base_url}/api/tags"
            
            self.logger.info(f"Verifying connection to Ollama at {self.base_url}")
            
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to connect to Ollama: {response.status}")
                    return False
                
                if check_model:
                    data = await response.json()
                    models = [model.get('name') for model in data.get('models', [])]
                    
                    self.logger.info(f"Available models in Ollama: {models}")
                    
                    model_found = any(
                        m.startswith(self.model) or  # Exact match or starts with our model name
                        m.split(':')[0] == self.model  # Match base name without tag
                        for m in models
                    )
                    
                    if not model_found:
                        self.logger.warning(
                            f"Model {self.model} not found in Ollama. "
                            f"Available models: {models}"
                        )
                        self.logger.warning(f"Please pull the model with: ollama pull {self.model}")
                        return False
                
                self.logger.info(f"Successfully verified connection to Ollama with model {self.model}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error verifying connection to Ollama: {str(e)}")
            return False


class OllamaBaseService:
    """Base class for Ollama services with common functionality."""
    
    def __init__(self, config: Dict[str, Any], service_type: str = ""):
        """
        Initialize base Ollama service.
        
        Args:
            config: Configuration dictionary
            service_type: Type of service (embeddings, inference, moderators, rerankers)
        """
        self.config = OllamaConfig(config, service_type)
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Initialize components
        self.session_manager = OllamaSessionManager(
            total_timeout=self.config.total_timeout,
            connection_limit=10,
            per_host_limit=5
        )
        
        self.retry_handler = OllamaRetryHandler(self.config, self.logger)
        
        self.model_warmer = OllamaModelWarmer(
            base_url=self.config.base_url,
            model=self.config.model,
            session_manager=self.session_manager,
            retry_handler=self.retry_handler,
            logger=self.logger
        )
        
        self.connection_verifier = OllamaConnectionVerifier(
            base_url=self.config.base_url,
            model=self.config.model,
            session_manager=self.session_manager,
            logger=self.logger
        )
        
        # State management
        self.initialized = False
        self._init_lock = asyncio.Lock()
        self._initializing = False
    
    async def initialize(self, warmup_endpoint: str = "generate") -> bool:
        """
        Initialize the Ollama service with retry logic for cold starts.
        
        Args:
            warmup_endpoint: API endpoint to use for warmup
            
        Returns:
            True if initialization was successful, False otherwise
        """
        # If already initialized, return immediately
        if self.initialized:
            return True
        
        # Use a lock to prevent concurrent initializations
        async with self._init_lock:
            # Double-check that it's not initialized after acquiring the lock
            if self.initialized:
                return True
            
            # Check if we're already in the process of initializing
            if self._initializing:
                self.logger.debug("Already initializing, waiting for completion")
                return self.initialized
            
            self._initializing = True
            
            try:
                # First, warm up the model
                await self.model_warmer.warmup_model(
                    endpoint=warmup_endpoint,
                    timeout=self.config.warmup_timeout
                )
                
                # Check if the model is available
                if await self.connection_verifier.verify_connection():
                    self.logger.info(f"Initialized {self.__class__.__name__} with model {self.config.model}")
                    self.initialized = True
                    return True
                return False
            except Exception as e:
                self.logger.error(f"Failed to initialize {self.__class__.__name__}: {str(e)}")
                await self.close()
                return False
            finally:
                self._initializing = False
    
    async def close(self) -> None:
        """Close the service and release any resources."""
        try:
            await self.session_manager.close()
            self.logger.debug(f"Closed {self.__class__.__name__}")
        except Exception as e:
            self.logger.error(f"Error closing {self.__class__.__name__}: {str(e)}")
        finally:
            self.initialized = False
            self._initializing = False