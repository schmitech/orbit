"""
Template for creating new vector database retriever implementations
Copy this file and modify it to create a new vector-based retriever

Usage:
1. Copy this file to {your_retriever_name}_retriever.py
2. Replace VectorTemplateRetriever with your retriever class name
3. Replace 'vector_template' with your datasource name in _get_datasource_name()
4. Implement the required methods
5. Register your retriever with the factory at the end of the file
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Union
from fastapi import HTTPException

from ..base.vector_retriever import VectorDBRetriever
from ..base.base_retriever import RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class VectorTemplateRetriever(VectorDBRetriever):
    """Vector DB Template implementation of the VectorDBRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                **kwargs):
        """
        Initialize VectorTemplateRetriever.
        
        Args:
            config: Configuration dictionary
            embeddings: Optional embeddings service or model
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings, **kwargs)
        
        # Initialize vector DB client
        self.client = None
        
        # Example: extract connection parameters
        db_config = self.datasource_config
        self.host = db_config.get('host', 'localhost')
        self.port = int(db_config.get('port', 8000))

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'vector_template'  # Change this to your datasource name

    async def initialize(self) -> None:
        """Initialize required services and connections."""
        # Call parent initialize to set up API key service and embeddings
        await super().initialize()
        
        # Initialize vector database client
        try:
            # Example client initialization:
            # self.client = YourVectorDBClient(
            #     host=self.host,
            #     port=self.port
            # )
            
            # Optional: Verify connection
            # await self.client.ping()
            pass
        except Exception as e:
            logger.error(f"Failed to initialize vector database client: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Vector DB connection error: {str(e)}")

    async def close(self) -> None:
        """Close any open services and connections."""
        # Close parent services (including embedding service)
        await super().close()
        
        # Close vector database client
        try:
            if self.client:
                # await self.client.close()
                pass
        except Exception as e:
            logger.error(f"Error closing vector DB connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        # Set the collection and validate that it exists
        try:
            # Example:
            # self.collection = self.client.get_collection(collection_name)
            self.collection = collection_name
            
            if self.verbose:
                logger.info(f"Switched to collection: {collection_name}")
        except Exception as e:
            error_msg = f"Failed to switch collection: {str(e)}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

    def _format_metadata(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format and create a context item from a document and its metadata.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        # Create the base item 
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
        Retrieve and filter relevant context from the vector database.
        
        Args:
            query: The user's query
            api_key: Optional API key for accessing the collection
            collection_name: Optional explicit collection name
            **kwargs: Additional parameters
            
        Returns:
            A list of context items filtered by relevance
        """
        try:
            # Call the parent implementation which resolves collection
            # and handles common logging/error handling
            await super().get_relevant_context(query, api_key, collection_name, **kwargs)
            
            debug_mode = self.verbose
            
            # Check for embeddings
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            # 1. Generate embedding for query
            query_embedding = await self.embed_query(query)
            
            if not query_embedding or len(query_embedding) == 0:
                logger.error("Received empty embedding, cannot perform vector search")
                return []
            
            # 2. Query vector database
            # Example:
            # results = await self.client.query(
            #     collection_name=self.collection,
            #     query_embeddings=[query_embedding],
            #     n_results=self.max_results
            # )
            
            # 3. Process results
            context_items = []
            
            # Example processing:
            # for doc, metadata, distance in results:
            #     # Calculate similarity score
            #     similarity = 1 - distance  # Adjust based on distance metric
            #     
            #     # Only include results that meet threshold
            #     if similarity >= self.relevance_threshold:
            #         item = self._format_metadata(doc, metadata)
            #         item["confidence"] = similarity
            #         context_items.append(item)
            
            # 4. Sort and limit results
            if context_items:
                context_items.sort(key=lambda x: x.get("confidence", 0), reverse=True)
                context_items = context_items[:self.return_results]
            
            if debug_mode:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                
            return context_items
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Uncomment to register your retriever with the factory
# RetrieverFactory.register_retriever('vector_template', VectorTemplateRetriever) 