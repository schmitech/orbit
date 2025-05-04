"""
OpenAI embedding service implementation.
"""

import logging
import aiohttp
import json
import asyncio
import os
from typing import List, Dict, Any, Optional

from embeddings.base import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for OpenAI models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the OpenAI embedding service.
        
        Args:
            config: Configuration dictionary for OpenAI
        """
        super().__init__(config)
        # First try to get the API key from environment variable, then from config
        self.api_key = os.environ.get('OPENAI_API_KEY') or config.get('api_key')
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or provide in config.")
        
        # If the API key contains a variable reference like ${OPENAI_API_KEY}, try to resolve it
        if self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]  # Remove ${ and }
            self.api_key = os.environ.get(env_var)
            if not self.api_key:
                raise ValueError(f"Environment variable {env_var} is not set")
        
        self.model = config.get('model', 'text-embedding-3-small')
        self.dimensions = config.get('dimensions', 1536)  # Default for text-embedding-3-small
        self.base_url = config.get('base_url', 'https://api.openai.com/v1')
        self.batch_size = config.get('batch_size', 10)
        self.session = None
    
    async def initialize(self) -> bool:
        """
        Initialize the OpenAI embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            self.session = aiohttp.ClientSession()
            # Using a direct connection test instead of calling verify_connection to avoid recursion
            url = f"{self.base_url}/embeddings"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "input": "test connection",
                "model": self.model
            }
            
            async with self.session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    self.logger.info(f"Initialized OpenAI embedding service with model {self.model} ({self.dimensions} dimensions)")
                    self.initialized = True
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Error from OpenAI during initialization: {error_text}")
                    return False
        except Exception as e:
            self.logger.error(f"Failed to initialize OpenAI embedding service: {str(e)}")
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
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize OpenAI embedding service")
        
        try:
            url = f"{self.base_url}/embeddings"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "input": text,
                "model": self.model
            }
            
            async with self.session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from OpenAI: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")
                
                data = await response.json()
                return data['data'][0]['embedding']
        except Exception as e:
            self.logger.error(f"Error getting embeddings from OpenAI: {str(e)}")
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.
        Uses batching to avoid rate limits.
        
        Args:
            texts: A list of document texts to embed
            
        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            success = await self.initialize()
            if not success:
                raise ValueError("Failed to initialize OpenAI embedding service")
        
        all_embeddings = []
        
        # Process in batches to avoid rate limits
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i+self.batch_size]
            try:
                batch_embeddings = await self._embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
                
                # Small delay to avoid rate limits
                if i + self.batch_size < len(texts):
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
        url = f"{self.base_url}/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "input": texts,
            "model": self.model
        }
        
        async with self.session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                self.logger.error(f"Error from OpenAI: {error_text}")
                raise ValueError(f"Failed to get batch embeddings: {error_text}")
            
            data = await response.json()
            
            # Sort by index to ensure order matches input order
            embeddings = sorted(data['data'], key=lambda x: x['index'])
            return [item['embedding'] for item in embeddings]
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.
        For OpenAI, we use the configured dimensions or determine from a test embedding.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        if not self.dimensions:
            try:
                embedding = await self.embed_query("test")
                self.dimensions = len(embedding)
            except Exception as e:
                self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
                # Default fallback dimensions based on model
                if "ada" in self.model:
                    self.dimensions = 1024
                elif "3-small" in self.model:
                    self.dimensions = 1536
                elif "3-large" in self.model:
                    self.dimensions = 3072
                else:
                    self.dimensions = 1536  # Default fallback
        
        return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the OpenAI embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            # Directly test the API without calling embed_query to avoid recursion
            url = f"{self.base_url}/embeddings"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "input": "test connection",
                "model": self.model
            }
            
            async with self.session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True
                else:
                    error_text = await response.text()
                    self.logger.error(f"Error verifying connection to OpenAI: {error_text}")
                    return False
        except Exception as e:
            self.logger.error(f"Error verifying connection to OpenAI: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        if self.session:
            await self.session.close()
            self.session = None
            self.initialized = False