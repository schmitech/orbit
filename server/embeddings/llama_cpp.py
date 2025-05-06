"""
llama.cpp embedding service implementation using GGUF models.
"""

import logging
import asyncio
import os
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Configure logging to suppress Metal-related messages
logging.getLogger('ggml_metal').setLevel(logging.ERROR)

from embeddings.base import EmbeddingService


class LlamaCppEmbeddingService(EmbeddingService):
    """
    Implementation of the embedding service for llama.cpp using local GGUF models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the llama.cpp embedding service.
        
        Args:
            config: Configuration dictionary for llama.cpp
        """
        super().__init__(config)
        
        # Support both model name and model_path for compatibility
        # If model is specified, construct path as "gguf/{model}.gguf"
        self.model = config.get('model', '')
        self.model_path = config.get('model_path', '')
        
        # If both are provided, model_path takes precedence
        if not self.model_path and self.model:
            # Check if model already ends with .gguf
            if self.model.endswith('.gguf'):
                self.model_path = os.path.join('gguf', self.model)
            else:
                self.model_path = os.path.join('gguf', f"{self.model}.gguf")
        elif not self.model_path and not self.model:
            raise ValueError("Either 'model' or 'model_path' must be specified in config for llama.cpp embedding service")
        
        # If specified model_path doesn't exist but is a relative path, try to find it in the gguf directory
        if not os.path.exists(self.model_path) and not os.path.isabs(self.model_path):
            # Try to locate in gguf directory
            gguf_dir = os.path.join(os.getcwd(), 'gguf')
            if os.path.exists(gguf_dir):
                potential_path = os.path.join(gguf_dir, os.path.basename(self.model_path))
                if os.path.exists(potential_path):
                    self.model_path = potential_path
        
        # If the model path contains a variable reference like ${MODEL_PATH}, try to resolve it
        if isinstance(self.model_path, str) and self.model_path.startswith('${') and self.model_path.endswith('}'):
            env_var = self.model_path[2:-1]  # Remove ${ and }
            self.model_path = os.environ.get(env_var)
            if not self.model_path:
                raise ValueError(f"Environment variable {env_var} is not set")
        
        # Set the model name for logging purposes if not already set
        if not self.model:
            self.model = os.path.basename(self.model_path)
        
        # Set other config parameters
        self.n_ctx = config.get('n_ctx', 4096)
        self.n_threads = config.get('n_threads', 4)
        self.n_gpu_layers = config.get('n_gpu_layers', -1)  # -1 means use all layers on GPU
        self.main_gpu = config.get('main_gpu', 0)
        self.tensor_split = config.get('tensor_split', None)
        self.batch_size = config.get('batch_size', 8)
        self.dimensions = config.get('dimensions')  # Get dimensions from config if available
        self.verbose = config.get('verbose', False)
        self.embed_type = config.get('embed_type', 'llama_embedding')  # Type of embedding to use
        
        # Initialize model
        self.llama_model = None
        self.executor = ThreadPoolExecutor(max_workers=1)  # For running model inference in separate thread
    
    async def initialize(self) -> bool:
        """
        Initialize the llama.cpp embedding service by loading the model.
        
        Returns:
            True if initialization was successful, False otherwise
        """
        try:
            # Run the model loading in a separate thread to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._load_model
            )
            
            # Determine dimensions if not provided
            if not self.dimensions:
                self.dimensions = await self.get_dimensions()
                
            self.logger.info(f"Initialized llama.cpp embedding service with model {self.model} ({self.dimensions} dimensions)")
            self.initialized = True
            return True
        except Exception as e:
            self.logger.error(f"Failed to initialize llama.cpp embedding service: {str(e)}")
            return False
    
    def _load_model(self):
        """
        Load the llama.cpp model.
        This runs in a separate thread.
        """
        try:
            # Import here to avoid dependency issues if not using llama.cpp
            from llama_cpp import Llama
            
            # Check if model path exists
            if not os.path.exists(self.model_path):
                error_msg = f"Model file not found at: {self.model_path}"
                self.logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            self.logger.info(f"Loading llama.cpp model from: {self.model_path}")
            
            # Initialize the model with specified parameters
            self.llama_model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=self.n_gpu_layers,
                main_gpu=self.main_gpu,
                tensor_split=self.tensor_split,
                verbose=False,  # Disable verbose output during initialization
                embedding=True  # Enable embedding support
            )
            
            self.logger.info(f"llama.cpp model {self.model} loaded successfully")
        except ImportError:
            error_msg = "llama_cpp package not installed. Please install with: pip install llama-cpp-python==0.3.8"
            self.logger.error(error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            self.logger.error(f"Error loading llama.cpp model: {str(e)}")
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
        Generate embedding for a single text using llama.cpp.
        This runs in a separate thread.
        
        Args:
            text: The text to embed
            
        Returns:
            A list of floats representing the embedding vector
        """
        try:
            # Get embedding from llama.cpp model
            if self.embed_type == 'llama_embedding':
                # Use the embedded embedding function (standard llama2 embedding)
                embedding = self.llama_model.embed(text)
            else:
                # Fall back to using last hidden state (experimental)
                embeddings = self.llama_model.create_embedding(text)
                embedding = embeddings['embedding']
                
            return embedding
        except Exception as e:
            self.logger.error(f"Error in llama.cpp _generate_embedding: {str(e)}")
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
            # Process documents in batches
            all_embeddings = []
            for i in range(0, len(texts), self.batch_size):
                batch_texts = texts[i:i+self.batch_size]
                
                # Run the batch embedding generation in a separate thread
                batch_embeddings = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self._generate_batch_embeddings,
                    batch_texts
                )
                all_embeddings.extend(batch_embeddings)
                
                # Add a small delay to avoid overwhelming the CPU/GPU
                if i + self.batch_size < len(texts):
                    await asyncio.sleep(0.1)
            
            return all_embeddings
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
        batch_embeddings = []
        for text in texts:
            try:
                embedding = self._generate_embedding(text)
                batch_embeddings.append(embedding)
            except Exception as e:
                self.logger.error(f"Error embedding text '{text[:30]}...': {str(e)}")
                raise
        
        return batch_embeddings
    
    async def get_dimensions(self) -> int:
        """
        Get the dimensionality of the embeddings produced by this service.
        
        Returns:
            The number of dimensions in the embedding vectors
        """
        # If dimensions are specified in config, use that value
        if self.dimensions:
            return self.dimensions
        
        # Get a test embedding to determine dimensions
        try:
            # Use a short test string to determine embedding dimensions
            embedding = await self.embed_query("test")
            self.dimensions = len(embedding)
            return self.dimensions
        except Exception as e:
            self.logger.error(f"Failed to determine embedding dimensions: {str(e)}")
            # Default fallback - many GGUF embedding models use 4096 dimensions
            self.dimensions = 4096
            self.logger.warning(f"Using fallback embedding dimensions: {self.dimensions}")
            return self.dimensions
    
    async def verify_connection(self) -> bool:
        """
        Verify the connection to the embedding service.
        For llama.cpp, we check if the model is loaded.
        
        Returns:
            True if the model is loaded, False otherwise
        """
        if not self.llama_model:
            try:
                await self.initialize()
                return self.initialized
            except Exception as e:
                self.logger.error(f"Failed to verify llama.cpp model: {str(e)}")
                return False
        return True
    
    async def close(self) -> None:
        """
        Close the embedding service and release any resources.
        """
        self.executor.shutdown(wait=True)
        self.llama_model = None
        self.initialized = False 