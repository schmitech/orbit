"""
ChromaDB implementation of the BaseRetriever interface
"""

import logging
from typing import Dict, Any, List, Optional, Union
from chromadb import HttpClient
from langchain_ollama import OllamaEmbeddings
from fastapi import HTTPException

from retrievers.base_retriever import BaseRetriever
from services.api_key_service import ApiKeyService
from embeddings.base import EmbeddingService

# Configure logging
logger = logging.getLogger(__name__)

class QAChromaRetriever(BaseRetriever):
    """Chroma implementation of the BaseRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],  # Make config the first required parameter
                embeddings: Optional[Union[OllamaEmbeddings, EmbeddingService]] = None,
                collection: Any = None):
        """
        Initialize ChromaRetriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional OllamaEmbeddings instance or EmbeddingService
            collection: Optional ChromaDB collection
        """
        if not config:
            raise ValueError("Config is required for ChromaRetriever initialization")
            
        self.config = config
        self.embeddings = embeddings
        self.collection = collection
        
        # Extract chroma-specific configuration
        chroma_config = config.get('chroma', {})
        if not chroma_config and 'datasources' in config and 'chroma' in config['datasources']:
            # Handle new config structure
            chroma_config = config.get('datasources', {}).get('chroma', {})
            
        self.confidence_threshold = chroma_config.get('confidence_threshold', 0.7)
        self.relevance_threshold = chroma_config.get('relevance_threshold', 0.5)
        self.verbose = config.get('general', {}).get('verbose', False)
        self.max_results = chroma_config.get('max_results', 10)
        self.return_results = chroma_config.get('return_results', 3)
        
        # Configure ChromaDB and related HTTP client logging based on verbose setting
        if not self.verbose:
            # Only show warnings and errors when not in verbose mode
            for logger_name in ["httpx", "chromadb"]:
                client_logger = logging.getLogger(logger_name)
                client_logger.setLevel(logging.WARNING)
        
        # Initialize dependent services
        self.api_key_service = ApiKeyService(config)
        
        # Initialize ChromaDB client
        self.chroma_client = HttpClient(
            host=chroma_config.get('host', 'localhost'),  # Add default values
            port=int(chroma_config.get('port', 8000))
        )
        
        # Flag to determine if we're using the old or new embedding service
        self.using_new_embedding_service = isinstance(embeddings, EmbeddingService)

    async def initialize(self) -> None:
        """Initialize required services."""
        await self.api_key_service.initialize()
        
        # Check if embedding is enabled
        embedding_enabled = self.config.get('embedding', {}).get('enabled', True)
        
        # Skip initialization if embeddings are disabled
        if not embedding_enabled:
            logger.info("Embedding services are disabled, retriever will operate in limited mode")
            self.embeddings = None
            self.using_new_embedding_service = False
            return
        
        # Initialize embeddings if not provided in constructor
        if self.embeddings is None:
            embedding_provider = self.config.get('embedding', {}).get('provider')
            
            # Use new embedding service architecture if specified
            if embedding_provider and 'embeddings' in self.config:
                from embeddings.base import EmbeddingServiceFactory
                self.embeddings = EmbeddingServiceFactory.create_embedding_service(self.config, embedding_provider)
                await self.embeddings.initialize()
                self.using_new_embedding_service = True
            else:
                # Fall back to legacy Ollama embeddings
                from langchain_ollama import OllamaEmbeddings
                ollama_conf = self.config.get('ollama', {})
                if not ollama_conf and 'inference' in self.config and 'ollama' in self.config['inference']:
                    # Handle new config structure
                    ollama_conf = self.config.get('inference', {}).get('ollama', {})
                    
                self.embeddings = OllamaEmbeddings(
                    model=ollama_conf.get('embed_model', 'bge-m3'),
                    base_url=ollama_conf.get('base_url', 'http://localhost:11434')
                )
                self.using_new_embedding_service = False

    async def close(self) -> None:
        """Close any open services."""
        await self.api_key_service.close()
        
        # Close embedding service if using new architecture
        if self.using_new_embedding_service and self.embeddings:
            await self.embeddings.close()

    async def _resolve_collection(self, api_key: Optional[str] = None, collection_name: Optional[str] = None) -> None:
        """
        Determine and set the appropriate collection.
        
        Priority:
          1. If an API key is provided, validate it and use its collection.
          2. If a collection name is provided directly, use it.
          3. If none is provided and the current collection is None, try the default from config.
        
        Raises:
            HTTPException: If no valid collection can be determined.
        """
        if api_key:
            is_valid, resolved_collection_name = await self.api_key_service.validate_api_key(api_key)
            if not is_valid:
                raise ValueError("Invalid API key")
            if resolved_collection_name:
                await self.set_collection(resolved_collection_name)
                return
        elif collection_name:
            await self.set_collection(collection_name)
            return

        # Fallback to the default collection if none is set
        if not self.collection:
            # Support both old and new config structures
            default_collection = None
            if 'chroma' in self.config:
                default_collection = self.config.get('chroma', {}).get('collection')
            elif 'datasources' in self.config and 'chroma' in self.config['datasources']:
                default_collection = self.config.get('datasources', {}).get('chroma', {}).get('collection')
                
            if default_collection:
                await self.set_collection(default_collection)
            else:
                error_msg = ("No collection available. Ensure a default collection is configured "
                             "or a valid API key is provided.")
                logger.error(error_msg)
                raise HTTPException(status_code=500, detail=error_msg)

    async def set_collection(self, collection_name: str) -> None:
        """Set the current collection for retrieval."""
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
        try:
            self.collection = self.chroma_client.get_collection(name=collection_name)
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            error_msg = f"Failed to switch collection: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def get_direct_answer(self, context: List[Dict[str, Any]]) -> Optional[str]:
        """
        Return a direct answer from the most relevant result if it meets the confidence threshold.
        
        Args:
            context: List of context items from Chroma.
            
        Returns:
            The direct answer if found, otherwise None.
        """
        if not context:
            return None
            
        first_result = context[0]
        
        # Detailed debugging if verbose mode is enabled
        if self.verbose:
            logger.info(f"Direct answer check - confidence: {first_result.get('confidence', 0)}")
            logger.info(f"Direct answer check - has question: {'question' in first_result}")
            logger.info(f"Direct answer check - has answer: {'answer' in first_result}")
            
        if ("question" in first_result and "answer" in first_result and 
            first_result.get("confidence", 0) >= self.confidence_threshold):
            if self.verbose:
                logger.info(f"Found direct answer with confidence {first_result.get('confidence')}")
            
            # Return a formatted answer that includes both question and answer for clarity
            return f"Question: {first_result['question']}\nAnswer: {first_result['answer']}"
        
        return None

    def _format_metadata(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        # Create the base item with confidence
        item = {
            "raw_document": doc,
            "metadata": metadata.copy(),  # Include full metadata
        }
        
        # Set the content field based on document type
        if "question" in metadata and "answer" in metadata:
            # If it's a QA pair, set content to the question and answer together
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
        else:
            # Otherwise, use the document content
            item["content"] = doc
            
        return item

    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from ChromaDB.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance.
        """
        try:
            # Set debug mode if verbose
            debug_mode = self.verbose
            
            if debug_mode:
                logger.info(f"=== Starting retrieval for query: '{query}' ===")
                logger.info(f"API Key: {'Provided' if api_key else 'None'}")
                logger.info(f"Collection name: {collection_name or 'Not specified'}")
            
            # Resolve collection
            await self._resolve_collection(api_key, collection_name)
            
            if debug_mode:
                logger.info(f"Resolved collection: {self.collection.name if self.collection else 'None'}")
            
            # Check if embeddings are available
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            if debug_mode:
                logger.info(f"Using embedding service: {type(self.embeddings).__name__}")
                logger.info(f"New embedding service: {self.using_new_embedding_service}")
            
            # Generate an embedding for the query
            try:
                if debug_mode:
                    logger.info("Generating embedding for query...")
                    
                if self.using_new_embedding_service:
                    # Use the new embedding service API
                    query_embedding = await self.embeddings.embed_query(query)
                    
                    if debug_mode:
                        logger.info(f"Generated embedding using new service: {len(query_embedding)} dimensions")
                        if not query_embedding or len(query_embedding) == 0:
                            logger.error("CRITICAL ERROR: Received empty embedding from service")
                        else:
                            logger.info(f"First 5 values: {query_embedding[:5]}")
                else:
                    # Use the legacy Ollama embeddings
                    query_embedding = self.embeddings.embed_query(query)
                    
                    if debug_mode:
                        logger.info(f"Generated embedding using legacy service: {len(query_embedding)} dimensions")
                        if not query_embedding or len(query_embedding) == 0:
                            logger.error("CRITICAL ERROR: Received empty embedding from legacy service")
                        else:
                            logger.info(f"First 5 values: {query_embedding[:5]}")
                
                if not query_embedding or len(query_embedding) == 0:
                    logger.error("Received empty embedding, cannot perform vector search")
                    return []
                
                # Query ChromaDB for multiple results to enable filtering
                if debug_mode:
                    logger.info(f"Querying ChromaDB with {len(query_embedding)}-dimensional embedding")
                    logger.info(f"Max results: {self.max_results}")
                    
                try:
                    results = self.collection.query(
                        query_embeddings=[query_embedding],
                        n_results=self.max_results,
                        include=["documents", "metadatas", "distances"]
                    )
                    
                    if debug_mode:
                        doc_count = len(results['documents'][0]) if results['documents'] else 0
                        logger.info(f"ChromaDB query returned {doc_count} documents")
                        if doc_count > 0:
                            logger.info(f"First document (truncated): {results['documents'][0][0][:100] if results['documents'][0] else 'None'}")
                            logger.info(f"First distance: {results['distances'][0][0] if results['distances'][0] else 'None'}")
                        else:
                            logger.warning("NO DOCUMENTS RETURNED FROM CHROMADB")
                except Exception as chroma_error:
                    logger.error(f"Error querying ChromaDB: {str(chroma_error)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return []
                
                context_items = []
                
                # DISTANCE HANDLING: Check if distances are unusually large (suggesting L2 or Euclidean)
                is_euclidean = False
                first_distance = results['distances'][0][0] if results['distances'] and results['distances'][0] else 0
                if first_distance > 10:  # Arbitrary threshold for detecting Euclidean distances
                    is_euclidean = True
                    if debug_mode:
                        logger.info(f"Detected Euclidean distances (large values). Will adjust similarity calculation.")
                
                # Get max distance to normalize if using Euclidean
                max_distance = max(results['distances'][0]) if is_euclidean else 1
                
                # Process and filter each result based on the relevance threshold
                for doc, metadata, distance in zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                ):
                    # Adjust similarity calculation based on distance metric
                    if is_euclidean:
                        # For Euclidean: normalize to [0,1] range and invert (smaller is better)
                        # This handles the case where distances are very large
                        normalized_distance = distance / max_distance if max_distance > 0 else 0
                        similarity = 1 - normalized_distance
                    else:
                        # For cosine: just use 1 - distance (closer to 1 is better)
                        similarity = 1 - distance
                    
                    # Always include at least the top result if we got results back
                    is_top_result = (doc == results['documents'][0][0] and 
                                    metadata == results['metadatas'][0][0])
                    
                    if similarity >= self.relevance_threshold or is_top_result:
                        # Create formatted context item
                        item = self._format_metadata(doc, metadata)
                        item["confidence"] = similarity  # Add confidence score
                        
                        context_items.append(item)
                
                # Sort the context items by confidence and select the top N results
                context_items = sorted(context_items, key=lambda x: x.get("confidence", 0), reverse=True)[:self.return_results]
                
                if debug_mode:
                    logger.info(f"Retrieved {len(context_items)} relevant context items")
                    if context_items:
                        logger.info(f"Top confidence score: {context_items[0].get('confidence', 0)}")
                    else:
                        logger.warning("NO CONTEXT ITEMS AFTER FILTERING")
                
                return context_items
                
            except Exception as embedding_error:
                logger.error(f"Error during embeddings or query: {str(embedding_error)}")
                # Print more detailed error information
                import traceback
                logger.error(traceback.format_exc())
                return []
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            # Print more detailed error information
            import traceback
            logger.error(traceback.format_exc())
            return []