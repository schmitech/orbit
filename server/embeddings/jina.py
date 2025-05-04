"""
Jina AI embedding service implementation.
"""

import logging
import aiohttp
import json
import os
from typing import List, Dict, Any, Optional
import asyncio

from embeddings.base import EmbeddingService


class JinaEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for Jina AI's embedding models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Jina embedding service.
        
        Args:
            config: Configuration dictionary for Jina
        """
        super().__init__(config)
        
        # First try to get the API key from environment variable, then from config
        self.api_key = os.environ.get('JINA_API_KEY') or config.get('api_key')
        if not self.api_key:
            raise ValueError("Jina API key is required. Set JINA_API_KEY environment variable or provide in config.")
        
        # If the API key contains a variable reference like ${JINA_API_KEY}, try to resolve it
        if self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]  # Remove ${ and }
            self.api_key = os.environ.get(env_var)
            if not self.api_key:
                raise ValueError(f"Environment variable {env_var} is not set")
        
        # Get other configuration parameters
        self.base_url = config.get('base_url', 'https://api.jina.ai/v1')
        self.model = config.get('model', 'jina-embeddings-v3')
        self.task = config.get('task', 'text-matching')
        self.dimensions = config.get('dimensions', 1024)  # Default dimensions
        self.batch_size = config.get('batch_size', 10)  # Default batch size for processing
        
        # Initialize session
        self.session = None
        self._session_lock = asyncio.Lock()
    
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
        Initialize the Jina embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Create session if not already created
            await self._get_session()
            
            # Verify connection by making a test request
            if await self.verify_connection():
                # If dimensions is specified in config, use that value
                if self.dimensions:
                    self.logger.info(f"Initialized Jina embedding service with model {self.model} ({self.dimensions} dimensions)")
                else:
                    # Otherwise determine dimensions from API
                    self.dimensions = await self.get_dimensions()
                    self.logger.info(f"Dynamically determined dimensions: {self.dimensions}")
                
                self.initialized = True
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Jina embedding service: {str(e)}")
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
                raise ValueError("Failed to initialize Jina embedding service")
        
        try:
            session = await self._get_session()
            url = f"{self.base_url}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": self.model,
                "task": self.task,
                "dimensions": self.dimensions,
                "input": [text]
            }
            
            self.logger.debug(f"Sending embedding request to Jina API for text: {text[:50]}...")
            
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error from Jina API: {error_text}")
                    raise ValueError(f"Failed to get embeddings: {error_text}")
                
                data = await response.json()
                
                # Extract the embedding from the response
                if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                    embedding = data["data"][0]["embedding"]
                    return embedding
                else:
                    self.logger.error(f"Unexpected response structure from Jina API: {data}")
                    raise ValueError("Failed to extract embedding from response")
                
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Jina API: {str(e)}")
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
                raise ValueError("Failed to initialize Jina embedding service")
        
        all_embeddings = []
        
        # Process in batches to avoid API limits
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i+self.batch_size]
            try:
                batch_embeddings = await self._embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
                
                # Add a small delay between batches to avoid rate limits
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
        session = await self._get_session()
        url = f"{self.base_url}/embeddings"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "task": self.task,
            "dimensions": self.dimensions,
            "input": texts
        }
        
        async with session.post(url, headers=headers, json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                self.logger.error(f"Error from Jina API: {error_text}")
                raise ValueError(f"Failed to get batch embeddings: {error_text}")
            
            data = await response.json()
            
            # Extract embeddings from the response
            if "data" in data and len(data["data"]) > 0:
                # Ensure the order matches the input order
                embeddings = []
                for item in data["data"]:
                    if "embedding" in item:
                        embeddings.append(item["embedding"])
                    else:
                        self.logger.error(f"Missing embedding in response item: {item}")
                        raise ValueError("Failed to extract embedding from response")
                
                # Verify we got the expected number of embeddings
                if len(embeddings) != len(texts):
                    self.logger.warning(f"Expected {len(texts)} embeddings but got {len(embeddings)}")
                
                return embeddings
            else:
                self.logger.error(f"Unexpected response structure from Jina API: {data}")
                raise ValueError("Failed to extract embeddings from response")
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.
        For Jina, we use the configured dimensions or generate a test embedding.
        
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
            # Default fallback dimensions for jina-embeddings-v3
            self.dimensions = 1024
            return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Jina embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            session = await self._get_session()
            url = f"{self.base_url}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            # Simple payload for testing
            payload = {
                "model": self.model,
                "task": self.task,
                "dimensions": self.dimensions,
                "input": ["test connection"]
            }
            
            self.logger.info(f"Verifying connection to Jina API with model {self.model}")
            
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Error connecting to Jina API: {error_text}")
                    return False
                
                data = await response.json()
                
                # Verify the response structure
                if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                    embedding = data["data"][0]["embedding"]
                    self.logger.info(f"Successfully verified connection to Jina API. Got embedding with {len(embedding)} dimensions.")
                    return True
                else:
                    self.logger.error(f"Unexpected response structure from Jina API: {data}")
                    return False
        except Exception as e:
            self.logger.error(f"Error verifying connection to Jina API: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        if self.session:
            await self.session.close()
            self.session = None
            self.initialized = False
