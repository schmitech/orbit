"""
AWS Bedrock embedding service implementation.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from embeddings.base import EmbeddingService


class BedrockEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for AWS Bedrock models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the AWS Bedrock embedding service.
        
        Args:
            config: Configuration dictionary for AWS Bedrock
        """
        super().__init__(config)
        self.region = config.get('region', 'us-east-1')
        self.model = config.get('model', 'amazon.titan-embed-text-v1')
        self.dimensions = config.get('dimensions', 1536)
        self.client = None
        self.executor = ThreadPoolExecutor(max_workers=1)  # For running boto3 calls in separate thread
    
    async def initialize(self) -> bool:
        """
        Initialize the AWS Bedrock embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Initialize boto3 client in a separate thread
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._init_client
            )
            
            # Verify connection
            if await self.verify_connection():
                self.logger.info(f"Initialized AWS Bedrock embedding service with model {self.model} ({self.dimensions} dimensions)")
                self.initialized = True
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize AWS Bedrock embedding service: {str(e)}")
            return False
    
    def _init_client(self):
        """
        Initialize the boto3 client for Bedrock.
        This runs in a separate thread.
        """
        try:
            import boto3
            self.client = boto3.client('bedrock-runtime', region_name=self.region)
            self.logger.info(f"AWS Bedrock client initialized for region {self.region}")
        except Exception as e:
            self.logger.error(f"Error initializing AWS Bedrock client: {str(e)}")
            raise
    
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
            # Run the embedding generation in a separate thread
            embedding = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._generate_embedding,
                text
            )
            return embedding
        except Exception as e:
            self.logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text using Bedrock.
        This runs in a separate thread.
        
        Args:
            text: The text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        # Format request body based on the model
        if "amazon.titan" in self.model:
            request_body = {
                "inputText": text
            }
        elif "cohere.embed" in self.model:
            request_body = {
                "texts": [text],
                "input_type": "search_document"
            }
        else:
            raise ValueError(f"Unsupported model: {self.model}")
        
        # Invoke the model
        response = self.client.invoke_model(
            modelId=self.model,
            body=json.dumps(request_body)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read())
        
        # Extract embeddings based on the model
        if "amazon.titan" in self.model:
            return response_body['embedding']
        elif "cohere.embed" in self.model:
            return response_body['embeddings'][0]
        else:
            raise ValueError(f"Unsupported model response format: {self.model}")
    
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
        
        # For Bedrock, process in batches of 10 to avoid rate limits
        batch_size = 10
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            
            # For models that support batch inference
            if "cohere.embed" in self.model:
                try:
                    batch_embeddings = await asyncio.get_event_loop().run_in_executor(
                        self.executor,
                        self._generate_batch_embeddings,
                        batch_texts
                    )
                    all_embeddings.extend(batch_embeddings)
                except Exception as e:
                    self.logger.error(f"Error in batch embedding: {str(e)}")
                    raise
            else:
                # Process one by one for models that don't support batching
                for text in batch_texts:
                    embedding = await self.embed_query(text)
                    all_embeddings.append(embedding)
            
            # Small delay to avoid rate limits
            if i + batch_size < len(texts):
                await asyncio.sleep(0.5)
        
        return all_embeddings
    
    def _generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts using Bedrock.
        This runs in a separate thread.
        
        Args:
            texts: The list of texts to embed
            
        Returns:
            A list of embedding vectors
        """
        # Only certain models support batch inference
        if "cohere.embed" in self.model:
            request_body = {
                "texts": texts,
                "input_type": "search_document"
            }
            
            response = self.client.invoke_model(
                modelId=self.model,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            return response_body['embeddings']
        else:
            raise ValueError(f"Batch embedding not supported for model: {self.model}")
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are already known, return them
        if self.dimensions:
            return self.dimensions
        
        # Otherwise, generate a test embedding to determine dimensions
        try:
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback dimensions based on model
            if "titan" in self.model:
                return 1536
            else:
                return 1024
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the Bedrock embedding service.
        
        Returns:
            True if the connection is working, False otherwise
        """
        try:
            # Try to generate a test embedding to verify connection
            await self.embed_query("test connection")
            return True
        except Exception as e:
            self.logger.error(f"Error verifying connection to AWS Bedrock: {str(e)}")
            return False
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        self.executor.shutdown(wait=False)
        self.client = None
        self.initialized = False