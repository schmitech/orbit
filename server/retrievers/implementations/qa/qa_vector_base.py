# qa_vector_base.py
"""
Base class for QA-specialized vector database retrievers
"""

from abc import abstractmethod
from typing import Dict, Any, List, Optional
import logging

from ...base.abstract_vector_retriever import AbstractVectorRetriever
from ...adapters.registry import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)

class QAVectorRetrieverBase(AbstractVectorRetriever):
    """
    Base class for QA-specialized vector database retrievers.
    
    This class provides common functionality for QA retrievers across
    different vector databases (Chroma, Qdrant, Pinecone, etc.)
    """
    
    def __init__(self, config: Dict[str, Any], **kwargs):
        super().__init__(config, **kwargs)
        
        # Initialize with default values first
        self.adapter_config = None
        self.datasource_config = {}
        
        # Set QA-specific parameters with defaults
        self._initialize_qa_parameters()
        
        # Extract QA adapter config after subclass is initialized
        self._initialize_adapter_config()
    
    def _initialize_adapter_config(self):
        """Initialize adapter config after subclass is fully initialized."""
        try:
            # Extract QA adapter config
            self.adapter_config = self._extract_adapter_config()
            
            # Merge configs
            self.datasource_config = self._merge_configs()
            
            # Re-initialize QA parameters with actual config
            self._initialize_qa_parameters()
        except Exception as e:
            logger.warning(f"Failed to initialize adapter config: {str(e)}")
            # Continue with default values
        
    def _extract_adapter_config(self) -> Optional[Dict[str, Any]]:
        """Extract QA adapter configuration if available."""
        try:
            datasource_name = self.get_datasource_name()
            for adapter in self.config.get('adapters', []):
                if (adapter.get('type') == 'retriever' and 
                    adapter.get('datasource') == datasource_name and 
                    adapter.get('adapter') == 'qa'):
                    return adapter.get('config', {})
        except Exception as e:
            logger.warning(f"Error extracting adapter config: {str(e)}")
        return None
    
    def _merge_configs(self) -> Dict[str, Any]:
        """Merge adapter config with datasource config."""
        try:
            datasource_name = self.get_datasource_name()
            merged_config = self.config.get('datasources', {}).get(datasource_name, {}).copy()
            
            if self.adapter_config:
                merged_config.update(self.adapter_config)
                
            # Override max_results and return_results in main config
            if 'max_results' in merged_config:
                self.config['max_results'] = merged_config['max_results']
                self.max_results = merged_config['max_results']
            if 'return_results' in merged_config:
                self.config['return_results'] = merged_config['return_results']
                self.return_results = merged_config['return_results']
                
            return merged_config
        except Exception as e:
            logger.warning(f"Error merging configs: {str(e)}")
            return {}
    
    def _initialize_qa_parameters(self):
        """Initialize QA-specific parameters from config."""
        # Common QA parameters
        self.confidence_threshold = self.adapter_config.get(
            'confidence_threshold', 0.3
        ) if self.adapter_config else 0.3
        
        # Log initialization
        logger.info(f"{self.__class__.__name__} initialized with:")
        logger.info(f"  confidence_threshold={self.confidence_threshold}")
        logger.info(f"  max_results={self.max_results}")
        logger.info(f"  return_results={self.return_results}")
    
    async def initialize_domain_adapter(self):
        """Initialize domain adapter if not provided."""
        if self.domain_adapter is None:
            try:
                # Create adapter using registry
                self.domain_adapter = ADAPTER_REGISTRY.create(
                    adapter_type='retriever',
                    datasource=self.get_datasource_name(),
                    adapter_name='qa',
                    config=self.config
                )
                logger.info(f"Successfully created QA domain adapter for {self.get_datasource_name()}")
            except Exception as e:
                logger.error(f"Failed to create domain adapter: {str(e)}")
                # Try fallback to generic QA adapter
                try:
                    self.domain_adapter = self._create_fallback_adapter()
                    logger.info("Using generic QA adapter as fallback")
                except Exception as fallback_e:
                    logger.error(f"Failed to create fallback domain adapter: {str(fallback_e)}")
                    self.domain_adapter = None
    
    def _create_fallback_adapter(self):
        """Create a fallback adapter. Can be overridden by subclasses."""
        return ADAPTER_REGISTRY.create(
            adapter_type='retriever',
            datasource='chroma',  # Default fallback
            adapter_name='qa',
            config=self.config
        )
    
    def format_document(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document using domain adapter if available.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'format_document'):
            return self.domain_adapter.format_document(doc, metadata)
        
        # Default QA formatting
        item = {
            "raw_document": doc,
            "metadata": metadata.copy(),
        }
        
        # Set content based on document type
        if "question" in metadata and "answer" in metadata:
            item["content"] = f"Question: {metadata['question']}\nAnswer: {metadata['answer']}"
            item["question"] = metadata["question"]
            item["answer"] = metadata["answer"]
        else:
            item["content"] = doc
            
        return item
    
    def apply_domain_filtering(self, context_items: List[Dict], query: str) -> List[Dict]:
        """Apply domain-specific filtering if domain adapter is available."""
        if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
            return self.domain_adapter.apply_domain_filtering(context_items, query)
        return context_items
    
    @abstractmethod
    def convert_score_to_confidence(self, score: float) -> float:
        """
        Convert database-specific score to confidence value [0, 1].
        Must be implemented by subclasses.
        
        Args:
            score: Database-specific similarity/distance score
            
        Returns:
            Confidence value between 0 and 1
        """
        pass
    
    @abstractmethod
    async def query_vector_database(self, 
                                  query_embedding: List[float], 
                                  collection_name: str,
                                  max_results: int) -> Any:
        """
        Query the specific vector database implementation.
        Must be implemented by subclasses.
        
        Args:
            query_embedding: Query embedding vector
            collection_name: Name of the collection to query
            max_results: Maximum number of results to return
            
        Returns:
            Database-specific results object
        """
        pass
    
    @abstractmethod
    def extract_document_data(self, result: Any) -> tuple[str, Dict[str, Any], float]:
        """
        Extract document, metadata, and score from database-specific result.
        Must be implemented by subclasses.
        
        Args:
            result: Single result from vector database
            
        Returns:
            Tuple of (document_text, metadata, score)
        """
        pass
    
    async def get_relevant_context(self, 
                                 query: str, 
                                 api_key: Optional[str] = None,
                                 collection_name: Optional[str] = None,
                                 **kwargs) -> List[Dict[str, Any]]:
        """
        Common retrieval workflow for QA vector databases.
        
        This method implements the common retrieval pattern and delegates
        database-specific operations to abstract methods.
        """
        try:
            # Check initialization
            if not self.initialized:
                await self.initialize()
            
            if self.verbose:
                logger.info(f"=== Starting QA {self.get_datasource_name()} retrieval ===")
                logger.info(f"Query: '{query}'")
                logger.info(f"API Key: {'Provided' if api_key else 'None'}")
                logger.info(f"Collection: {collection_name or 'From config'}")
            
            # Resolve collection name
            resolved_collection = collection_name or self.collection_name or self.datasource_config.get('collection')
            
            if resolved_collection:
                await self.set_collection(resolved_collection)
            
            # Check embeddings
            if not self.embeddings:
                logger.warning("Embeddings are disabled, no vector search can be performed")
                return []
            
            # Generate query embedding
            if self.verbose:
                logger.info("Generating embedding for query...")
            
            query_embedding = await self.embed_query(query)
            
            if not query_embedding or len(query_embedding) == 0:
                logger.error("Received empty embedding, cannot perform vector search")
                return []
            
            # Query vector database (delegated to subclass)
            if self.verbose:
                logger.info(f"Querying {self.get_datasource_name()} with {len(query_embedding)}-dimensional embedding")
            
            results = await self.query_vector_database(
                query_embedding, 
                resolved_collection, 
                self.max_results
            )
            
            # Process results
            context_items = []
            
            for result in self._iterate_results(results):
                doc_text, metadata, score = self.extract_document_data(result)
                confidence = self.convert_score_to_confidence(score)
                
                if confidence >= self.confidence_threshold:
                    context_item = self.format_document(doc_text, metadata)
                    context_item["confidence"] = confidence
                    
                    # Add metadata
                    if "metadata" not in context_item:
                        context_item["metadata"] = {}
                    
                    context_item["metadata"].update({
                        "source": self.get_datasource_name(),
                        "collection": resolved_collection,
                        "similarity": confidence,
                        "raw_score": score
                    })
                    
                    context_items.append(context_item)
            
            # Sort by confidence
            context_items = sorted(
                context_items, 
                key=lambda x: x.get("confidence", 0), 
                reverse=True
            )
            
            # Apply domain filtering
            context_items = self.apply_domain_filtering(context_items, query)
            
            # Apply final limit
            context_items = context_items[:self.return_results]
            
            if self.verbose:
                logger.info(f"Retrieved {len(context_items)} relevant context items")
                if context_items:
                    logger.info(f"Top confidence: {context_items[0].get('confidence', 0):.4f}")
            
            return context_items
            
        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}")
            return []
    
    @abstractmethod
    def _iterate_results(self, results: Any):
        """
        Convert database-specific results to iterable format.
        Must be implemented by subclasses.
        """
        pass
    
    @abstractmethod
    def get_datasource_name(self) -> str:
        """Return the datasource name for this retriever."""
        pass