"""
QA-specialized ChromaDB retriever using the base class
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Tuple
from chromadb import HttpClient, PersistentClient
from fastapi import HTTPException

from .qa_vector_base import QAVectorRetrieverBase
from ...base.base_retriever import RetrieverFactory
from ..vector.chroma_retriever import ChromaRetriever

logger = logging.getLogger(__name__)

class QAChromaRetriever(QAVectorRetrieverBase, ChromaRetriever):
    """
    QA-specialized ChromaDB retriever that extends QAVectorRetrieverBase.
    
    Inherits from both QAVectorRetrieverBase for QA functionality and
    ChromaRetriever for Chroma-specific database operations.
    """
    
    def __init__(self, 
                 config: Dict[str, Any],
                 embeddings: Optional[Any] = None,
                 domain_adapter=None,
                 collection: Any = None,
                 **kwargs):
        """Initialize QA ChromaDB retriever."""
        # Call QAVectorRetrieverBase constructor first
        QAVectorRetrieverBase.__init__(self, config, **kwargs)
        
        # Initialize ChromaRetriever with the same config and embeddings
        ChromaRetriever.__init__(self, config, embeddings, domain_adapter, **kwargs)
        
        # Store additional parameters for later use
        self._embeddings = embeddings
        self._domain_adapter = domain_adapter
        self._collection = collection
        
        # Ensure collection name is set from adapter config after both parents are initialized
        if self.adapter_config and 'collection' in self.adapter_config:
            self.collection_name = self.adapter_config['collection']
            logger.debug(f"QAChromaRetriever using collection from adapter config: {self.collection_name}")
        
        # Chroma-specific parameters
        # With cosine similarity, we don't need aggressive scaling
        self.distance_scaling_factor = self.adapter_config.get(
            'distance_scaling_factor', 2.0  # Changed from 200.0 to 2.0 for cosine distance
        ) if self.adapter_config else 2.0
        
        logger.debug(f"QAChromaRetriever initialized with distance_scaling_factor={self.distance_scaling_factor} (cosine mode)")
    
    def get_datasource_name(self) -> str:
        """Return the datasource name."""
        return 'chroma'
    
    async def initialize(self) -> None:
        """Initialize the QA ChromaDB retriever."""
        # Initialize parent services (including embeddings)
        await super().initialize()
        
        # Initialize the ChromaDB client and set collection
        await self.initialize_client()
        
        # Initialize domain adapter
        await self.initialize_domain_adapter()
        
        # Mark as initialized
        self.initialized = True
        
        if self.verbose:
            logger.info(f"QAChromaRetriever initialized successfully")
    
    def convert_score_to_confidence(self, score: float) -> float:
        """
        Convert ChromaDB cosine distance to confidence value.
        
        With cosine similarity metric, ChromaDB returns distances where:
        - 0 = identical vectors (similarity = 1)
        - 1 = orthogonal vectors (similarity = 0) 
        - 2 = opposite vectors (similarity = -1)
        
        Convert to similarity score between 0 and 1 to match Qdrant.
        """
        # Direct conversion from cosine distance to similarity
        if score <= 0:
            return 1.0
        elif score >= 2:
            return 0.0
        else:
            # Linear conversion: distance 0->1, distance 2->0
            return 1.0 - (score / 2.0)
    
    async def query_vector_database(self, 
                                  query_embedding: List[float], 
                                  collection_name: str,
                                  max_results: int) -> Any:
        """Query ChromaDB collection."""
        try:
            # Ensure collection is initialized
            if not self.collection:
                logger.error("ChromaDB collection is not initialized")
                await self.initialize_client()
                
                # Try to set the collection using the configured collection name
                if self.collection_name:
                    await self.set_collection(self.collection_name)
                elif collection_name:
                    await self.set_collection(collection_name)
                    
            if not self.collection:
                logger.error("Failed to initialize ChromaDB collection")
                return None
                
            if hasattr(self.collection, 'query'):
                return self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=max_results,
                    include=["documents", "metadatas", "distances"]
                )
            else:
                logger.error("Collection object does not have a query method")
                return None
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def extract_document_data(self, result: Tuple[str, Dict, float]) -> Tuple[str, Dict[str, Any], float]:
        """Extract document, metadata, and distance from ChromaDB result."""
        doc, metadata, distance = result
        return doc, metadata or {}, distance
    
    def _iterate_results(self, results: Any):
        """Convert ChromaDB results to iterable format."""
        if results and results.get('documents'):
            # ChromaDB returns nested lists, we need to zip them
            for doc, metadata, distance in zip(
                results['documents'][0], 
                results['metadatas'][0], 
                results['distances'][0]
            ):
                yield (doc, metadata, distance)
    
    def _get_result_count(self, results: Any) -> int:
        """Get the count of results from ChromaDB format."""
        if results and results.get('documents') and results['documents']:
            return len(results['documents'][0])
        return 0
    
    async def validate_collection(self) -> bool:
        """Validate that ChromaDB collection is properly set."""
        # Check if collection exists
        if not hasattr(self, 'collection') or self.collection is None:
            try:
                await self.initialize_client()
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB client during validation: {str(e)}")
                return False
        
        return hasattr(self, 'collection') and self.collection is not None
    
    def _add_database_specific_metadata(self, context_item: Dict, result: Any, score: float):
        """Add ChromaDB-specific metadata."""
        context_item["metadata"]["distance"] = score  # Keep original distance for debugging
        context_item["metadata"]["cosine_similarity"] = self.convert_score_to_confidence(score)  # Add converted similarity
            
# Register the QA-specialized retriever with the factory
RetrieverFactory.register_retriever('qa_chroma', QAChromaRetriever)