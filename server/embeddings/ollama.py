"""
Ollama embedding service implementation.
"""

import logging
import aiohttp
import json
from typing import List, Dict, Any, Optional
import asyncio

from embeddings.base import EmbeddingService


class OllamaEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for Ollama.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama embedding service.
        
        Args:
            config: Configuration dictionary for Ollama
        """
        super().__init__(config)
        self.base_url = config.get('base_url', 'http://localhost:11434')
        self.model = config.get('model', 'nomic-embed-text')
        self.session = None
        self.dimensions = None  # Will be determined during initialization
        self._session_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initializing = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
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
                    limit=10,  # Limit total number of connections
                    limit_per_host=5,  # Limit connections per host
                    ttl_dns_cache=300,  # Cache DNS results for 5 minutes
                )
                timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds total timeout
                self.session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
                )
            return self.session
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama embedding service.
        
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
                # Check if the model is available
                if await self.verify_connection():
                    # Determine the dimensionality of the model
                    dimensions = await self.get_dimensions()
                    self.dimensions = dimensions
                    self.logger.info(f"Initialized Ollama embedding service with model {self.model} ({dimensions} dimensions)")
                    self.initialized = True
                    return True
                return False
            except Exception as e:
                self.logger.error(f"Failed to initialize Ollama embedding service: {str(e)}")
                await self.close()
                return False
            finally:
                self._initializing = False
    
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.
        
        Args:
            text: The query text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            if not await self.initialize():
                self.logger.error("Failed to initialize embedding service before query")
                raise ValueError("Failed to initialize embedding service")
        
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/embeddings"
            payload = {
                "model": self.model,
                "prompt": text
            }
            
            self.logger.debug(f"Sending embedding request to {url} for text: {text[:50]}...")
            
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Ollama: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")
                
                data = await response.json()
                embedding = data.get('embedding', [])
                
                # Verify we got a valid embedding
                if not embedding or not isinstance(embedding, list) or len(embedding) == 0:
                    self.logger.error(f"Received invalid embedding from Ollama: {embedding}")
                    raise ValueError(f"Received invalid embedding from Ollama")
                    
                self.logger.debug(f"Successfully generated embedding with {len(embedding)} dimensions")
                return embedding
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Ollama: {str(e)}")
            # Re-raise the exception to be handled by the caller
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.
        
        Args:
            texts: A list of document texts to embed
            
        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize embedding service")
        
        embeddings = []
        for text in texts:
            embedding = await self.embed_query(text)
            embeddings.append(embedding)
        
        return embeddings
    
    async def get_dimensions(self) -> int:
        """
        Determine the dimensionality of the embeddings.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        if self.dimensions:
            return self.dimensions
        
        # Create a test embedding to determine dimensions
        try:
            # Don't use embed_query here as it would create an initialization loop
            session = await self._get_session()
            url = f"{self.base_url}/api/embeddings"
            payload = {
                "model": self.model,
                "prompt": "test"
            }
            
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Ollama: {error_text}")
                    # Default fallback dimensions
                    return 768
                
                data = await response.json()
                embedding = data.get('embedding', [])
                return len(embedding)
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback dimensions
            return 768
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Ollama embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/tags"
            
            self.logger.info(f"Verifying connection to Ollama at {self.base_url}")
            
            async with session.get(url) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to connect to Ollama: {response.status}")
                    return False
                
                data = await response.json()
                
                # Check if our model is in the list, considering :latest tag
                models = [model.get('name') for model in data.get('models', [])]
                
                self.logger.info(f"Available models in Ollama: {models}")
                
                model_found = any(
                    m.startswith(self.model) or  # Exact match or starts with our model name
                    m.split(':')[0] == self.model  # Match base name without tag
                    for m in models
                )
                
                if not model_found:
                    self.logger.warning(f"Embedding model {self.model} not found in Ollama. Available models: {models}")
                    # Try to generate a test embedding anyway
                    try:
                        # Don't use embed_query here as it would create an initialization loop
                        url = f"{self.base_url}/api/embeddings"
                        payload = {
                            "model": self.model,
                            "prompt": "test connection"
                        }
                        
                        self.logger.info(f"Testing embedding generation with model {self.model}")
                        
                        async with session.post(url, json=payload) as embed_response:
                            if embed_response.status != 200:
                                error_text = await embed_response.text()
                                self.logger.error(f"Error from Ollama: {error_text}")
                                return False
                            
                            # Verify we get a valid embedding
                            data = await embed_response.json()
                            embedding = data.get('embedding', [])
                            
                            if not embedding or len(embedding) == 0:
                                self.logger.error("Received empty embedding from Ollama")
                                return False
                                
                            self.logger.info(f"Successfully generated test embedding with {len(embedding)} dimensions")
                            return True
                    except Exception as e:
                        self.logger.error(f"Failed to generate test embedding: {str(e)}")
                        return False
                
                self.logger.info(f"Successfully verified connection to Ollama with model {self.model}")
                return True
        except Exception as e:
            self.logger.error(f"Error verifying connection to Ollama: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        try:
            if self.session and not self.session.closed:
                await self.session.close()
        except Exception as e:
            self.logger.error(f"Error closing Ollama embedding service session: {str(e)}")
        finally:
            self.session = None
            self.initialized = False
            self._initializing = False