# qa_pinecone_retriever.py
"""
QA-specialized Pinecone retriever using the base class
"""

import logging
import traceback
from typing import Dict, Any, List, Optional, Tuple

from .qa_vector_base import QAVectorRetrieverBase
from ...base.base_retriever import RetrieverFactory
from adapters.registry import ADAPTER_REGISTRY
from ..vector.pinecone_retriever import PineconeRetriever

logger = logging.getLogger(__name__)

class QAPineconeRetriever(QAVectorRetrieverBase, PineconeRetriever):
    """
    QA-specialized Pinecone retriever that extends QAVectorRetrieverBase.

    Inherits from both QAVectorRetrieverBase for QA functionality and
    PineconeRetriever for Pinecone-specific database operations.
    """

    def __init__(self,
                 config: Dict[str, Any],
                 embeddings: Optional[Any] = None,
                 domain_adapter=None,
                 collection: Any = None,
                 **kwargs):
        """Initialize QA Pinecone retriever."""
        # Call QAVectorRetrieverBase constructor first
        QAVectorRetrieverBase.__init__(self, config, **kwargs)

        # Initialize PineconeRetriever with the same config and embeddings
        PineconeRetriever.__init__(self, config, embeddings, domain_adapter, **kwargs)

        # Store additional parameters for later use
        self._embeddings = embeddings
        self._domain_adapter = domain_adapter
        self._collection = collection

        # Ensure collection name is set from adapter config after both parents are initialized
        if self.adapter_config and 'collection' in self.adapter_config:
            self.collection_name = self.adapter_config['collection']
            logger.debug(f"QAPineconeRetriever using collection from adapter config: {self.collection_name}")

        # Pinecone-specific parameters
        # Re-read confidence_threshold to ensure we have the correct value
        # (in case parent class initialization didn't get it right)
        if self.adapter_config and 'confidence_threshold' in self.adapter_config:
            self.confidence_threshold = self.adapter_config['confidence_threshold']
            logger.info(f"QAPineconeRetriever overriding confidence_threshold to {self.confidence_threshold}")

        self.score_scaling_factor = self.adapter_config.get(
            'score_scaling_factor', 1.0
        ) if self.adapter_config else 1.0

        logger.info(f"QAPineconeRetriever initialized with:")
        logger.info(f"  confidence_threshold={self.confidence_threshold} (used for filtering)")
        logger.info(f"  score_scaling_factor={self.score_scaling_factor}")

    def get_datasource_name(self) -> str:
        """Return the datasource name."""
        return 'pinecone'

    async def initialize(self) -> None:
        """Initialize the QA Pinecone retriever."""
        # Initialize parent services (including embeddings)
        await super().initialize()

        # Initialize the Pinecone client
        await self.initialize_client()

        # Initialize domain adapter
        await self.initialize_domain_adapter()

        # Mark as initialized
        self.initialized = True

        if self.verbose:
            logger.info(f"QAPineconeRetriever initialized successfully")

    def convert_score_to_confidence(self, score: float) -> float:
        """
        Convert Pinecone similarity score to confidence value.

        Pinecone returns similarity scores, typically in range [0, 1] for cosine.
        Apply scaling factor if configured.
        """
        return score * self.score_scaling_factor

    async def query_vector_database(self,
                                  query_embedding: List[float],
                                  collection_name: str,
                                  max_results: int) -> Any:
        """Query Pinecone index."""
        try:
            # Validate collection name (index name in Pinecone)
            if not collection_name:
                logger.error("Collection name (index) is None or empty")
                logger.error(f"Available collection_name sources:")
                logger.error(f"  - Parameter: {collection_name}")
                logger.error(f"  - Self.index_name: {getattr(self, 'index_name', 'Not set')}")
                logger.error(f"  - Adapter config collection: {self.adapter_config.get('collection') if self.adapter_config else 'No adapter config'}")
                return []

            # Ensure client is initialized
            if not self.pinecone_client:
                logger.error("Pinecone client is not initialized")
                await self.initialize_client()

            if not self.pinecone_client:
                logger.error("Failed to initialize Pinecone client")
                return []

            # Set the collection if not already set or if it has changed
            if not self.index or self.index_name != collection_name:
                await self.set_collection(collection_name)

            if not self.index:
                logger.error(f"Failed to set Pinecone index '{collection_name}'")
                return []

            if self.verbose:
                logger.info(f"Querying Pinecone index: {collection_name}")
                logger.info(f"Namespace: {self.namespace}")
                logger.info(f"Max results: {max_results}")

            # Perform the query
            results = self.index.query(
                vector=query_embedding,
                top_k=max_results,
                namespace=self.namespace,
                include_metadata=True,
                include_values=False
            )

            if self.verbose:
                logger.info(f"Pinecone query results type: {type(results)}")
                logger.info(f"Pinecone query results: {results}")
                if hasattr(results, 'matches'):
                    logger.info(f"Number of matches: {len(results.matches)}")
                    logger.info(f"Matches: {results.matches}")
                elif isinstance(results, dict):
                    logger.info(f"Results dict keys: {results.keys()}")
                    logger.info(f"Number of matches in dict: {len(results.get('matches', []))}")

            # Return matches list from results
            # Pinecone v3+ returns an object with .matches attribute
            if hasattr(results, 'matches'):
                return results.matches
            elif isinstance(results, dict):
                return results.get('matches', [])
            else:
                logger.error(f"Unexpected Pinecone results format: {type(results)}")
                return []

        except Exception as e:
            logger.error(f"Error querying Pinecone: {str(e)}")
            if self.verbose:
                logger.error(traceback.format_exc())
            return []

    def extract_document_data(self, result: Any) -> Tuple[str, Dict[str, Any], float]:
        """Extract document, metadata, and score from Pinecone result."""
        # Pinecone returns objects with attributes, not dicts
        # Access metadata and score as attributes
        metadata = getattr(result, 'metadata', {}) or {}

        # Debug logging
        if self.verbose:
            logger.info(f"Pinecone result type: {type(result)}")
            logger.info(f"Pinecone result dir: {dir(result)}")
            logger.info(f"Pinecone result metadata: {metadata}")
            logger.info(f"Pinecone result score: {getattr(result, 'score', 'NO SCORE ATTR')}")

        # Get document content from metadata
        # Common field names: 'content', 'text', 'document', 'answer'
        doc = (metadata.get('content') or
               metadata.get('text') or
               metadata.get('document') or
               metadata.get('answer') or
               '')

        score = float(getattr(result, 'score', 0.0))

        if self.verbose:
            logger.info(f"Extracted doc: {doc[:100] if doc else 'EMPTY'}")
            logger.info(f"Extracted score: {score}")

        return str(doc), metadata, score

    def _iterate_results(self, results: Any):
        """Convert Pinecone results to iterable format."""
        # Pinecone returns a list of matches directly
        return results

    def _get_result_count(self, results: Any) -> int:
        """Get the count of results from Pinecone format."""
        return len(results) if results else 0

    async def validate_collection(self) -> bool:
        """Validate that Pinecone index is properly set."""
        # For Pinecone, we need to ensure both client and index are set
        if not self.pinecone_client:
            try:
                await self.initialize_client()
            except Exception as e:
                logger.error(f"Failed to initialize Pinecone client during validation: {str(e)}")
                return False

        return bool(self.pinecone_client and self.index_name)

    def _add_database_specific_metadata(self, context_item: Dict, result: Any, score: float):
        """Add Pinecone-specific metadata."""
        context_item["metadata"]["score"] = score
        context_item["metadata"]["score_scaling_factor"] = self.score_scaling_factor
        context_item["metadata"]["scaled_similarity"] = self.convert_score_to_confidence(score)

    async def set_collection(self, collection_name: str) -> None:
        """Set the current index name for Pinecone."""
        if not collection_name:
            raise ValueError("Index name (collection) cannot be empty")

        # Ensure client is initialized
        if not self.pinecone_client:
            await self.initialize_client()

        # Use the parent class method to set the index
        await PineconeRetriever.set_collection(self, collection_name)

        # Also update collection_name for base class compatibility
        self.collection_name = collection_name

        if self.verbose:
            logger.info(f"[QAPineconeRetriever] Set index name to: {collection_name}")

    def _create_fallback_adapter(self):
        """Create a fallback adapter specifically for Pinecone."""
        # For Pinecone, fall back to a generic QA adapter
        return ADAPTER_REGISTRY.create(
            adapter_type='retriever',
            datasource='chroma',  # Use chroma as fallback
            adapter_name='qa',
            config=self.config
        )

# Register the QA-specialized retriever with the factory
RetrieverFactory.register_retriever('qa_pinecone', QAPineconeRetriever)
