"""
Cohere embedding service implementation using the official Cohere Python library.
"""

import logging
import asyncio
import os
from typing import List, Dict, Any, Optional

from embeddings.base import EmbeddingService


class CohereEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for Cohere models using the official Cohere Python library.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Cohere embedding service.
        
        Args:
            config: Configuration dictionary for Cohere
        """
        super().__init__(config)
        
        # First try to get the API key from environment variable, then from config
        self.api_key = os.environ.get('COHERE_API_KEY') or config.get('api_key')
        if not self.api_key:
            raise ValueError("Cohere API key is required. Set COHERE_API_KEY environment variable or provide in config.")
        
        # If the API key contains a variable reference like ${COHERE_API_KEY}, try to resolve it
        if isinstance(self.api_key, str) and self.api_key.startswith('${') and self.api_key.endswith('}'):
            env_var = self.api_key[2:-1]  # Remove ${ and }
            self.api_key = os.environ.get(env_var)
            if not self.api_key:
                raise ValueError(f"Environment variable {env_var} is not set")
        
        self.model = config.get('model', 'embed-english-v3.0')
        self.input_type = config.get('input_type', 'search_document')
        self.embedding_types = ["float"]  # Default embedding type
        self.dimensions = config.get('dimensions')  # Get dimensions from config if available
        self.batch_size = config.get('batch_size', 32)  # Batch size for processing
        
        # Using 'NONE' instead of boolean for truncate
        truncate_setting = config.get('truncate', 'NONE')
        self.truncate = truncate_setting
        
        self.client = None
    
    async def initialize(self) -> bool:
        """
        Initialize the Cohere embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Import cohere here to avoid dependency issues if not using Cohere
            import cohere
            
            # Initialize the Cohere client
            self.client = cohere.ClientV2(api_key=self.api_key)
            
            self.logger.info(f"Initialized Cohere client with model {self.model}")
            
            # Verify connection and determine dimensions if not provided
            if await self.verify_connection():
                if not self.dimensions:
                    self.dimensions = await self.get_dimensions()
                
                self.logger.info(f"Cohere embedding service initialized successfully ({self.dimensions} dimensions)")
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
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere embedding service")
        
        try:
            # Run in a separate thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            
            # Prepare the embedding parameters
            params = {
                "texts": [text],
                "model": self.model,
                "input_type": "search_query",  # Better for single queries
                "embedding_types": self.embedding_types
            }
            
            # Only include truncate if it's set to something
            if self.truncate != "AUTO":
                params["truncate"] = self.truncate
            
            response = await loop.run_in_executor(
                None,
                lambda: self.client.embed(**params)
            )
            
            # Extract the embedding from the response - properly handle the response structure
            # The response format differs between API versions
            embedding = None
            
            # Try different ways to access the embedding data based on the response structure
            if hasattr(response, 'embeddings') and hasattr(response.embeddings, 'float_'):
                # For newer API versions that return embeddings by type with float_ (underscore)
                embedding = response.embeddings.float_[0]
            elif hasattr(response, 'embeddings') and hasattr(response.embeddings, 'float'):
                # For versions that use float without underscore
                embedding = response.embeddings.float[0]
            elif hasattr(response, 'embeddings') and isinstance(response.embeddings, list):
                # For older API versions that return a list directly
                embedding = response.embeddings[0]
            elif hasattr(response, 'float_'):
                # For clients that might directly return the float_ embeddings
                embedding = response.float_[0]
            elif hasattr(response, 'float'):
                # For clients that might directly return the float embeddings
                embedding = response.float[0]
            else:
                # If none of the expected structures is found, try to get the raw response data
                self.logger.warning(f"Unexpected response structure: {dir(response)}")
                # Last resort - try to access as dictionary
                try:
                    if isinstance(response, dict) and 'embeddings' in response:
                        if isinstance(response['embeddings'], list):
                            embedding = response['embeddings'][0]
                        elif isinstance(response['embeddings'], dict):
                            if 'float_' in response['embeddings']:
                                embedding = response['embeddings']['float_'][0]
                            elif 'float' in response['embeddings']:
                                embedding = response['embeddings']['float'][0]
                except Exception as dict_e:
                    self.logger.error(f"Failed to extract embedding from response: {str(dict_e)}")
            
            if embedding is None:
                raise ValueError(f"Could not extract embedding from response: {response}")
                
            return embedding
        except Exception as e:
            self.logger.error(f"Error getting embeddings from Cohere: {str(e)}")
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple documents.
        Uses batching to avoid API limits.
        
        Args:
            texts: A list of document texts to embed
            
        Returns:
            A list of embedding vectors (each a list of floats)
        """
        if not self.initialized:
            if not await self.initialize():
                raise ValueError("Failed to initialize Cohere embedding service")
        
        all_embeddings = []
        
        # Process in batches to avoid API limits
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
        try:
            # Run in a separate thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            
            # Prepare the embedding parameters
            params = {
                "texts": texts,
                "model": self.model,
                "input_type": self.input_type,
                "embedding_types": self.embedding_types
            }
            
            # Only include truncate if it's set to something
            if self.truncate != "AUTO":
                params["truncate"] = self.truncate
            
            response = await loop.run_in_executor(
                None,
                lambda: self.client.embed(**params)
            )
            
            # Extract embeddings from the response - properly handle the response structure
            embeddings = []
            
            # Try different ways to access the embedding data based on the response structure
            if hasattr(response, 'embeddings') and hasattr(response.embeddings, 'float_'):
                # For newer API versions that return embeddings by type with float_ (underscore)
                embeddings = response.embeddings.float_
            elif hasattr(response, 'embeddings') and hasattr(response.embeddings, 'float'):
                # For versions that use float without underscore
                embeddings = response.embeddings.float
            elif hasattr(response, 'embeddings') and isinstance(response.embeddings, list):
                # For older API versions that return a list directly
                embeddings = response.embeddings
            elif hasattr(response, 'float_'):
                # For clients that might directly return the float_ embeddings
                embeddings = response.float_
            elif hasattr(response, 'float'):
                # For clients that might directly return the float embeddings
                embeddings = response.float
            else:
                # If none of the expected structures is found, try to get the raw response data
                self.logger.warning(f"Unexpected response structure: {dir(response)}")
                # Last resort - try to access as dictionary
                try:
                    if isinstance(response, dict) and 'embeddings' in response:
                        if isinstance(response['embeddings'], list):
                            embeddings = response['embeddings']
                        elif isinstance(response['embeddings'], dict):
                            if 'float_' in response['embeddings']:
                                embeddings = response['embeddings']['float_']
                            elif 'float' in response['embeddings']:
                                embeddings = response['embeddings']['float']
                except Exception as dict_e:
                    self.logger.error(f"Failed to extract embeddings from response: {str(dict_e)}")
            
            if not embeddings:
                raise ValueError(f"Could not extract embeddings from response: {response}")
                
            return embeddings
        except Exception as e:
            self.logger.error(f"Error in batch embedding: {str(e)}")
            raise
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.
        For Cohere, we use the configured dimensions or determine from a test embedding.
        
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
                self.dimensions = 1024
            elif "multilingual" in self.model:
                self.dimensions = 768
            elif "v4" in self.model:
                self.dimensions = 1024
            else:
                self.dimensions = 1024  # Default fallback
            
            return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Cohere embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Try to generate a test embedding to verify connection
            if not self.client:
                import cohere
                self.client = cohere.ClientV2(api_key=self.api_key)
            
            # Run in a separate thread to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            
            # Prepare the embedding parameters
            params = {
                "texts": ["test connection"],
                "model": self.model,
                "input_type": "search_query",
                "embedding_types": self.embedding_types
            }
            
            # Only include truncate if it's set to something
            if self.truncate != "AUTO":
                params["truncate"] = self.truncate
            
            # Get test response
            response = await loop.run_in_executor(
                None,
                lambda: self.client.embed(**params)
            )
            
            # Log the response structure for debugging
            self.logger.info(f"Cohere API response structure: {dir(response)}")
            if hasattr(response, 'embeddings'):
                self.logger.info(f"  embeddings attribute: {dir(response.embeddings)}")
            
            self.logger.info("Successfully connected to Cohere API")
            return True
        except Exception as e:
            self.logger.error(f"Error verifying connection to Cohere: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        # The Cohere client doesn't need explicit cleanup
        self.client = None
        self.initialized = False