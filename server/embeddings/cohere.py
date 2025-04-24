"""
Cohere embedding service implementation.
"""

import logging
import aiohttp
import json
import asyncio
from typing import List, Dict, Any, Optional

from embeddings.base import EmbeddingService


class CohereEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for Cohere models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Cohere embedding service.
        
        Args:
            config: Configuration dictionary for Cohere
        """
        super().__init__(config)
        self.api_key = config.get('api_key')
        if not self.api_key:
            raise ValueError("Cohere API key is required")
        
        self.model = config.get('model', 'embed-english-v3.0')
        self.truncation = config.get('truncation', True)
        self.dimensions = None  # Will be determined during initialization
        self.session = None
        self.base_url = config.get('base_url', 'https://api.cohere.ai/v1')
    
    async def initialize(self) -> bool:
        """
        Initialize the Cohere embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.session = aiohttp.ClientSession()
            
            # Verify connection and determine dimensions
            if await self.verify_connection():
                self.dimensions = await self.get_dimensions()
                self.logger.info(f"Initialized Cohere embedding service with model {self.model} ({self.dimensions} dimensions)")
                self.initialized = True
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Cohere embedding service: {str(e)}")
            return False
    
    async def embed_query(self, text: str) -> List[float]:
        """
        Generate embeddings for a single query text.
        
        Args:
            text: The query text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        if not self.initialized:
            await self.initialize()
        
        try:
            url = f"{self.base_url}/embed"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json"
            }
            
            payload = {
                "texts": [text],
                "model": self.model,
                "truncate": self.truncation,
                "input_type": "search_query"  # Better for single queries
            }
            
            async with self.session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Cohere: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")
                
                data = await response.json()
                return data['embeddings'][0]
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Cohere: {str(e)}")
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
            await self.initialize()
        
        # Cohere has a limit on batch size (96 for embed-v3)
        # Process in smaller batches to avoid issues
        max_batch_size = 32
        all_embeddings = []
        
        for i in range(0, len(texts), max_batch_size):
            batch_texts = texts[i:i+max_batch_size]
            try:
                batch_embeddings = await self._embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
                
                # Small delay to avoid rate limits
                if i + max_batch_size < len(texts):
                    await asyncio.sleep(0.5)
            except Exception as e:
                self.logger.error(f"Error in batch embedding (batch starting at {i}): {str(e)}")
                raise
        
        return all_embeddings
    
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        
        Args:
            texts: A batch of texts to embed
            
        Returns:
            A list of embedding vectors
        """
        url = f"{self.base_url}/embed"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        
        payload = {
            "texts": texts,
            "model": self.model,
            "truncate": self.truncation,
            "input_type": "search_document"  # Better for document collections
        }
        
        async with self.session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                self.logger.error(f"Error from Cohere: {error_text}")
                raise ValueError(f"Failed to get batch embeddings: {error_text}")
            
            data = await response.json()
            return data['embeddings']
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        if self.dimensions:
            return self.dimensions
        
        # Generate a test embedding to determine dimensions
        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback dimensions based on model
            if "english-v3" in self.model:
                return 1024
            elif "multilingual" in self.model:
                return 768
            else:
                return 1024  # Default fallback
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Cohere embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Try to generate a test embedding to verify connection
            await self.embed_query("test connection")
            return True
        except Exception as e:
            self.logger.error(f"Error verifying connection to Cohere: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        if self.session:
            await self.session.close()
            self.session = None
            self.initialized = False