"""
Composite Intent Retriever base class for routing queries across multiple intent adapters.

This base class provides functionality to:
- Search across template stores of multiple child intent adapters
- Find the best matching template across all sources
- Route query execution to the child adapter that owns the best match

Multi-Stage Selection (v2):
- Stage 1: Embedding-based retrieval for initial candidates
- Stage 2: Reranking with LLM-based reranker for semantic refinement
- Stage 3: String similarity scoring for lexical matching
- Combined scoring with configurable weights
"""

import logging
import traceback
import asyncio
import time
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

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

    # Multi-stage scoring fields (populated during enhanced selection)
    rerank_score: Optional[float] = None
    string_similarity_score: Optional[float] = None
    combined_score: Optional[float] = None

    # Scoring metadata
    scoring_details: Dict[str, Any] = field(default_factory=dict)


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

        # Multi-stage selection configuration (from config.yaml composite_retrieval section)
        self._init_multi_stage_config(config)

        # Reranking service (initialized lazily)
        self._reranker = None
        self._rerank_cache: Dict[str, Tuple[float, List[Dict]]] = {}  # query -> (timestamp, results)

        logger.info(f"CompositeIntentRetriever configured with {len(self.child_adapter_names)} child adapters: {self.child_adapter_names}")
        if self.multistage_enabled:
            logger.info(f"Multi-stage selection enabled: reranking={self.reranking_enabled}, string_similarity={self.string_similarity_enabled}")

    def _init_multi_stage_config(self, config: Dict[str, Any]) -> None:
        """Initialize multi-stage selection configuration from composite_retrieval section."""
        composite_retrieval = config.get('composite_retrieval', {})

        # Reranking configuration
        reranking_config = composite_retrieval.get('reranking', {})
        self.reranking_enabled = reranking_config.get('enabled', False)
        self.reranking_provider = reranking_config.get('provider', 'anthropic')
        self.reranking_top_candidates = reranking_config.get('top_candidates', 10)
        self.reranking_weight = reranking_config.get('weight', 0.4)

        # String similarity configuration
        string_sim_config = composite_retrieval.get('string_similarity', {})
        self.string_similarity_enabled = string_sim_config.get('enabled', False)
        self.string_similarity_algorithm = string_sim_config.get('algorithm', 'jaro_winkler')
        self.string_similarity_weight = string_sim_config.get('weight', 0.2)
        self.string_similarity_fields = string_sim_config.get('compare_fields', ['description', 'nl_examples'])
        self.string_similarity_min_threshold = string_sim_config.get('min_threshold', 0.3)
        self.string_similarity_aggregation = string_sim_config.get('aggregation', 'max')

        # Scoring configuration
        scoring_config = composite_retrieval.get('scoring', {})
        self.embedding_weight = scoring_config.get('embedding_weight', 0.4)
        self.normalize_scores = scoring_config.get('normalize_scores', True)
        self.tie_breaker = scoring_config.get('tie_breaker', 'embedding')

        # Performance configuration
        performance_config = composite_retrieval.get('performance', {})
        self.parallel_rerank = performance_config.get('parallel_rerank', True)
        self.cache_rerank_results = performance_config.get('cache_rerank_results', True)
        self.rerank_cache_ttl = performance_config.get('cache_ttl_seconds', 300)

        # Check if multi-stage is enabled (either reranking or string similarity)
        self.multistage_enabled = self.reranking_enabled or self.string_similarity_enabled

        # Validate weights sum to approximately 1.0 if both are enabled
        if self.multistage_enabled:
            total_weight = self.embedding_weight
            if self.reranking_enabled:
                total_weight += self.reranking_weight
            if self.string_similarity_enabled:
                total_weight += self.string_similarity_weight

            if abs(total_weight - 1.0) > 0.01:
                logger.warning(
                    f"Composite retrieval weights sum to {total_weight:.2f}, not 1.0. "
                    f"Scores will be normalized but may not reflect intended weighting."
                )
    
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

    async def _initialize_reranker(self) -> None:
        """Lazily initialize the reranking service."""
        if self._reranker is not None:
            return

        if not self.reranking_enabled:
            return

        try:
            from ai_services.factory import AIServiceFactory
            from ai_services.base import ServiceType

            self._reranker = AIServiceFactory.create_service(
                ServiceType.RERANKING,
                self.reranking_provider,
                self.config
            )

            if hasattr(self._reranker, 'initialize'):
                await self._reranker.initialize()

            logger.info(f"Initialized {self.reranking_provider} reranker for composite retriever")

        except Exception as e:
            logger.warning(f"Failed to initialize reranker ({self.reranking_provider}): {e}")
            logger.warning("Reranking will be disabled for this session")
            self.reranking_enabled = False

    def _calculate_string_similarity_score(
        self,
        query: str,
        template_match: TemplateMatch
    ) -> float:
        """
        Calculate string similarity score between query and template fields.

        Args:
            query: The user's query
            template_match: The template match to score

        Returns:
            Similarity score between 0.0 and 1.0
        """
        try:
            from utils.string_similarity import StringSimilarity

            scores = []
            template_data = template_match.template_data

            for field in self.string_similarity_fields:
                field_value = template_data.get(field)

                if field_value is None:
                    continue

                # Handle list fields (like nl_examples)
                if isinstance(field_value, list):
                    for item in field_value:
                        if isinstance(item, str):
                            score = StringSimilarity.calculate_best_text_similarity(
                                query,
                                item,
                                algorithm=self.string_similarity_algorithm,
                                case_sensitive=False,
                                check_words=True
                            )
                            scores.append(score)

                elif isinstance(field_value, str):
                    score = StringSimilarity.calculate_best_text_similarity(
                        query,
                        field_value,
                        algorithm=self.string_similarity_algorithm,
                        case_sensitive=False,
                        check_words=True
                    )
                    scores.append(score)

            if not scores:
                return 0.0

            # Aggregate scores based on configuration
            if self.string_similarity_aggregation == 'max':
                return max(scores)
            elif self.string_similarity_aggregation == 'avg':
                return sum(scores) / len(scores)
            elif self.string_similarity_aggregation == 'weighted_avg':
                # Give more weight to higher scores
                sorted_scores = sorted(scores, reverse=True)
                weighted_sum = sum(s * (len(sorted_scores) - i) for i, s in enumerate(sorted_scores))
                weight_total = sum(range(1, len(sorted_scores) + 1))
                return weighted_sum / weight_total if weight_total > 0 else 0.0
            else:
                return max(scores)

        except ImportError as e:
            logger.warning(f"String similarity module not available: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"Error calculating string similarity: {e}")
            return 0.0

    async def _rerank_candidates(
        self,
        query: str,
        candidates: List[TemplateMatch]
    ) -> Dict[str, float]:
        """
        Rerank candidates using the configured reranker.

        Args:
            query: The user's query
            candidates: List of template matches to rerank

        Returns:
            Dictionary mapping template_id to rerank score
        """
        if not self.reranking_enabled or not candidates:
            return {}

        # Check cache first
        cache_key = f"{query}:{','.join(sorted(c.template_id for c in candidates))}"
        if self.cache_rerank_results and cache_key in self._rerank_cache:
            cached_time, cached_results = self._rerank_cache[cache_key]
            if time.time() - cached_time < self.rerank_cache_ttl:
                logger.debug(f"Using cached rerank results for query")
                return cached_results

        try:
            # Ensure reranker is initialized
            await self._initialize_reranker()

            if not self._reranker:
                return {}

            # Prepare documents for reranking
            # Combine template description and nl_examples for better context
            documents = []
            template_ids = []

            for match in candidates:
                template_data = match.template_data
                doc_parts = []

                # Add description
                if 'description' in template_data:
                    doc_parts.append(template_data['description'])

                # Add nl_examples
                nl_examples = template_data.get('nl_examples', [])
                if isinstance(nl_examples, list):
                    for ex in nl_examples[:3]:  # Limit to first 3 examples
                        if isinstance(ex, str):
                            doc_parts.append(ex)

                # Add template name/id
                if 'name' in template_data:
                    doc_parts.append(f"Template: {template_data['name']}")

                document = " | ".join(doc_parts) if doc_parts else match.template_id
                documents.append(document)
                template_ids.append(match.template_id)

            # Call reranker
            rerank_results = await self._reranker.rerank(
                query=query,
                documents=documents,
                top_n=len(documents)
            )

            # Build score map
            score_map: Dict[str, float] = {}
            for result in rerank_results:
                idx = result.get('index', 0)
                score = result.get('score', 0.0)
                if 0 <= idx < len(template_ids):
                    score_map[template_ids[idx]] = score

            # Cache results
            if self.cache_rerank_results:
                self._rerank_cache[cache_key] = (time.time(), score_map)

                # Clean old cache entries
                current_time = time.time()
                expired_keys = [
                    k for k, (t, _) in self._rerank_cache.items()
                    if current_time - t > self.rerank_cache_ttl
                ]
                for k in expired_keys:
                    del self._rerank_cache[k]

            logger.debug(f"Reranked {len(candidates)} candidates, top score: {max(score_map.values()) if score_map else 0:.3f}")
            return score_map

        except Exception as e:
            logger.error(f"Error during reranking: {e}")
            logger.debug(traceback.format_exc())
            return {}

    async def _calculate_combined_scores(
        self,
        query: str,
        matches: List[TemplateMatch]
    ) -> List[TemplateMatch]:
        """
        Calculate combined scores for all matches using multi-stage scoring.

        Args:
            query: The user's query
            matches: List of template matches from embedding search

        Returns:
            List of matches with combined_score populated, sorted by combined_score
        """
        if not matches:
            return matches

        if not self.multistage_enabled:
            # If multi-stage is disabled, just use embedding scores
            for match in matches:
                match.combined_score = match.similarity_score
            return matches

        # Limit candidates for reranking
        candidates = matches[:self.reranking_top_candidates]

        # Get rerank scores
        rerank_scores: Dict[str, float] = {}
        if self.reranking_enabled:
            rerank_scores = await self._rerank_candidates(query, candidates)

        # Calculate scores for each match
        for match in matches:
            # Embedding score (already normalized 0-1)
            emb_score = match.similarity_score

            # Rerank score
            rerank_score = rerank_scores.get(match.template_id, 0.0) if self.reranking_enabled else 0.0
            match.rerank_score = rerank_score

            # String similarity score
            string_sim_score = 0.0
            if self.string_similarity_enabled:
                string_sim_score = self._calculate_string_similarity_score(query, match)
                match.string_similarity_score = string_sim_score

            # Calculate combined score
            combined = 0.0

            if self.reranking_enabled and self.string_similarity_enabled:
                # All three scoring methods
                combined = (
                    self.embedding_weight * emb_score +
                    self.reranking_weight * rerank_score +
                    self.string_similarity_weight * string_sim_score
                )
            elif self.reranking_enabled:
                # Embedding + reranking only
                total_weight = self.embedding_weight + self.reranking_weight
                combined = (
                    (self.embedding_weight / total_weight) * emb_score +
                    (self.reranking_weight / total_weight) * rerank_score
                )
            elif self.string_similarity_enabled:
                # Embedding + string similarity only
                total_weight = self.embedding_weight + self.string_similarity_weight
                combined = (
                    (self.embedding_weight / total_weight) * emb_score +
                    (self.string_similarity_weight / total_weight) * string_sim_score
                )

            match.combined_score = combined

            # Store scoring details for debugging
            match.scoring_details = {
                'embedding_score': emb_score,
                'embedding_weight': self.embedding_weight,
                'rerank_score': rerank_score if self.reranking_enabled else None,
                'rerank_weight': self.reranking_weight if self.reranking_enabled else None,
                'string_similarity_score': string_sim_score if self.string_similarity_enabled else None,
                'string_similarity_weight': self.string_similarity_weight if self.string_similarity_enabled else None,
                'combined_score': combined
            }

        # Sort by combined score (descending)
        matches.sort(key=lambda m: m.combined_score or 0.0, reverse=True)

        # Log top matches for debugging
        if matches and logger.isEnabledFor(logging.DEBUG):
            top_3 = matches[:3]
            for i, m in enumerate(top_3):
                rerank_str = f"{m.rerank_score:.3f}" if m.rerank_score is not None else "N/A"
                str_sim_str = f"{m.string_similarity_score:.3f}" if m.string_similarity_score is not None else "N/A"
                logger.debug(
                    f"  #{i+1} {m.template_id} ({m.source_adapter}): "
                    f"combined={m.combined_score:.3f} "
                    f"[emb={m.similarity_score:.3f}, rerank={rerank_str}, str_sim={str_sim_str}]"
                )

        return matches
    
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

        When multi-stage selection is enabled, uses combined_score.
        Otherwise, uses embedding similarity_score.

        Args:
            matches: List of all template matches, sorted by score

        Returns:
            The best matching template, or None if no matches meet threshold
        """
        if not matches:
            return None

        # The list is already sorted (by combined_score if multi-stage, else by similarity_score)
        best_match = matches[0]

        # Determine which score to use for threshold comparison
        if self.multistage_enabled and best_match.combined_score is not None:
            score_to_check = best_match.combined_score
            score_type = "combined"
        else:
            score_to_check = best_match.similarity_score
            score_type = "embedding"

        if score_to_check < self.confidence_threshold:
            logger.debug(
                f"Best match {score_type} score {score_to_check:.3f} below threshold {self.confidence_threshold}"
            )
            return None

        # Log selection details
        if self.multistage_enabled:
            rerank_str = f"{best_match.rerank_score:.3f}" if best_match.rerank_score is not None else "N/A"
            str_sim_str = f"{best_match.string_similarity_score:.3f}" if best_match.string_similarity_score is not None else "N/A"
            logger.debug(
                f"Selected best match: template '{best_match.template_id}' from adapter '{best_match.source_adapter}' "
                f"(combined={best_match.combined_score:.3f}, emb={best_match.similarity_score:.3f}, "
                f"rerank={rerank_str}, str_sim={str_sim_str})"
            )
        else:
            logger.debug(
                f"Selected best match: template '{best_match.template_id}' from adapter '{best_match.source_adapter}' "
                f"(score: {best_match.similarity_score:.3f})"
            )

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
        1. Searches all child adapters' template stores in parallel (Stage 1: Embedding)
        2. Applies multi-stage scoring if enabled (Stage 2: Reranking, Stage 3: String Similarity)
        3. Finds the best matching template using combined scores
        4. Routes the query to the child adapter that owns that template
        5. Returns results from that single source

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

            # Stage 1: Search all template stores (embedding-based)
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

            # Stage 2 & 3: Multi-stage scoring (reranking + string similarity)
            if self.multistage_enabled:
                logger.debug(f"Applying multi-stage scoring to {len(all_matches)} candidates")
                all_matches = await self._calculate_combined_scores(query, all_matches)

            # Select the best match
            best_match = self._select_best_match(all_matches)

            if not best_match:
                logger.warning("No template matches met the confidence threshold")
                # Get the best score from top match for diagnostics
                if all_matches:
                    top_match = all_matches[0]
                    best_score = top_match.combined_score if self.multistage_enabled else top_match.similarity_score
                else:
                    best_score = 0.0

                return [{
                    "content": "I found potential matches but none met the confidence threshold.",
                    "metadata": {
                        "source": "composite_intent",
                        "error": "below_threshold",
                        "searched_adapters": list(self._child_adapters.keys()),
                        "best_score": best_score,
                        "multistage_enabled": self.multistage_enabled
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
                    routing_metadata = {
                        'selected_adapter': best_match.source_adapter,
                        'template_id': best_match.template_id,
                        'similarity_score': best_match.similarity_score,
                        'adapters_searched': list(self._child_adapters.keys()),
                        'total_matches_found': len(all_matches)
                    }

                    # Add multi-stage scoring details if enabled
                    if self.multistage_enabled:
                        routing_metadata['multistage_scoring'] = {
                            'enabled': True,
                            'combined_score': best_match.combined_score,
                            'embedding_score': best_match.similarity_score,
                            'rerank_score': best_match.rerank_score,
                            'string_similarity_score': best_match.string_similarity_score,
                            'scoring_details': best_match.scoring_details
                        }

                    result['metadata']['composite_routing'] = routing_metadata

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

