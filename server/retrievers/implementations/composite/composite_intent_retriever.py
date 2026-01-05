"""
Composite Intent Retriever Implementation

This retriever routes queries across multiple intent adapters by:
1. Searching all child adapters' template stores in parallel (Stage 1: Embedding)
2. Applying multi-stage scoring if enabled:
   - Stage 2: LLM-based reranking for semantic refinement
   - Stage 3: String similarity (Jaro-Winkler/Levenshtein) for lexical matching
3. Finding the best matching template using combined scores
4. Routing query execution to the child adapter that owns the best match

Multi-stage selection significantly improves accuracy when routing across
many templates with similar vocabulary across different business domains.
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
    3. Optionally applies multi-stage scoring (reranking + string similarity)
    4. Ranks all matching templates by combined score
    5. Routes the query to the child adapter that owns the best matching template
    6. Returns results from that single source

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

    Multi-stage selection is configured in config.yaml under composite_retrieval:
    ```yaml
    composite_retrieval:
      reranking:
        enabled: true
        provider: "anthropic"
        top_candidates: 10
        weight: 0.4
      string_similarity:
        enabled: true
        algorithm: "jaro_winkler"
        weight: 0.2
      scoring:
        embedding_weight: 0.4
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
                    logger.info(f"[Composite] Total matches: {routing.get('total_matches_found', 0)}")

                    # Log multi-stage scoring details if available
                    multistage = routing.get('multistage_scoring', {})
                    if multistage.get('enabled'):
                        logger.info(f"[Composite] Combined Score: {multistage.get('combined_score', 0):.3f}")
                        logger.info(f"[Composite]   - Embedding: {multistage.get('embedding_score', 0):.3f}")
                        if multistage.get('rerank_score') is not None:
                            logger.info(f"[Composite]   - Rerank: {multistage.get('rerank_score', 0):.3f}")
                        if multistage.get('string_similarity_score') is not None:
                            logger.info(f"[Composite]   - String Similarity: {multistage.get('string_similarity_score', 0):.3f}")
                    else:
                        logger.info(f"[Composite] Score: {routing.get('similarity_score', 0):.3f}")

        return results
    
    async def get_routing_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the composite routing configuration.

        Returns:
            Dictionary with routing statistics including:
            - Number of child adapters
            - Template counts per adapter
            - Configuration settings
            - Multi-stage selection configuration
        """
        stats = {
            "child_adapter_count": len(self._child_adapters),
            "child_adapters": {},
            "configuration": {
                "confidence_threshold": self.confidence_threshold,
                "max_templates_per_source": self.max_templates_per_source,
                "parallel_search": self.parallel_search,
                "search_timeout": self.search_timeout
            },
            "multistage_selection": {
                "enabled": self.multistage_enabled,
                "reranking": {
                    "enabled": self.reranking_enabled,
                    "provider": self.reranking_provider if self.reranking_enabled else None,
                    "top_candidates": self.reranking_top_candidates if self.reranking_enabled else None,
                    "weight": self.reranking_weight if self.reranking_enabled else None
                },
                "string_similarity": {
                    "enabled": self.string_similarity_enabled,
                    "algorithm": self.string_similarity_algorithm if self.string_similarity_enabled else None,
                    "weight": self.string_similarity_weight if self.string_similarity_enabled else None,
                    "compare_fields": self.string_similarity_fields if self.string_similarity_enabled else None
                },
                "scoring": {
                    "embedding_weight": self.embedding_weight,
                    "normalize_scores": self.normalize_scores,
                    "tie_breaker": self.tie_breaker
                }
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
        including multi-stage scoring if enabled, but does not execute
        the query. Useful for debugging and testing routing decisions.

        Args:
            query: The query to test routing for

        Returns:
            Dictionary with routing test results including:
            - All matched templates with all score types
            - Which adapter would be selected
            - Multi-stage scoring breakdown
            - Why other templates were not selected
        """
        try:
            # Stage 1: Search all template stores (embedding-based)
            all_matches = await self._search_all_template_stores(query)

            # Stage 2 & 3: Apply multi-stage scoring if enabled
            if self.multistage_enabled and all_matches:
                all_matches = await self._calculate_combined_scores(query, all_matches)

            # Format matches for output
            formatted_matches = []
            for match in all_matches:
                match_info = {
                    "template_id": match.template_id,
                    "source_adapter": match.source_adapter,
                    "embedding_score": match.similarity_score,
                    "description": match.template_data.get('description', ''),
                    "nl_examples": match.template_data.get('nl_examples', [])[:3]  # First 3 examples
                }

                # Add multi-stage scores if available
                if self.multistage_enabled:
                    match_info["combined_score"] = match.combined_score
                    match_info["rerank_score"] = match.rerank_score
                    match_info["string_similarity_score"] = match.string_similarity_score
                    match_info["above_threshold"] = (match.combined_score or 0) >= self.confidence_threshold
                    match_info["scoring_details"] = match.scoring_details
                else:
                    match_info["above_threshold"] = match.similarity_score >= self.confidence_threshold

                formatted_matches.append(match_info)

            # Determine routing decision
            best_match = self._select_best_match(all_matches)

            if best_match:
                if self.multistage_enabled:
                    selection_score = best_match.combined_score
                    reason = "highest_combined_score_above_threshold"
                else:
                    selection_score = best_match.similarity_score
                    reason = "highest_embedding_score_above_threshold"

                routing_decision = {
                    "would_route_to": best_match.source_adapter,
                    "selected_template": best_match.template_id,
                    "selection_score": selection_score,
                    "embedding_score": best_match.similarity_score,
                    "rerank_score": best_match.rerank_score if self.multistage_enabled else None,
                    "string_similarity_score": best_match.string_similarity_score if self.multistage_enabled else None,
                    "reason": reason
                }
            else:
                routing_decision = {
                    "would_route_to": None,
                    "selected_template": None,
                    "selection_score": None,
                    "reason": "no_matches_above_threshold"
                }

            # Calculate threshold-based counts
            if self.multistage_enabled:
                above_threshold = sum(1 for m in all_matches if (m.combined_score or 0) >= self.confidence_threshold)
            else:
                above_threshold = sum(1 for m in all_matches if m.similarity_score >= self.confidence_threshold)

            return {
                "query": query,
                "total_matches": len(all_matches),
                "matches_above_threshold": above_threshold,
                "all_matches": formatted_matches,
                "routing_decision": routing_decision,
                "configuration": {
                    "confidence_threshold": self.confidence_threshold,
                    "adapters_searched": list(self._child_adapters.keys()),
                    "multistage_enabled": self.multistage_enabled,
                    "reranking_enabled": self.reranking_enabled,
                    "string_similarity_enabled": self.string_similarity_enabled,
                    "scoring_weights": {
                        "embedding": self.embedding_weight,
                        "reranking": self.reranking_weight if self.reranking_enabled else None,
                        "string_similarity": self.string_similarity_weight if self.string_similarity_enabled else None
                    }
                }
            }

        except Exception as e:
            logger.error(f"Error in test_routing: {e}")
            logger.debug(traceback.format_exc())
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

