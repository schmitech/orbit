"""
HuggingFace embedding service implementation.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from embeddings.base import EmbeddingService


class HuggingFaceEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for HuggingFace models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the HuggingFace embedding service.
        
        Args:
            config: Configuration dictionary for HuggingFace
        """
        super().__init__(config)
        self.model_name = config.get('model', 'sentence-transformers/all-mpnet-base-v2')
        self.device = config.get('device', 'cpu')
        self.normalize = config.get('normalize', True)
        # Get dimensions from config, or set to None to determine dynamically
        self.dimensions = config.get('dimensions')
        self.model = None
        self.tokenizer = None
        self.executor = ThreadPoolExecutor(max_workers=1)  # For running model inference in separate thread
    
    async def initialize(self) -> bool:
        """
        Initialize the HuggingFace embedding service.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Run the model loading in a separate thread to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._load_model
            )
            
            # Determine dimensions
            self.dimensions = await self.get_dimensions()
            self.logger.info(f"Initialized HuggingFace embedding service with model {self.model_name} ({self.dimensions} dimensions)")
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize HuggingFace embedding service: {str(e)}")
            return False
    
    def _load_model(self):
        """
        Load the HuggingFace model and tokenizer.
        This runs in a separate thread.
        """
        try:
            # Import here to avoid dependency issues if not using HuggingFace
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            self.logger.info(f"Loading HuggingFace model {self.model_name}...")
            
            # Load tokenizer and model
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModel.from_pretrained(self.model_name)
            
            # Move model to specified device
            if self.device == 'cuda' and torch.cuda.is_available():
                self.model = self.model.to('cuda')
                self.logger.info("Using CUDA for HuggingFace model")
            else:
                self.model = self.model.to('cpu')
                self.logger.info("Using CPU for HuggingFace model")
            
            # Set model to evaluation mode
            self.model.eval()
            self.logger.info(f"HuggingFace model {self.model_name} loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading HuggingFace model: {str(e)}")
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
        Generate embedding for a single text.
        This runs in a separate thread.
        
        Args:
            text: The text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        import torch
        
        # Tokenize the text
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        
        # Move inputs to the same device as the model
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        
        # Generate embeddings
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # Use mean pooling to get a single vector per text
        attention_mask = inputs["attention_mask"]
        token_embeddings = outputs.last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        embeddings = sum_embeddings / sum_mask
        
        # Normalize if configured
        if self.normalize:
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        
        # Convert to list and return
        return embeddings[0].cpu().tolist()
    
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
            # Run the batch embedding generation in a separate thread
            embeddings = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._generate_batch_embeddings,
                texts
            )
            return embeddings
        except Exception as e:
            self.logger.error(f"Error generating batch embeddings: {str(e)}")
            raise
    
    def _generate_batch_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.
        This runs in a separate thread.
        
        Args:
            texts: The list of texts to embed
            
        Returns:
            A list of embedding vectors
        """
        import torch
        
        # Process in batches of 8 to avoid OOM issues
        batch_size = 8
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            
            # Tokenize the texts
            inputs = self.tokenizer(batch_texts, return_tensors="pt", padding=True, truncation=True, max_length=512)
            
            # Move inputs to the same device as the model
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.model(**inputs)
            
            # Use mean pooling to get a single vector per text
            attention_mask = inputs["attention_mask"]
            token_embeddings = outputs.last_hidden_state
            input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
            sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
            sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
            embeddings = sum_embeddings / sum_mask
            
            # Normalize if configured
            if self.normalize:
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            
            # Convert to list and append
            batch_embeddings = embeddings.cpu().tolist()
            all_embeddings.extend(batch_embeddings)
        
        return all_embeddings
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings produced by this service.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        if self.dimensions:
            return self.dimensions
        
        if not self.initialized:
            # Partially initialized - model is loaded but dimensions not determined
            if self.model:
                # Get dimensions from model config
                try:
                    self.dimensions = self.model.config.hidden_size
                    return self.dimensions
                except AttributeError:
                    # Generate a test embedding to determine dimensions
                    embedding = await self.embed_query("test")
                    self.dimensions = len(embedding)
                    return self.dimensions
            
            # Not initialized at all
            await self.initialize()
            
        # Generate a test embedding to determine dimensions
        embedding = await self.embed_query("test")
        self.dimensions = len(embedding)
        return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the embedding service.
        For local HuggingFace models, we just check if the model is loaded.
        
        Returns:
            True if the model is loaded, False otherwise
        """
        if not self.model or not self.tokenizer:
            try:
                await self.initialize()
                return self.initialized
            except Exception as e:
                self.logger.error(f"Failed to verify HuggingFace model: {str(e)}")
                return False
        return True
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        self.executor.shutdown(wait=True)
        self.model = None
        self.tokenizer = None
        self.initialized = False