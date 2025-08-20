"""
Ollama embedding service implementation.
"""

import logging
from typing import List, Dict, Any, Optional

from embeddings.base import EmbeddingService
from utils.ollama_utils import OllamaBaseService


class OllamaEmbeddingService(EmbeddingService, OllamaBaseService):
    """
    Implementation of the embedding service for Ollama.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Ollama embedding service.
        
        Args:
            config: Configuration dictionary for Ollama
        """
        EmbeddingService.__init__(self, config)
        OllamaBaseService.__init__(self, config, 'embeddings')
        
        # Get dimensions from config, or set to None to determine dynamically
        self.dimensions = config.get('dimensions')
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama embedding service with retry logic for cold starts.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        # Use the base class initialization with embeddings endpoint
        success = await OllamaBaseService.initialize(self, warmup_endpoint='embeddings')
        
        if success:
            # Determine the dimensionality of the model
            dimensions = await self.get_dimensions()
            self.dimensions = dimensions
            self.logger.info(f"Initialized Ollama embedding service with model {self.config.model} ({dimensions} dimensions)")
        
        return success
    
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text with retry logic.
        
        Args:
            text: The query text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            if not await self.initialize():
                self.logger.error("Failed to initialize embedding service before query")
                raise ValueError("Failed to initialize embedding service")
        
        async def _embed():
            session = await self.session_manager.get_session()
            url = f"{self.config.base_url}/api/embeddings"
            payload = {
                "model": self.config.model,
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
        
        try:
            return await self.retry_handler.execute_with_retry(_embed)
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Ollama: {str(e)}")
            # Re-raise the exception to be handled by the caller
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents with retry logic.
        
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
        Determine the dimensionality of the embeddings with retry logic.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        if self.dimensions:
            return self.dimensions
        
        # Create a test embedding to determine dimensions
        async def _get_dims():
            session = await self.session_manager.get_session()
            url = f"{self.config.base_url}/api/embeddings"
            payload = {
                "model": self.config.model,
                "prompt": "test"
            }
            
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Ollama: {error_text}")
                    # Default fallback dimensions
                    self.dimensions = 768
                    return self.dimensions
                
                data = await response.json()
                embedding = data.get('embedding', [])
                self.dimensions = len(embedding)
                return self.dimensions
        
        try:
            return await self.retry_handler.execute_with_retry(_get_dims)
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback dimensions
            self.dimensions = 768
            return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Ollama embedding service with retry logic.
        
        Returns:
            True if the connection is working, False otherwise
        """
        # First use the base verifier
        if not await self.connection_verifier.verify_connection():
            # If model not found, try to generate a test embedding anyway
            async def _test_embedding():
                session = await self.session_manager.get_session()
                url = f"{self.config.base_url}/api/embeddings"
                payload = {
                    "model": self.config.model,
                    "prompt": "test connection"
                }
                
                self.logger.info(f"Testing embedding generation with model {self.config.model}")
                
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        self.logger.error(f"Error from Ollama: {error_text}")
                        return False
                    
                    # Verify we get a valid embedding
                    data = await response.json()
                    embedding = data.get('embedding', [])
                    
                    if not embedding or len(embedding) == 0:
                        self.logger.error("Received empty embedding from Ollama")
                        return False
                        
                    self.logger.info(f"Successfully generated test embedding with {len(embedding)} dimensions")
                    return True
            
            try:
                return await self.retry_handler.execute_with_retry(_test_embedding)
            except Exception as e:
                self.logger.error(f"Error testing embedding generation: {str(e)}")
                return False
        
        return True
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        await OllamaBaseService.close(self)