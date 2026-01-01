"""
Composite Intent Retriever Implementation

This retriever routes queries across multiple intent adapters by:
1. Searching all child adapters' template stores in parallel
2. Finding the best matching template across all sources
3. Routing query execution to the child adapter that owns the best match
"""

import logging
import traceback
import asyncio
from typing import Dict, Any, List, Optional

from retrievers.base.intent_composite_base import CompositeIntentRetriever as BaseCompositeRetriever, TemplateMatch

logger = logging.getLogger(__name__)


class CompositeIntentRetriever(BaseCompositeRetriever):
    """
    Composite Intent Retriever that routes queries across multiple data sources.
    
    This retriever is configured with a list of child intent adapter names.
    When a query is received, it:
    1. Generates a query embedding using its own embedding client
    2. Searches each child adapter's template store in parallel
    3. Collects and ranks all matching templates by similarity score
    4. Routes the query to the child adapter that owns the best matching template
    5. Returns results from that single source
    
    Configuration example:
    ```yaml
    adapters:
      - name: "composite-multi-source"
        enabled: true
        type: "retriever"
        adapter: "composite"
        implementation: "retrievers.implementations.composite.CompositeIntentRetriever"
        embedding_provider: "openai"  # Shared embedding for consistent scoring
        
        child_adapters:
          - "intent-sql-sqlite-hr"
          - "intent-duckdb-ev-population"
          - "intent-mongodb-mflix"
        
        config:
          confidence_threshold: 0.4
          max_templates_per_source: 3
          parallel_search: true
          search_timeout: 5.0
    ```
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, 
                 adapter_manager=None, **kwargs):
        """
        Initialize the Composite Intent Retriever.
        
        Args:
            config: Configuration dictionary containing:
                - adapter_config.child_adapters: List of child adapter names
                - adapter_config.confidence_threshold: Minimum similarity score
                - adapter_config.max_templates_per_source: Max templates per child
                - adapter_config.parallel_search: Whether to search in parallel
                - adapter_config.search_timeout: Timeout per template search
            domain_adapter: Not used directly (child adapters have their own)
            adapter_manager: Reference to DynamicAdapterManager for resolving children
            **kwargs: Additional arguments
        """
        super().__init__(
            config=config,
            domain_adapter=domain_adapter,
            adapter_manager=adapter_manager,
            **kwargs
        )
        
        # Additional configuration specific to this implementation
        self.verbose = self.composite_config.get('verbose', False)
        
        logger.info(f"CompositeIntentRetriever initialized with child adapters: {self.child_adapter_names}")
    
    async def initialize(self) -> None:
        """
        Initialize the composite retriever.
        
        This method:
        1. Initializes the embedding client for query embedding
        2. Resolves all child adapter references via the adapter manager
        3. Validates that child adapters have required template stores
        """
        await super().initialize()
        
        if self.verbose:
            logger.info(f"Verbose mode enabled for composite retriever")
            for name, adapter in self._child_adapters.items():
                try:
                    stats = await adapter.template_store.get_statistics()
                    logger.info(f"  Child adapter '{name}': {stats.get('total_templates', 0)} templates")
                except Exception as e:
                    logger.warning(f"  Child adapter '{name}': Could not get stats - {e}")
    
    async def get_relevant_context(
        self, 
        query: str, 
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None, 
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Process a query by routing to the best matching child adapter.
        
        This implementation adds verbose logging and additional metadata
        to the base class implementation.
        
        Args:
            query: The user's natural language query
            api_key: Optional API key for child adapter access
            collection_name: Optional collection name (passed to child adapter)
            **kwargs: Additional parameters passed to child adapter
            
        Returns:
            List of context items from the best matching child adapter,
            enriched with composite routing metadata
        """
        if self.verbose:
            logger.info(f"[Composite] Processing query: '{query}'")
            logger.info(f"[Composite] Searching across {len(self._child_adapters)} adapters: {list(self._child_adapters.keys())}")
        
        # Use base class implementation
        results = await super().get_relevant_context(
            query=query,
            api_key=api_key,
            collection_name=collection_name,
            **kwargs
        )
        
        if self.verbose and results:
            for result in results:
                metadata = result.get('metadata', {})
                routing = metadata.get('composite_routing', {})
                if routing:
                    logger.info(f"[Composite] Routed to: {routing.get('selected_adapter')}")
                    logger.info(f"[Composite] Template: {routing.get('template_id')}")
                    logger.info(f"[Composite] Score: {routing.get('similarity_score', 0):.3f}")
                    logger.info(f"[Composite] Total matches: {routing.get('total_matches_found', 0)}")
        
        return results
    
    async def get_routing_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the composite routing configuration.
        
        Returns:
            Dictionary with routing statistics including:
            - Number of child adapters
            - Template counts per adapter
            - Configuration settings
        """
        stats = {
            "child_adapter_count": len(self._child_adapters),
            "child_adapters": {},
            "configuration": {
                "confidence_threshold": self.confidence_threshold,
                "max_templates_per_source": self.max_templates_per_source,
                "parallel_search": self.parallel_search,
                "search_timeout": self.search_timeout
            }
        }
        
        for name, adapter in self._child_adapters.items():
            try:
                if hasattr(adapter, 'template_store') and adapter.template_store:
                    adapter_stats = await adapter.template_store.get_statistics()
                    stats["child_adapters"][name] = {
                        "total_templates": adapter_stats.get('total_templates', 0),
                        "collection_name": adapter_stats.get('collection_name', 'unknown')
                    }
                else:
                    stats["child_adapters"][name] = {"error": "No template store"}
            except Exception as e:
                stats["child_adapters"][name] = {"error": str(e)}
        
        return stats
    
    async def test_routing(self, query: str) -> Dict[str, Any]:
        """
        Test query routing without executing the query.
        
        This method performs template matching across all child adapters
        but does not execute the query. Useful for debugging and testing.
        
        Args:
            query: The query to test routing for
            
        Returns:
            Dictionary with routing test results including:
            - All matched templates with scores
            - Which adapter would be selected
            - Why other templates were not selected
        """
        try:
            # Search all template stores
            all_matches = await self._search_all_template_stores(query)
            
            # Format matches for output
            formatted_matches = []
            for match in all_matches:
                formatted_matches.append({
                    "template_id": match.template_id,
                    "source_adapter": match.source_adapter,
                    "similarity_score": match.similarity_score,
                    "description": match.template_data.get('description', ''),
                    "above_threshold": match.similarity_score >= self.confidence_threshold
                })
            
            # Determine routing decision
            best_match = self._select_best_match(all_matches)
            
            routing_decision = {
                "would_route_to": best_match.source_adapter if best_match else None,
                "selected_template": best_match.template_id if best_match else None,
                "selection_score": best_match.similarity_score if best_match else None,
                "reason": "highest_score_above_threshold" if best_match else "no_matches_above_threshold"
            }
            
            return {
                "query": query,
                "total_matches": len(all_matches),
                "matches_above_threshold": sum(1 for m in all_matches if m.similarity_score >= self.confidence_threshold),
                "all_matches": formatted_matches,
                "routing_decision": routing_decision,
                "configuration": {
                    "confidence_threshold": self.confidence_threshold,
                    "adapters_searched": list(self._child_adapters.keys())
                }
            }
            
        except Exception as e:
            logger.error(f"Error in test_routing: {e}")
            return {
                "query": query,
                "error": str(e)
            }
    
    async def reload_child_adapters(self) -> Dict[str, Any]:
        """
        Reload child adapter references from the adapter manager.
        
        This is useful when child adapters have been reloaded/reconfigured
        and the composite retriever needs to pick up the changes.
        
        Returns:
            Summary of reload results
        """
        previous_adapters = set(self._child_adapters.keys())
        
        # Clear current cache
        self._child_adapters.clear()
        
        # Re-resolve adapters
        await self._resolve_child_adapters()
        
        current_adapters = set(self._child_adapters.keys())
        
        return {
            "previous_adapters": list(previous_adapters),
            "current_adapters": list(current_adapters),
            "added": list(current_adapters - previous_adapters),
            "removed": list(previous_adapters - current_adapters),
            "total_active": len(self._child_adapters)
        }

