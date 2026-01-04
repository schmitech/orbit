"""
Composite Intent Retriever base class for routing queries across multiple intent adapters.

This base class provides functionality to:
- Search across template stores of multiple child intent adapters
- Find the best matching template across all sources
- Route query execution to the child adapter that owns the best match
"""

import logging
import traceback
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .base_retriever import BaseRetriever

logger = logging.getLogger(__name__)


@dataclass
class TemplateMatch:
    """Represents a template match from a child adapter."""
    template_id: str
    source_adapter: str
    similarity_score: float
    template_data: Dict[str, Any]
    embedding_text: str = ""


class CompositeIntentRetriever(BaseRetriever):
    """
    Base class for composite intent retrievers that route queries across multiple sources.
    
    This retriever acts as a "smart router" that:
    1. Searches template stores of all configured child intent adapters in parallel
    2. Ranks all matching templates by similarity score
    3. Routes the query to the child adapter that owns the best matching template
    4. Returns results from that single source
    
    Child adapters must be initialized intent retrievers that have:
    - A template_store with search_similar_templates() method
    - A domain_adapter with get_template_by_id() method
    - A get_relevant_context() method for query execution
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, 
                 adapter_manager=None, **kwargs):
        """
        Initialize Composite Intent Retriever.
        
        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter (not used directly, child adapters have their own)
            adapter_manager: Reference to DynamicAdapterManager for resolving child adapters
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)
        
        # Get composite-specific configuration
        self.composite_config = config.get('adapter_config', {})
        
        # Child adapter names to search across
        self.child_adapter_names: List[str] = self.composite_config.get('child_adapters', [])
        if not self.child_adapter_names:
            raise ValueError("child_adapters is required in adapter configuration")
        
        # Composite settings
        self.confidence_threshold = self.composite_config.get('confidence_threshold', 0.4)
        self.max_templates_per_source = self.composite_config.get('max_templates_per_source', 3)
        self.parallel_search = self.composite_config.get('parallel_search', True)
        self.search_timeout = self.composite_config.get('search_timeout', 5.0)
        
        # Reference to adapter manager for resolving child adapters
        self.adapter_manager = adapter_manager
        
        # Cache of resolved child adapters (populated during initialization)
        self._child_adapters: Dict[str, Any] = {}
        
        # Shared embedding client for consistent scoring
        self.embedding_client = None
        
        logger.info(f"CompositeIntentRetriever configured with {len(self.child_adapter_names)} child adapters: {self.child_adapter_names}")
    
    def _get_datasource_name(self) -> str:
        """Return the name of this datasource for config lookup."""
        return "composite"
    
    async def initialize(self) -> None:
        """Initialize the composite retriever and resolve child adapters."""
        try:
            logger.info(f"Initializing CompositeIntentRetriever with {len(self.child_adapter_names)} child adapters")
            
            # Initialize base class
            await super().initialize()
            
            # Initialize embedding client for query embedding
            await self._initialize_embedding_client()
            
            # Resolve and cache child adapters
            await self._resolve_child_adapters()
            
            logger.info(f"CompositeIntentRetriever initialization complete with {len(self._child_adapters)} active child adapters")
            
        except Exception as e:
            logger.error(f"Failed to initialize CompositeIntentRetriever: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _initialize_embedding_client(self) -> None:
        """Initialize embedding client for query embedding."""
        embedding_provider = self.config.get('embedding', {}).get('provider')
        
        from embeddings.base import EmbeddingServiceFactory
        
        try:
            if embedding_provider:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(
                    self.config, embedding_provider)
            else:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config)
            
            if not self.embedding_client.initialized:
                await self.embedding_client.initialize()
                logger.info(f"Initialized {embedding_provider} embedding provider for composite retriever")
            else:
                logger.debug("Embedding service already initialized")
                
        except Exception as e:
            logger.warning(f"Failed to initialize {embedding_provider}: {e}")
            logger.info("Falling back to Ollama embedding provider")
            
            self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, 'ollama')
            if not self.embedding_client.initialized:
                await self.embedding_client.initialize()
    
    async def _resolve_child_adapters(self) -> None:
        """Resolve child adapter references via the adapter manager."""
        if not self.adapter_manager:
            raise ValueError("adapter_manager is required for resolving child adapters")
        
        for adapter_name in self.child_adapter_names:
            try:
                # Get adapter from the manager
                adapter = await self.adapter_manager.get_adapter(adapter_name)
                
                if adapter is None:
                    logger.warning(f"Child adapter '{adapter_name}' not found, skipping")
                    continue
                
                # Verify the adapter has required attributes for template search
                if not hasattr(adapter, 'template_store') or adapter.template_store is None:
                    logger.warning(f"Child adapter '{adapter_name}' has no template_store, skipping")
                    continue
                
                if not hasattr(adapter, 'domain_adapter'):
                    logger.warning(f"Child adapter '{adapter_name}' has no domain_adapter, skipping")
                    continue
                
                self._child_adapters[adapter_name] = adapter
                logger.debug(f"Resolved child adapter: {adapter_name}")
                
            except Exception as e:
                logger.error(f"Failed to resolve child adapter '{adapter_name}': {e}")
                continue
        
        if not self._child_adapters:
            raise ValueError(f"No valid child adapters could be resolved from: {self.child_adapter_names}")
        
        logger.info(f"Resolved {len(self._child_adapters)} child adapters: {list(self._child_adapters.keys())}")
    
    async def _search_single_template_store(
        self, 
        adapter_name: str, 
        adapter: Any, 
        query_embedding: List[float]
    ) -> List[TemplateMatch]:
        """
        Search a single child adapter's template store.
        
        Args:
            adapter_name: Name of the child adapter
            adapter: The child adapter instance
            query_embedding: Pre-computed query embedding
            
        Returns:
            List of TemplateMatch objects from this adapter
        """
        matches = []
        
        try:
            # Search the adapter's template store
            search_results = await adapter.template_store.search_similar_templates(
                query_embedding=query_embedding,
                limit=self.max_templates_per_source,
                threshold=self.confidence_threshold
            )
            
            if not search_results:
                logger.debug(f"No template matches from adapter '{adapter_name}'")
                return matches
            
            # Convert results to TemplateMatch objects
            for result in search_results:
                template_id = result.get('template_id')
                
                # Get full template data from the adapter's domain adapter
                template_data = adapter.domain_adapter.get_template_by_id(template_id)
                
                if template_data:
                    matches.append(TemplateMatch(
                        template_id=template_id,
                        source_adapter=adapter_name,
                        similarity_score=result.get('score', 0.0),
                        template_data=template_data,
                        embedding_text=result.get('description', '')
                    ))
            
            logger.debug(f"Found {len(matches)} template matches from adapter '{adapter_name}'")
            
        except Exception as e:
            logger.error(f"Error searching template store for adapter '{adapter_name}': {e}")
        
        return matches
    
    async def _search_all_template_stores(self, query: str) -> List[TemplateMatch]:
        """
        Search all child adapters' template stores for matching templates.
        
        Args:
            query: The user's query
            
        Returns:
            List of all TemplateMatch objects from all adapters, sorted by similarity
        """
        # Generate query embedding once (shared across all searches)
        query_embedding = await self.embedding_client.embed_query(query)
        
        if not query_embedding:
            logger.error("Failed to generate query embedding")
            return []
        
        logger.debug(f"Generated query embedding with {len(query_embedding)} dimensions")
        
        all_matches: List[TemplateMatch] = []
        
        if self.parallel_search:
            # Search all template stores in parallel
            async def search_with_timeout(adapter_name: str, adapter: Any) -> List[TemplateMatch]:
                try:
                    return await asyncio.wait_for(
                        self._search_single_template_store(adapter_name, adapter, query_embedding),
                        timeout=self.search_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Template search timeout for adapter '{adapter_name}'")
                    return []
            
            tasks = [
                search_with_timeout(name, adapter) 
                for name, adapter in self._child_adapters.items()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error in parallel template search: {result}")
                elif isinstance(result, list):
                    all_matches.extend(result)
        else:
            # Search sequentially
            for adapter_name, adapter in self._child_adapters.items():
                matches = await self._search_single_template_store(
                    adapter_name, adapter, query_embedding
                )
                all_matches.extend(matches)
        
        # Sort all matches by similarity score (highest first)
        all_matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        logger.debug(f"Found {len(all_matches)} total template matches across {len(self._child_adapters)} adapters")
        
        return all_matches
    
    def _select_best_match(self, matches: List[TemplateMatch]) -> Optional[TemplateMatch]:
        """
        Select the best matching template from all matches.
        
        Args:
            matches: List of all template matches, sorted by similarity
            
        Returns:
            The best matching template, or None if no matches meet threshold
        """
        if not matches:
            return None
        
        # The list is already sorted, so the first match is the best
        best_match = matches[0]
        
        if best_match.similarity_score < self.confidence_threshold:
            logger.debug(f"Best match score {best_match.similarity_score:.3f} below threshold {self.confidence_threshold}")
            return None
        
        logger.debug(f"Selected best match: template '{best_match.template_id}' from adapter '{best_match.source_adapter}' (score: {best_match.similarity_score:.3f})")
        
        return best_match
    
    async def get_relevant_context(
        self, 
        query: str, 
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None, 
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Process a query by routing to the best matching child adapter.
        
        This method:
        1. Searches all child adapters' template stores in parallel
        2. Finds the best matching template across all sources
        3. Routes the query to the child adapter that owns that template
        4. Returns results from that single source
        
        Args:
            query: The user's query
            api_key: Optional API key
            collection_name: Optional collection name (not used directly)
            **kwargs: Additional parameters passed to child adapter
            
        Returns:
            List of context items from the best matching child adapter
        """
        try:
            logger.debug(f"CompositeIntentRetriever processing query: {query}")
            
            # Search all template stores
            all_matches = await self._search_all_template_stores(query)
            
            if not all_matches:
                logger.warning("No matching templates found across any child adapters")
                return [{
                    "content": "I couldn't find a matching query pattern across any data sources.",
                    "metadata": {
                        "source": "composite_intent",
                        "error": "no_matching_template",
                        "searched_adapters": list(self._child_adapters.keys())
                    },
                    "confidence": 0.0
                }]
            
            # Select the best match
            best_match = self._select_best_match(all_matches)
            
            if not best_match:
                logger.warning("No template matches met the confidence threshold")
                return [{
                    "content": "I found potential matches but none met the confidence threshold.",
                    "metadata": {
                        "source": "composite_intent",
                        "error": "below_threshold",
                        "searched_adapters": list(self._child_adapters.keys()),
                        "best_score": all_matches[0].similarity_score if all_matches else 0.0
                    },
                    "confidence": 0.0
                }]
            
            # Get the child adapter that owns the best match
            source_adapter = self._child_adapters.get(best_match.source_adapter)
            
            if not source_adapter:
                logger.error(f"Source adapter '{best_match.source_adapter}' not found in cache")
                return [{
                    "content": "An error occurred routing to the data source.",
                    "metadata": {
                        "source": "composite_intent",
                        "error": "adapter_not_found",
                        "attempted_adapter": best_match.source_adapter
                    },
                    "confidence": 0.0
                }]
            
            # Route the query to the child adapter
            logger.debug(f"Routing query to adapter '{best_match.source_adapter}' for template '{best_match.template_id}'")
            
            results = await source_adapter.get_relevant_context(
                query=query,
                api_key=api_key,
                collection_name=collection_name,
                **kwargs
            )
            
            # Enrich results with composite routing metadata
            for result in results:
                if isinstance(result, dict) and 'metadata' in result:
                    result['metadata']['composite_routing'] = {
                        'selected_adapter': best_match.source_adapter,
                        'template_id': best_match.template_id,
                        'similarity_score': best_match.similarity_score,
                        'adapters_searched': list(self._child_adapters.keys()),
                        'total_matches_found': len(all_matches)
                    }
            
            return results
            
        except Exception as e:
            logger.error(f"Error in composite intent retrieval: {e}")
            logger.error(traceback.format_exc())
            return [{
                "content": f"An error occurred while processing your query: {e}",
                "metadata": {"source": "composite_intent", "error": str(e)},
                "confidence": 0.0
            }]
    
    async def set_collection(self, collection_name: str) -> None:
        """
        Set collection is not directly applicable to composite retriever.
        Child adapters manage their own collections.
        """
        logger.debug(f"CompositeIntentRetriever.set_collection called with '{collection_name}' - delegating to child adapters is handled per-query")
    
    async def close(self) -> None:
        """Close the composite retriever and its resources."""
        errors = []
        
        # Close embedding client
        if self.embedding_client:
            try:
                aclose_method = getattr(self.embedding_client, 'aclose', None)
                if aclose_method and callable(aclose_method):
                    await aclose_method()
                else:
                    close_method = getattr(self.embedding_client, 'close', None)
                    if close_method and callable(close_method):
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
            except AttributeError:
                pass
            except Exception as e:
                errors.append(f"embedding: {e}")
                logger.warning(f"Error closing embedding client: {e}")
        
        # Note: We do NOT close child adapters here as they are managed
        # by the adapter manager and may be shared with other consumers
        
        if errors:
            logger.error(f"Errors closing CompositeIntentRetriever: {'; '.join(errors)}")
        
        logger.debug("CompositeIntentRetriever closed")

