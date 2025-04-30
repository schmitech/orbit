"""
Template for creating new retriever implementations
Copy this file and modify it to create a new retriever

Usage:
1. Copy this file to {your_retriever_name}_retriever.py
2. Replace TemplateRetriever with your retriever class name
3. Replace 'template' with your datasource name in _get_datasource_name()
4. Implement the required methods
5. Register your retriever with the factory at the end of the file
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Union
from fastapi import HTTPException

from retrievers.base_retriever import BaseRetriever, RetrieverFactory

# Configure logging
logger = logging.getLogger(__name__)

class TemplateRetriever(BaseRetriever):
    """Template implementation of the BaseRetriever interface"""

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                **kwargs):
        """
        Initialize TemplateRetriever.
        
        Args:
            config: Configuration dictionary
            embeddings: Optional embeddings instance 
            **kwargs: Additional arguments
        """
        # Call the parent constructor first
        super().__init__(config=config, embeddings=embeddings)
        
        # Initialize datasource-specific attributes
        # Example:
        # self.client = None
        # self.connection_string = self.datasource_config.get('connection_string')

    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup"""
        return 'template'  # Change this to your datasource name

    async def initialize(self) -> None:
        """Initialize required services and connections."""
        # Call parent initialize to set up API key service
        await super().initialize()
        
        # Initialize datasource-specific connections/clients
        try:
            # Example:
            # self.client = YourClientLibrary(
            #    connection_string=self.connection_string
            # )
            pass
        except Exception as e:
            logger.error(f"Failed to initialize datasource: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")

    async def close(self) -> None:
        """Close any open services and connections."""
        # Close parent services
        await super().close()
        
        # Close datasource-specific connections
        try:
            # Example:
            # if self.client:
            #     await self.client.close()
            pass
        except Exception as e:
            logger.error(f"Error closing connection: {str(e)}")

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection for retrieval.
        
        Args:
            collection_name: Name of the collection to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        # Set the collection and validate that it exists
        # Example:
        # try:
        #     self.collection = self.client.get_collection(collection_name)
        # except Exception as e:
        #     raise HTTPException(status_code=404, detail=f"Collection not found: {str(e)}")
        
        self.collection = collection_name
        if self.verbose:
            logger.info(f"Switched to collection: {collection_name}")

    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from the datasource.
        
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
            
            # Implement your retrieval logic here
            # Example:
            # 1. Generate embeddings if needed
            # 2. Query your datasource 
            # 3. Process results
            
            results = []
            
            # Example of result structure for QA type retrievers:
            # results.append({
            #     "question": "Example question?",
            #     "answer": "Example answer",
            #     "confidence": 0.95,
            #     "content": "Question: Example question?\nAnswer: Example answer",
            #     "raw_document": "Original raw document content",
            #     "metadata": {
            #         "source": "template",
            #         "collection": self.collection,
            #     }
            # })
            
            # Sort by confidence and limit results
            if results:
                results.sort(key=lambda x: x.get("confidence", 0), reverse=True)
                results = results[:self.return_results]
            
            return results
                
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            logger.error(traceback.format_exc())
            return []

# Uncomment to register your retriever with the factory
# RetrieverFactory.register_retriever('template', TemplateRetriever) 