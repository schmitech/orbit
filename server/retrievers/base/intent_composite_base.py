"""
Composite Intent Retriever base class for routing queries across multiple intent adapters.

This base class provides functionality to:
- Search across template stores of multiple child intent adapters
- Find the best matching template across all sources
- Route query execution to the child adapter that owns the best match
- Cross-adapter templates for multi-domain queries (e.g., cross-city comparisons)

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
import os
import yaml
from pathlib import Path
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
        self._embedding_reinit_lock = asyncio.Lock()

        # Multi-stage selection configuration (from config.yaml composite_retrieval section)
        self._init_multi_stage_config(config)

        # Reranking service (initialized lazily)
        self._reranker = None
        self._rerank_cache: Dict[str, Tuple[float, List[Dict]]] = {}  # query -> (timestamp, results)
        self._max_rerank_cache_size = 1000

        # Cross-adapter template configuration
        cross_adapter_config = self.composite_config.get('cross_adapter_templates', {})
        self.cross_adapter_enabled = cross_adapter_config.get('enabled', False)
        self.cross_adapter_template_paths: List[str] = cross_adapter_config.get('template_library_path', [])
        if isinstance(self.cross_adapter_template_paths, str):
            self.cross_adapter_template_paths = [self.cross_adapter_template_paths]
        self.cross_adapter_collection_name = cross_adapter_config.get(
            'template_collection_name', 'composite_cross_adapter_templates'
        )
        self.cross_adapter_store_name = cross_adapter_config.get('store_name', 'chroma')

        # Cross-adapter execution configuration
        cross_exec_config = self.composite_config.get('cross_adapter_execution', {})
        self.cross_adapter_timeout = cross_exec_config.get('timeout_per_adapter', 10.0)
        self.cross_adapter_partial_results = cross_exec_config.get('partial_results', True)
        self.cross_adapter_default_merge_strategy = cross_exec_config.get('default_merge_strategy', 'side_by_side')

        # Cross-adapter template store and cache (populated during initialization)
        self._cross_adapter_template_store = None
        self._cross_adapter_templates: Dict[str, Dict[str, Any]] = {}

        logger.info(f"CompositeIntentRetriever configured with {len(self.child_adapter_names)} child adapters: {self.child_adapter_names}")
        if self.cross_adapter_enabled:
            logger.info(f"Cross-adapter templates enabled with {len(self.cross_adapter_template_paths)} template path(s)")
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

        # Validate weights sum to approximately 1.0 for enabled stages
        if self.multistage_enabled:
            total_weight = self.embedding_weight
            if self.reranking_enabled:
                total_weight += self.reranking_weight
            if self.string_similarity_enabled:
                total_weight += self.string_similarity_weight

            if abs(total_weight - 1.0) > 0.01:
                # Weights don't sum to 1.0 for the active subset — this is expected
                # when the defaults are tuned for all-three-enabled mode. The scoring
                # code normalizes automatically, preserving the intended ratio.
                enabled = ['embedding']
                if self.reranking_enabled:
                    enabled.append('reranking')
                if self.string_similarity_enabled:
                    enabled.append('string_similarity')
                logger.info(
                    f"Composite retrieval active weights ({', '.join(enabled)}) sum to "
                    f"{total_weight:.2f}. Scores will be normalized to 1.0 "
                    f"(ratio preserved)."
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

            # Initialize cross-adapter templates if enabled
            if self.cross_adapter_enabled:
                await self._initialize_cross_adapter_templates()

            logger.info(f"CompositeIntentRetriever initialization complete with {len(self._child_adapters)} active child adapters")
            
        except Exception as e:
            logger.error(f"Failed to initialize CompositeIntentRetriever: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _initialize_embedding_client(self) -> None:
        """Initialize embedding client for query embedding."""
        embedding_provider = self.config.get('embedding', {}).get('provider')
        self._embedding_provider = embedding_provider  # Store for re-initialization

        from embeddings.base import EmbeddingServiceFactory

        try:
            if embedding_provider:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(
                    self.config, embedding_provider)
            else:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config)
            self._owns_embedding_client = False

            if not self.embedding_client.initialized:
                await self.embedding_client.initialize()
                logger.info(f"Initialized {embedding_provider} embedding provider for composite retriever")
            else:
                logger.debug("Embedding service already initialized")

        except Exception as e:
            logger.warning(f"Failed to initialize {embedding_provider}: {e}")
            logger.info("Falling back to Ollama embedding provider")

            self._embedding_provider = 'ollama'
            self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, 'ollama')
            self._owns_embedding_client = False
            if not self.embedding_client.initialized:
                await self.embedding_client.initialize()

    async def _ensure_embedding_client_valid(self) -> bool:
        """
        Ensure the embedding client is valid and ready for use.

        If the underlying client was closed (e.g., by cache cleanup of another adapter),
        re-initialize the embedding service. Uses an asyncio lock to prevent concurrent
        re-initialization races.

        Returns:
            True if the client is valid, False if re-initialization failed
        """
        # Quick check without lock
        if self.embedding_client is not None and not self._is_embedding_client_closed():
            return True

        async with self._embedding_reinit_lock:
            # Re-check under lock
            if self.embedding_client is not None and not self._is_embedding_client_closed():
                return True

            if self.embedding_client is None:
                logger.warning("Composite retriever embedding client is None, reinitializing...")
                await self._initialize_embedding_client()
                return self.embedding_client is not None

            # Client was closed, re-initialize
            provider = getattr(self, '_embedding_provider', None) or 'unknown'
            logger.warning(
                f"Composite retriever's {provider} embedding client was closed "
                f"(likely by cache cleanup of another adapter). Reinitializing..."
            )

            from embeddings.base import EmbeddingServiceFactory

            try:
                provider_to_use = self._embedding_provider or self.config.get('embedding', {}).get('provider', 'ollama')
                factory_instances = EmbeddingServiceFactory.get_cached_instances()
                keys_to_remove = [k for k in factory_instances.keys() if k.startswith(f"{provider_to_use}:")]
                if keys_to_remove:
                    with EmbeddingServiceFactory._get_lock():
                        for key in keys_to_remove:
                            if key in EmbeddingServiceFactory._instances:
                                del EmbeddingServiceFactory._instances[key]

                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(
                    self.config, provider_to_use
                )

                if not self.embedding_client.initialized:
                    await self.embedding_client.initialize()

                logger.info(f"Successfully reinitialized {provider_to_use} embedding client for composite retriever")
                return True

            except Exception as e:
                logger.error(f"Failed to reinitialize embedding client: {e}")
                return False

    def _is_embedding_client_closed(self) -> bool:
        """Check if the embedding client's underlying connection was closed."""
        if self.embedding_client is None:
            return True
        if hasattr(self.embedding_client, '_genai_client'):
            return False

        # Services that manage their own session (e.g. Voyage, OpenRouter)
        # use self.session instead of self.client — check that first
        if hasattr(self.embedding_client, 'session') and self.embedding_client.session is not None:
            return False

        # Services with a session_manager (e.g. Jina) handle their own lifecycle
        if hasattr(self.embedding_client, 'session_manager'):
            return False

        # For SDK-based services, client=None means the connection was closed
        return (
            hasattr(self.embedding_client, 'client') and
            self.embedding_client.client is None
        )
    
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

    async def _initialize_cross_adapter_templates(self) -> None:
        """
        Initialize cross-adapter templates: load from YAML, embed nl_examples,
        and store in a dedicated TemplateEmbeddingStore.
        """
        try:
            # Load templates from YAML files
            all_templates = []
            for path in self.cross_adapter_template_paths:
                loaded = self._load_cross_adapter_yaml(path)
                if loaded:
                    all_templates.extend(loaded)

            if not all_templates:
                logger.warning("No cross-adapter templates loaded, disabling cross-adapter search")
                self.cross_adapter_enabled = False
                return

            # Validate target_adapters reference valid child adapters
            valid_templates = []
            for template in all_templates:
                target_adapters = template.get('target_adapters', [])
                valid_targets = []
                for target in target_adapters:
                    adapter_name = target.get('adapter', '')
                    if adapter_name in self._child_adapters or adapter_name in self.child_adapter_names:
                        valid_targets.append(target)
                    else:
                        logger.warning(
                            f"Cross-adapter template '{template.get('id')}' references unknown adapter '{adapter_name}', skipping target"
                        )
                if len(valid_targets) >= 2:
                    template['target_adapters'] = valid_targets
                    valid_templates.append(template)
                else:
                    logger.warning(
                        f"Cross-adapter template '{template.get('id')}' has fewer than 2 valid target adapters, skipping"
                    )

            if not valid_templates:
                logger.warning("No valid cross-adapter templates after validation")
                self.cross_adapter_enabled = False
                return

            # Create template embedding store
            from vector_stores.services.template_embedding_store import TemplateEmbeddingStore

            self._cross_adapter_template_store = TemplateEmbeddingStore(
                store_name=f"cross_adapter_{self.cross_adapter_store_name}",
                store_type=self.cross_adapter_store_name,
                collection_name=self.cross_adapter_collection_name,
                config={}
            )
            await self._cross_adapter_template_store.initialize()

            # Embed all nl_examples (per-example embedding, same pattern as child adapters)
            vector_entries = []  # (vector_id, template_data, embedding_text)
            for template in valid_templates:
                template_id = template.get('id', '')
                description = template.get('description', '')
                nl_examples = template.get('nl_examples', [])

                for i, example in enumerate(nl_examples):
                    if example and example.strip():
                        embedding_text = f"{example} {description}"
                        vector_id = f"{template_id}::ex{i}"
                        vector_entries.append((vector_id, template, embedding_text))

                # Store template in cache for later lookup
                self._cross_adapter_templates[template_id] = template

            if not vector_entries:
                logger.warning("No cross-adapter template examples to embed")
                self.cross_adapter_enabled = False
                return

            # Batch embed all texts
            embedding_texts = [entry[2] for entry in vector_entries]
            embeddings = await self.embedding_client.embed_documents(embedding_texts)

            if not embeddings or len(embeddings) != len(vector_entries):
                logger.error("Failed to embed cross-adapter templates")
                self.cross_adapter_enabled = False
                return

            # Batch add to template store
            batch = []
            for (vector_id, template, _), embedding in zip(vector_entries, embeddings):
                template_data = {
                    'template_id': vector_id,
                    'description': template.get('description', ''),
                    'category': 'cross_adapter',
                    'nl_examples': template.get('nl_examples', [])
                }
                batch.append((vector_id, template_data, embedding))

            await self._cross_adapter_template_store.batch_add_templates(batch)

            logger.info(
                f"Initialized {len(self._cross_adapter_templates)} cross-adapter templates "
                f"with {len(vector_entries)} example embeddings"
            )

        except Exception as e:
            logger.error(f"Failed to initialize cross-adapter templates: {e}")
            logger.error(traceback.format_exc())
            self.cross_adapter_enabled = False

    async def reload_templates(self) -> Dict[str, Any]:
        """
        Reload cross-adapter templates from YAML files and rebuild embeddings.

        This mirrors intent adapter template hot reload behavior for composite
        retrievers that own their own cross-adapter template collection.
        """
        try:
            if not self.cross_adapter_enabled:
                return {
                    "templates_loaded": 0,
                    "cross_adapter_templates_loaded": 0,
                    "cross_adapter_examples_loaded": 0,
                    "collection_name": self.cross_adapter_collection_name,
                    "template_library_path": self.cross_adapter_template_paths,
                    "cross_adapter_enabled": False,
                }

            logger.info(
                "Reloading cross-adapter templates for collection '%s'...",
                self.cross_adapter_collection_name,
            )

            if self._cross_adapter_template_store:
                await self._cross_adapter_template_store.clear_all_templates()
                logger.info(
                    "Cleared existing cross-adapter templates from collection '%s'",
                    self.cross_adapter_collection_name,
                )

            self._cross_adapter_templates = {}
            await self._initialize_cross_adapter_templates()

            stats = {}
            if self._cross_adapter_template_store:
                stats = await self._cross_adapter_template_store.get_statistics()

            templates_loaded = len(self._cross_adapter_templates)
            examples_loaded = stats.get("total_templates", 0)

            logger.info(
                "Cross-adapter template reload complete: %s templates with %s example embeddings in '%s'",
                templates_loaded,
                examples_loaded,
                self.cross_adapter_collection_name,
            )

            return {
                "templates_loaded": templates_loaded,
                "cross_adapter_templates_loaded": templates_loaded,
                "cross_adapter_examples_loaded": examples_loaded,
                "collection_name": self.cross_adapter_collection_name,
                "template_library_path": self.cross_adapter_template_paths,
                "cross_adapter_enabled": self.cross_adapter_enabled,
            }

        except Exception as e:
            logger.error(f"Error reloading cross-adapter templates: {e}")
            logger.error(traceback.format_exc())
            raise

    def _load_cross_adapter_yaml(self, path: str) -> Optional[List[Dict[str, Any]]]:
        """Load cross-adapter templates from a YAML file."""
        try:
            if not os.path.isabs(path):
                project_root = Path(__file__).parent.parent.parent.parent
                full_path = project_root / path
            else:
                full_path = Path(path)

            if not full_path.exists():
                logger.warning(f"Cross-adapter template file not found: {full_path}")
                return None

            with open(full_path, 'r') as f:
                data = yaml.safe_load(f)

            templates = data.get('templates', [])
            if not isinstance(templates, list):
                logger.warning(f"Expected 'templates' list in {full_path}")
                return None

            # Mark all templates as cross-adapter
            for t in templates:
                t['cross_adapter'] = True

            logger.info(f"Loaded {len(templates)} cross-adapter templates from {full_path}")
            return templates

        except Exception as e:
            logger.error(f"Error loading cross-adapter templates from {path}: {e}")
            return None

    async def _search_cross_adapter_templates(
        self,
        query_embedding: List[float]
    ) -> List[TemplateMatch]:
        """
        Search cross-adapter template store for matching templates.

        Args:
            query_embedding: Pre-computed query embedding

        Returns:
            List of TemplateMatch objects from cross-adapter templates
        """
        if not self.cross_adapter_enabled or not self._cross_adapter_template_store:
            return []

        matches = []
        try:
            search_results = await self._cross_adapter_template_store.search_similar_templates(
                query_embedding=query_embedding,
                limit=self.max_templates_per_source * 3,
                threshold=self.confidence_threshold
            )

            if not search_results:
                return matches

            # Deduplicate per-example vectors (same pattern as child adapter search)
            seen: Dict[str, Dict[str, Any]] = {}
            for result in search_results:
                raw_tid = result.get('template_id', '')
                base_tid = raw_tid.rsplit('::', 1)[0] if '::' in raw_tid else raw_tid
                score = result.get('score', 0)
                if base_tid not in seen or score > seen[base_tid].get('score', 0):
                    result_copy = dict(result)
                    result_copy['template_id'] = base_tid
                    seen[base_tid] = result_copy

            deduped = sorted(seen.values(), key=lambda r: r.get('score', 0), reverse=True)
            deduped = deduped[:self.max_templates_per_source]

            for result in deduped:
                template_id = result.get('template_id')
                template_data = self._cross_adapter_templates.get(template_id)

                if template_data:
                    matches.append(TemplateMatch(
                        template_id=template_id,
                        source_adapter="__cross_adapter__",
                        similarity_score=result.get('score', 0.0),
                        template_data=template_data,
                        embedding_text=result.get('description', '')
                    ))

            logger.debug(f"Found {len(matches)} cross-adapter template matches")

        except Exception as e:
            logger.error(f"Error searching cross-adapter templates: {e}")

        return matches

    async def _execute_cross_adapter_query(
        self,
        query: str,
        best_match: TemplateMatch,
        api_key: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Execute a cross-adapter query by routing to multiple child adapters in parallel.

        Args:
            query: The user's query
            best_match: The matched cross-adapter template
            api_key: Optional API key
            **kwargs: Additional parameters

        Returns:
            Merged results from all target adapters
        """
        template_data = best_match.template_data
        target_adapters = template_data.get('target_adapters', [])
        merge_strategy = template_data.get('merge_strategy', self.cross_adapter_default_merge_strategy)
        partial_results = template_data.get('partial_results', self.cross_adapter_partial_results)
        timeout = template_data.get('timeout_per_adapter', self.cross_adapter_timeout)

        logger.info(
            f"Executing cross-adapter query across {len(target_adapters)} adapters "
            f"(strategy={merge_strategy}, template={best_match.template_id})"
        )

        # Execute queries in parallel across target adapters
        async def query_adapter(target: Dict[str, Any]) -> Tuple[str, str, Optional[List[Dict[str, Any]]], Optional[str]]:
            """Returns (adapter_name, label, results, error)"""
            adapter_name = target['adapter']
            label = target.get('label', adapter_name)
            adapter = self._child_adapters.get(adapter_name)

            if not adapter:
                return (adapter_name, label, None, f"Adapter '{adapter_name}' not found")

            try:
                results = await asyncio.wait_for(
                    adapter.get_relevant_context(
                        query=query,
                        api_key=api_key,
                        **kwargs
                    ),
                    timeout=timeout
                )
                return (adapter_name, label, results, None)
            except asyncio.TimeoutError:
                return (adapter_name, label, None, f"Timeout after {timeout}s")
            except Exception as e:
                return (adapter_name, label, None, str(e))

        tasks = [query_adapter(target) for target in target_adapters]
        adapter_results = await asyncio.gather(*tasks)

        # Collect successful and failed results
        successful_results: List[Tuple[str, str, List[Dict[str, Any]]]] = []
        failed_adapters: List[Dict[str, str]] = []

        for adapter_name, label, results, error in adapter_results:
            if error:
                logger.warning(f"Cross-adapter query failed for '{adapter_name}': {error}")
                failed_adapters.append({'adapter': adapter_name, 'label': label, 'error': error})
            elif results:
                successful_results.append((adapter_name, label, results))

        if not successful_results:
            return [{
                "content": "Cross-adapter query failed: no adapters returned results.",
                "metadata": {
                    "source": "composite_intent",
                    "error": "cross_adapter_all_failed",
                    "failed_adapters": failed_adapters,
                    "template_id": best_match.template_id
                },
                "confidence": 0.0
            }]

        if not partial_results and failed_adapters:
            return [{
                "content": "Cross-adapter query incomplete: some adapters failed and partial_results is disabled.",
                "metadata": {
                    "source": "composite_intent",
                    "error": "cross_adapter_partial_failure",
                    "failed_adapters": failed_adapters,
                    "successful_adapters": [r[0] for r in successful_results],
                    "template_id": best_match.template_id
                },
                "confidence": 0.0
            }]

        # Merge results
        merged = self._merge_cross_adapter_results(
            successful_results, merge_strategy, best_match, failed_adapters
        )

        return merged

    def _merge_cross_adapter_results(
        self,
        successful_results: List[Tuple[str, str, List[Dict[str, Any]]]],
        merge_strategy: str,
        best_match: TemplateMatch,
        failed_adapters: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Merge results from multiple adapters according to the merge strategy.

        Args:
            successful_results: List of (adapter_name, label, results) tuples
            merge_strategy: How to merge ('side_by_side' or 'labeled_concat')
            best_match: The matched cross-adapter template
            failed_adapters: List of adapters that failed

        Returns:
            Merged result list
        """
        routing_metadata = {
            'cross_adapter': True,
            'template_id': best_match.template_id,
            'merge_strategy': merge_strategy,
            'similarity_score': best_match.similarity_score,
            'target_adapters': [r[0] for r in successful_results],
            'successful_adapters': [r[0] for r in successful_results],
            'failed_adapters': failed_adapters,
            'total_sources': len(successful_results)
        }

        if best_match.combined_score is not None:
            routing_metadata['combined_score'] = best_match.combined_score

        if merge_strategy == 'labeled_concat':
            return self._merge_labeled_concat(successful_results, routing_metadata)
        else:
            # Default: side_by_side
            return self._merge_side_by_side(successful_results, routing_metadata)

    def _merge_side_by_side(
        self,
        successful_results: List[Tuple[str, str, List[Dict[str, Any]]]],
        routing_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Side-by-side merge: each adapter's results are kept as separate items,
        annotated with source label. The LLM presentation layer handles comparison formatting.
        """
        merged = []
        for adapter_name, label, results in successful_results:
            for result in results:
                enriched = dict(result)
                metadata = enriched.get('metadata', {})
                metadata['composite_routing'] = routing_metadata.copy()
                metadata['cross_adapter_source'] = {
                    'adapter': adapter_name,
                    'label': label
                }
                enriched['metadata'] = metadata
                merged.append(enriched)

        return merged

    def _merge_labeled_concat(
        self,
        successful_results: List[Tuple[str, str, List[Dict[str, Any]]]],
        routing_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Labeled concatenation: all result content is concatenated with source labels prepended.
        Each adapter's content is clearly marked with its label for comparison.
        """
        content_parts = []
        all_metadata = {}

        for adapter_name, label, results in successful_results:
            for result in results:
                content = result.get('content', result.get('raw_document', ''))
                if content:
                    content_parts.append(f"--- {label} ---\n{content}")

                # Collect metadata from each source
                result_meta = result.get('metadata', {})
                all_metadata[adapter_name] = {
                    'label': label,
                    'template_id': result_meta.get('template_id'),
                    'confidence': result.get('confidence', result_meta.get('confidence', 0))
                }

        merged_content = "\n\n".join(content_parts)

        return [{
            "content": merged_content,
            "metadata": {
                "source": "composite_intent_cross_adapter",
                "composite_routing": routing_metadata,
                "source_details": all_metadata
            },
            "confidence": min(
                (r.get('confidence', r.get('metadata', {}).get('confidence', 0.5))
                 for results in [res[2] for res in successful_results]
                 for r in results),
                default=0.5
            )
        }]

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
        cache_key = f"{query}:{','.join(sorted(f'{c.source_adapter}:{c.template_id}' for c in candidates))}"
        if self.cache_rerank_results and cache_key in self._rerank_cache:
            cached_time, cached_results = self._rerank_cache[cache_key]
            if time.time() - cached_time < self.rerank_cache_ttl:
                logger.debug("Using cached rerank results for query")
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

                # Evict oldest entries if cache exceeds max size
                if len(self._rerank_cache) > self._max_rerank_cache_size:
                    sorted_entries = sorted(self._rerank_cache.items(), key=lambda x: x[1][0])
                    for k, _ in sorted_entries[:len(sorted_entries) // 2]:
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

            # Rerank score — for candidates not sent to the reranker, use
            # their embedding score as a proxy to avoid a cliff effect where
            # position top_candidates vs top_candidates+1 causes a massive
            # score discontinuity (reranked=real_score vs not_reranked=0.0).
            if self.reranking_enabled:
                rerank_result = rerank_scores.get(match.template_id)
                rerank_score = rerank_result if rerank_result is not None else match.similarity_score
            else:
                rerank_score = 0.0
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

        # Sort by combined score (descending), with tie-breaker
        def _sort_key(m):
            score = m.combined_score or 0.0
            if self.tie_breaker == 'rerank':
                return (score, m.rerank_score or 0.0)
            # Default tie-breaker: embedding score
            return (score, m.similarity_score)

        matches.sort(key=_sort_key, reverse=True)

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
            # Over-fetch to account for per-example deduplication
            search_results = await adapter.template_store.search_similar_templates(
                query_embedding=query_embedding,
                limit=self.max_templates_per_source * 3,
                threshold=self.confidence_threshold
            )

            if not search_results:
                logger.debug(f"No template matches from adapter '{adapter_name}'")
                return matches

            # Deduplicate per-example vectors: per-example indexing stores
            # multiple vectors per template with IDs like "template_id::ex0".
            # Strip the "::exN" suffix and keep the highest-scoring hit per
            # base template, mirroring IntentSQLRetriever._find_best_templates.
            seen: Dict[str, Dict[str, Any]] = {}
            for result in search_results:
                raw_tid = result.get('template_id', '')
                base_tid = raw_tid.rsplit('::', 1)[0] if '::' in raw_tid else raw_tid
                score = result.get('score', 0)
                if base_tid not in seen or score > seen[base_tid].get('score', 0):
                    result_copy = dict(result)
                    result_copy['template_id'] = base_tid
                    seen[base_tid] = result_copy

            deduped = sorted(seen.values(), key=lambda r: r.get('score', 0), reverse=True)
            deduped = deduped[:self.max_templates_per_source]

            # Convert results to TemplateMatch objects
            for result in deduped:
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
                else:
                    logger.warning(
                        f"Template '{template_id}' not found in adapter '{adapter_name}' domain adapter"
                    )

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
        # Ensure embedding client is valid (may have been closed by cache cleanup)
        if not await self._ensure_embedding_client_valid():
            logger.error("Failed to ensure embedding client is valid")
            return []

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
        
        # Search cross-adapter templates if enabled
        if self.cross_adapter_enabled:
            cross_matches = await self._search_cross_adapter_templates(query_embedding)
            all_matches.extend(cross_matches)
            if cross_matches:
                logger.debug(f"Found {len(cross_matches)} cross-adapter template matches")

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

            # Check if this is a cross-adapter template match
            if best_match.template_data.get('cross_adapter'):
                logger.debug(
                    f"Cross-adapter template matched: '{best_match.template_id}' "
                    f"(score={best_match.similarity_score:.3f})"
                )
                results = await self._execute_cross_adapter_query(
                    query=query,
                    best_match=best_match,
                    api_key=api_key,
                    **kwargs
                )
                return results

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
        if self.embedding_client and getattr(self, '_owns_embedding_client', False):
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
        
        # Close cross-adapter template store if initialized
        if self._cross_adapter_template_store:
            try:
                close_method = getattr(self._cross_adapter_template_store, 'close', None)
                if close_method and callable(close_method):
                    if asyncio.iscoroutinefunction(close_method):
                        await close_method()
                    else:
                        close_method()
            except Exception as e:
                errors.append(f"cross_adapter_store: {e}")
                logger.warning(f"Error closing cross-adapter template store: {e}")

        # Note: We do NOT close child adapters here as they are managed
        # by the adapter manager and may be shared with other consumers
        
        if errors:
            logger.error(f"Errors closing CompositeIntentRetriever: {'; '.join(errors)}")
        
        logger.debug("CompositeIntentRetriever closed")
