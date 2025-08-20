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
        self.dimensions = self.config.dimensions
        
        # Debug logging for configuration (only in verbose mode)
        if self.config.verbose:
            self.logger.info(f"Ollama Embedding Config - Model: {self.config.model}, Dimensions: {self.dimensions}, Base URL: {self.config.base_url}")
    
    async def initialize(self) -> bool:
        """
        Initialize the Ollama embedding service with retry logic for cold starts.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        # Use the base class initialization with embeddings endpoint
        success = await OllamaBaseService.initialize(self, warmup_endpoint='embeddings')
        
        if success:
            # Test what dimensions the model actually produces
            await self._check_actual_dimensions()
            
            # Report the final dimensions (after any resizing)
            dimensions = await self.get_dimensions()
            self.logger.info(f"Initialized Ollama embedding service with model {self.config.model}")
            self.logger.info(f"Output dimensions: {dimensions} (configured: {self.config.dimensions})")
        
        return success
    
    async def _check_actual_dimensions(self) -> None:
        """Check what dimensions the model actually produces."""
        # Skip if we've already checked
        if hasattr(self, '_actual_dims_checked'):
            return
            
        try:
            session = await self.session_manager.get_session()
            url = f"{self.config.base_url}/api/embeddings"
            payload = {
                "model": self.config.model,
                "prompt": "test"
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    embedding = data.get('embedding', [])
                    actual_dims = len(embedding)
                    
                    if self.config.dimensions and actual_dims != self.config.dimensions:
                        self.logger.warning(
                            f"Model {self.config.model} produces {actual_dims}-dimensional embeddings, "
                            f"but config specifies {self.config.dimensions}. Embeddings will be resized."
                        )
                    else:
                        self.logger.info(f"Model {self.config.model} produces {actual_dims}-dimensional embeddings")
                    
                    self._actual_dims_checked = True
        except Exception as e:
            self.logger.error(f"Error checking actual dimensions: {str(e)}")
    
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
            
            # Try to set dimensions if configured (some models support this)
            if self.config.dimensions:
                payload["options"] = {
                    "num_ctx": self.config.dimensions,
                    "embedding_size": self.config.dimensions
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
                
                # Check if actual dimensions match configured dimensions
                actual_dims = len(embedding)
                if self.config.dimensions and actual_dims != self.config.dimensions:
                    self.logger.warning(
                        f"Dimension mismatch: Model {self.config.model} returned {actual_dims} dimensions, "
                        f"but config specifies {self.config.dimensions}."
                    )
                    
                    # Option to resize embeddings to match expected dimensions
                    if self.config.dimensions:
                        embedding = self._resize_embedding(embedding, self.config.dimensions)
                        self.logger.info(f"Resized embedding from {actual_dims} to {self.config.dimensions} dimensions")
                    
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
        Processes documents in parallel batches for better performance.
        
        Args:
            texts: A list of document texts to embed
            
        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize embedding service")
        
        if not texts:
            return []
        
        # Process in parallel batches for better performance
        import asyncio
        batch_size = 5  # Process 5 texts at a time to avoid overwhelming Ollama
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Create tasks for parallel processing
            tasks = [self.embed_query(text) for text in batch]
            
            # Wait for all tasks in this batch to complete
            try:
                batch_embeddings = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Handle any exceptions in the batch
                for j, result in enumerate(batch_embeddings):
                    if isinstance(result, Exception):
                        self.logger.error(f"Failed to embed document {i+j}: {result}")
                        # Retry individually for failed embeddings
                        try:
                            result = await self.embed_query(batch[j])
                        except Exception as e:
                            self.logger.error(f"Retry failed for document {i+j}: {e}")
                            # Use empty embedding as fallback
                            result = [0.0] * (self.dimensions or 768)
                    
                    all_embeddings.append(result)
                
                # Log progress for large batches
                if len(texts) > 20 and (i + batch_size) % 20 == 0:
                    self.logger.debug(f"Processed {min(i + batch_size, len(texts))}/{len(texts)} documents")
                    
            except Exception as e:
                self.logger.error(f"Batch processing failed, falling back to sequential: {e}")
                # Fall back to sequential processing for this batch
                for text in batch:
                    try:
                        embedding = await self.embed_query(text)
                        all_embeddings.append(embedding)
                    except Exception as e:
                        self.logger.error(f"Failed to embed document: {e}")
                        # Use empty embedding as fallback
                        all_embeddings.append([0.0] * (self.dimensions or 768))
        
        return all_embeddings
    
    async def get_dimensions(self) -> int:
        """
        Determine the dimensionality of the embeddings with retry logic.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        # This will be the output dimensions after any resizing
        if self.dimensions:
            self.logger.debug(f"Using configured dimensions: {self.dimensions}")
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
                    # Use configured dimensions as fallback if available, otherwise default to 768
                    fallback_dimensions = self.config.dimensions if self.config.dimensions else 768
                    self.dimensions = fallback_dimensions
                    self.logger.warning(f"Using fallback dimensions: {fallback_dimensions}")
                    return self.dimensions
                
                data = await response.json()
                embedding = data.get('embedding', [])
                actual_dimensions = len(embedding)
                # Only log if we haven't logged this before
                if not hasattr(self, '_dims_logged'):
                    self.logger.debug(f"Model {self.config.model} returned {actual_dimensions} dimensions")
                    self._dims_logged = True
                self.dimensions = actual_dimensions
                return self.dimensions
        
        try:
            return await self.retry_handler.execute_with_retry(_get_dims)
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Use configured dimensions as fallback if available, otherwise default to 768
            fallback_dimensions = self.config.dimensions if self.config.dimensions else 768
            self.dimensions = fallback_dimensions
            self.logger.warning(f"Using fallback dimensions after exception: {fallback_dimensions}")
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
    
    def _resize_embedding(self, embedding: List[float], target_size: int) -> List[float]:
        """
        Resize an embedding vector to match the target dimensions.
        
        Args:
            embedding: The original embedding vector
            target_size: The target number of dimensions
            
        Returns:
            Resized embedding vector
        """
        current_size = len(embedding)
        
        if current_size == target_size:
            return embedding
        elif current_size > target_size:
            # Truncate: Take first target_size dimensions
            self.logger.debug(f"Truncating embedding from {current_size} to {target_size} dimensions")
            return embedding[:target_size]
        else:
            # Pad: Add zeros to reach target size
            self.logger.debug(f"Padding embedding from {current_size} to {target_size} dimensions")
            padded = embedding.copy()
            padded.extend([0.0] * (target_size - current_size))
            return padded
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        await OllamaBaseService.close(self)