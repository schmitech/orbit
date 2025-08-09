"""
File-specialized ChromaDB retriever for uploaded documents
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import HTTPException

from ...implementations.qa.qa_chroma_retriever import QAChromaRetriever
from ...adapters.registry import ADAPTER_REGISTRY

# Configure logging
logger = logging.getLogger(__name__)

class FileChromaRetriever(QAChromaRetriever):
    """
    File-specialized ChromaDB retriever that extends QAChromaRetriever.
    
    This implementation adds file-specific functionality on top of the 
    standard ChromaDB retriever, optimized for uploaded document content.
    """

    def __init__(self, 
                config: Dict[str, Any],
                embeddings: Optional[Any] = None,
                domain_adapter=None,
                collection: Any = None,
                **kwargs):
        """
        Initialize File ChromaDB retriever.
        
        Args:
            config: Configuration dictionary containing Chroma and general settings
            embeddings: Optional EmbeddingService instance
            domain_adapter: Optional domain adapter for file document types
            collection: Optional ChromaDB collection
            **kwargs: Additional arguments
        """
        # Get file-specific adapter config if available (only if enabled)
        adapter_config = None
        for adapter in config.get('adapters', []):
            if (adapter.get('enabled', True) and
                adapter.get('type') == 'retriever' and 
                adapter.get('datasource') == 'chroma' and 
                adapter.get('adapter') == 'file'):
                adapter_config = adapter.get('config', {})
                break
        
        # Create modified config for parent with file-specific overrides
        modified_config = config.copy()
        if adapter_config:
            # Override the datasource config with file-specific settings
            if 'datasources' not in modified_config:
                modified_config['datasources'] = {}
            if 'chroma' not in modified_config['datasources']:
                modified_config['datasources']['chroma'] = {}
            
            # Apply file-specific confidence threshold and distance scaling
            file_confidence_threshold = adapter_config.get('confidence_threshold', 0.2)
            file_distance_scaling = adapter_config.get('distance_scaling_factor', 150.0)
            
            # Override in the config that will be passed to parent
            modified_config['confidence_threshold'] = file_confidence_threshold
            modified_config['distance_scaling_factor'] = file_distance_scaling
            
            logger.info(f"FileChromaRetriever: Using file-specific confidence_threshold={file_confidence_threshold}, distance_scaling_factor={file_distance_scaling}")
        
        # Call parent constructor (QAChromaRetriever) with modified config
        super().__init__(config=modified_config, embeddings=embeddings, domain_adapter=domain_adapter, **kwargs)
        
        # IMPORTANT: Override parent's confidence settings with file-specific values
        # The parent QAChromaRetriever hardcodes looking for 'qa' adapter, so we need to override
        if adapter_config:
            self.confidence_threshold = adapter_config.get('confidence_threshold', 0.2)
            self.distance_scaling_factor = adapter_config.get('distance_scaling_factor', 150.0)
            logger.info(f"FileChromaRetriever: Overrode parent settings - confidence_threshold={self.confidence_threshold}, distance_scaling_factor={self.distance_scaling_factor}")
        
        # File-specific settings from adapter config
        if adapter_config:
            self.include_file_metadata = adapter_config.get('include_file_metadata', True)
            self.boost_file_uploads = adapter_config.get('boost_file_uploads', True)
            self.file_content_weight = adapter_config.get('file_content_weight', 1.5)
            self.metadata_weight = adapter_config.get('metadata_weight', 0.8)
        else:
            self.include_file_metadata = True
            self.boost_file_uploads = True
            self.file_content_weight = 1.5
            self.metadata_weight = 0.8
        
        logger.info(f"FileChromaRetriever initialized with file-specific settings")

    async def initialize(self) -> None:
        """Initialize required services."""
        # Call parent initialize to set up basic services
        await super().initialize()
        
        # Initialize file-specific domain adapter if not provided
        if self.domain_adapter is None:
            try:
                # Create file adapter using registry
                self.domain_adapter = ADAPTER_REGISTRY.create(
                    adapter_type='retriever',
                    datasource='chroma',
                    adapter_name='file',
                    config=self.config
                )
                logger.info("Successfully created File domain adapter")
            except Exception as e:
                logger.warning(f"Could not create file domain adapter: {str(e)}")
                # Fall back to QA adapter if file adapter not available
                try:
                    self.domain_adapter = ADAPTER_REGISTRY.create(
                        adapter_type='retriever',
                        datasource='chroma',
                        adapter_name='qa',
                        config=self.config
                    )
                    logger.info("Falling back to QA domain adapter")
                except Exception as fallback_error:
                    logger.error(f"Failed to create any domain adapter: {str(fallback_error)}")
                    raise
        
        logger.info("FileChromaRetriever initialized successfully")

    def format_document(self, doc: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format document with file-specific enhancements.
        
        Args:
            doc: The document text
            metadata: The document metadata
            
        Returns:
            A formatted context item optimized for file content
        """
        if self.domain_adapter and hasattr(self.domain_adapter, 'format_document'):
            formatted_item = self.domain_adapter.format_document(doc, metadata)
        else:
            # Default file formatting
            formatted_item = {
                "raw_document": doc,
                "metadata": metadata.copy(),
                "content": doc
            }
        
        # Add file-specific enhancements
        if self.include_file_metadata and metadata:
            # Extract file information
            filename = metadata.get('filename', 'Unknown file')
            file_type = metadata.get('mime_type', 'Unknown type')
            source_type = metadata.get('source_type', 'unknown')
            upload_time = metadata.get('upload_timestamp', 'Unknown time')
            
            # Enhance content with file context for uploaded files
            if source_type == 'file_upload':
                # For CSV/structured data, enhance the content presentation
                if 'csv' in file_type.lower() or filename.endswith('.csv'):
                    formatted_item['content_type'] = 'structured_data'
                    formatted_item['display_name'] = f"Data from {filename}"
                    
                    # Parse CSV-like content for better presentation
                    if '|' in doc:  # Our CSV format uses | separators
                        lines = doc.strip().split('\n')
                        if len(lines) > 1:
                            headers = lines[0].split(' | ')
                            formatted_item['structured_content'] = {
                                'headers': headers,
                                'data_preview': lines[1:min(6, len(lines))]  # Show first 5 data rows
                            }
                
                # Add file context to content
                file_context = f"\n[Source: {filename} ({file_type}) uploaded at {upload_time}]"
                formatted_item['content'] = doc + file_context
                
                # Boost confidence for file uploads if enabled
                if self.boost_file_uploads and 'confidence' in formatted_item:
                    formatted_item['confidence'] *= self.file_content_weight
        
        if self.verbose:
            logger.info(f"FileChromaRetriever: Formatted file document - Type: {formatted_item.get('content_type', 'standard')}")
            
        return formatted_item
    
    def apply_domain_filtering(self, context_items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Apply file-specific filtering and ranking.
        
        Args:
            context_items: List of context items to filter/rerank
            query: The original query
            
        Returns:
            Filtered/reranked list of context items optimized for file content
        """
        if self.verbose:
            logger.info(f"FileChromaRetriever.apply_domain_filtering called with {len(context_items)} items")
        
        # First apply domain adapter filtering if available
        if self.domain_adapter and hasattr(self.domain_adapter, 'apply_domain_filtering'):
            context_items = self.domain_adapter.apply_domain_filtering(context_items, query)
        
        # Apply file-specific enhancements
        enhanced_items = []
        
        for item in context_items:
            enhanced_item = item.copy()
            metadata = item.get('metadata', {})
            
            # File-specific confidence boosting
            if metadata.get('source_type') == 'file_upload':
                # Boost confidence for recently uploaded files
                base_confidence = enhanced_item.get('confidence', 0.5)
                
                # Check if query matches file content patterns
                content = item.get('content', '').lower()
                query_lower = query.lower()
                
                # Boost for CSV/structured data matches
                if metadata.get('mime_type', '').lower().startswith('text/csv'):
                    # Look for exact term matches in structured data
                    if any(term in content for term in query_lower.split()):
                        enhanced_item['confidence'] = min(base_confidence * 1.3, 0.95)
                        enhanced_item['match_reason'] = 'Structured data match'
                
                # Boost for filename matches
                filename = metadata.get('filename', '').lower()
                if any(term in filename for term in query_lower.split()):
                    enhanced_item['confidence'] = min(enhanced_item.get('confidence', base_confidence) * 1.2, 0.95)
                    enhanced_item['match_reason'] = enhanced_item.get('match_reason', '') + ' + Filename match'
                
                # Add file-specific display information
                enhanced_item['file_info'] = {
                    'filename': metadata.get('filename', 'Unknown'),
                    'type': metadata.get('mime_type', 'Unknown'),
                    'size': metadata.get('file_size', 0),
                    'upload_time': metadata.get('upload_timestamp', 'Unknown')
                }
            
            enhanced_items.append(enhanced_item)
        
        # Sort by enhanced confidence
        enhanced_items.sort(key=lambda x: x.get('confidence', 0), reverse=True)
        
        if self.verbose:
            logger.info(f"FileChromaRetriever: Enhanced {len(enhanced_items)} items with file-specific scoring")
            for i, item in enumerate(enhanced_items[:3]):  # Log top 3
                logger.info(f"  Item {i+1}: confidence={item.get('confidence', 0):.3f}, "
                          f"reason={item.get('match_reason', 'N/A')}")
        
        return enhanced_items

    async def get_relevant_context(self, 
                           query: str, 
                           api_key: Optional[str] = None, 
                           collection_name: Optional[str] = None,
                           **kwargs) -> List[Dict[str, Any]]:
        """
        Retrieve and filter relevant context from uploaded files.
        
        Args:
            query: The user's query.
            api_key: Optional API key for accessing the collection.
            collection_name: Optional explicit collection name.
            **kwargs: Additional parameters, including file-specific options
            
        Returns:
            A list of context items filtered and enhanced for file content.
        """
        try:
            # Call parent implementation first
            context_items = await super().get_relevant_context(
                query, api_key, collection_name, **kwargs
            )
            
            if self.verbose:
                logger.info(f"FileChromaRetriever: Retrieved {len(context_items)} items from parent")
            
            # Apply file-specific post-processing
            if context_items:
                # Filter for file upload content if specifically requested
                file_only = kwargs.get('file_only', False)
                if file_only:
                    context_items = [
                        item for item in context_items 
                        if item.get('metadata', {}).get('source_type') == 'file_upload'
                    ]
                    if self.verbose:
                        logger.info(f"FileChromaRetriever: Filtered to {len(context_items)} file-only items")
                
                # Apply file-specific domain filtering
                context_items = self.apply_domain_filtering(context_items, query)
            
            if self.verbose:
                logger.info(f"FileChromaRetriever: Final result count: {len(context_items)}")
                
            return context_items
            
        except Exception as e:
            logger.error(f"Error in FileChromaRetriever.get_relevant_context: {str(e)}")
            # Fall back to parent implementation
            return await super().get_relevant_context(query, api_key, collection_name, **kwargs) 