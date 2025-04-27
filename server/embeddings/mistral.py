"""
Mistral embedding service implementation.
"""

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional

# Import the official Mistral client
from mistralai import Mistral

from embeddings.base import EmbeddingService


class MistralEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for Mistral models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Mistral embedding service.
        
        Args:
            config: Configuration dictionary for Mistral
        """
        super().__init__(config)
        self.api_key = config.get('api_key')
        if not self.api_key:
            self.api_key = os.environ.get("MISTRAL_API_KEY")
            if not self.api_key:
                raise ValueError("Mistral API key is required")
        
        self.model = config.get('model', 'mistral-embed')
        self.dimensions = config.get('dimensions', 1024)  # Default for mistral-embed
        self.client = None
    
    async def initialize(self) -> bool:
        """
        Initialize the Mistral embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Initialize Mistral client
            self.client = Mistral(api_key=self.api_key)
            
            if await self.verify_connection():
                self.logger.info(f"Initialized Mistral embedding service with model {self.model} ({self.dimensions} dimensions)")
                self.initialized = True
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Mistral embedding service: {str(e)}")
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
            response = await self.client.embeddings.create_async(
                model=self.model,
                input=[text],
            )
            return response.data[0].embedding
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Mistral: {str(e)}")
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
        
        try:
            response = await self.client.embeddings.create_async(
                model=self.model,
                input=texts,
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            self.logger.error(f"Error getting batch embeddings from Mistral: {str(e)}")
            raise
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings produced by this service.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Mistral embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Test with a simple text to verify connection
            response = await self.client.embeddings.create_async(
                model=self.model,
                input=["Test connection"],
            )
            
            # Verify we got a valid embedding
            if response and response.data and len(response.data) > 0:
                embedding = response.data[0].embedding
                if embedding and len(embedding) > 0:
                    # Update dimensions based on actual embedding
                    self.dimensions = len(embedding)
                    self.logger.info(f"Successfully verified connection to Mistral API with model {self.model}")
                    return True
            
            self.logger.error("Received invalid embedding from Mistral")
            return False
        except Exception as e:
            self.logger.error(f"Error verifying connection to Mistral API: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        self.initialized = False
        self.client = None