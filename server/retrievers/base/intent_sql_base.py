"""
Unified Intent SQL Retriever base class that combines intent functionality
with database-specific implementations to reduce duplication.
"""

import logging
import traceback
import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple
from abc import abstractmethod

from .base_sql_database import BaseSQLDatabaseRetriever
from adapters.intent.adapter import IntentAdapter
from retrievers.implementations.intent.domain.extraction import DomainParameterExtractor
from retrievers.implementations.intent.domain.response import DomainResponseGenerator
from retrievers.implementations.intent.template_reranker import TemplateReranker
from retrievers.implementations.intent.template_processor import TemplateProcessor

logger = logging.getLogger(__name__)


class IntentSQLRetriever(BaseSQLDatabaseRetriever):
    """
    Unified base class for intent-based SQL retrievers.
    Combines intent functionality with database operations.
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, datasource: Any = None, **kwargs):
        """
        Initialize Intent SQL retriever.

        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter
            datasource: Datasource instance from the registry
            **kwargs: Additional arguments
        """
        super().__init__(config=config, datasource=datasource, **kwargs)

        # Get intent-specific configuration from standardized key
        self.intent_config = config.get('adapter_config', {})

        # Override return_results from intent_config if specified (fixes default of 3 in parent class)
        if 'return_results' in self.intent_config:
            self.return_results = self.intent_config.get('return_results')
            logger.info(f"Intent SQL retriever: return_results set to {self.return_results} from adapter config")
        else:
            logger.info(f"Intent SQL retriever: using default return_results={self.return_results} from parent class")

        # Store configuration for vector store
        self.store_name = self.intent_config.get('store_name')
        if not self.store_name:
            raise ValueError("store_name is required in adapter configuration. Please specify a store from stores.yaml")
        self.store_manager = None
        
        # Create IntentAdapter if not provided
        if not domain_adapter:
            domain_adapter = IntentAdapter(
                domain_config_path=self.intent_config.get('domain_config_path'),
                template_library_path=self.intent_config.get('template_library_path'),
                confidence_threshold=self.intent_config.get('confidence_threshold', 0.75),
                verbose=config.get('verbose', False),
                config=self.intent_config
            )
        
        self.domain_adapter = domain_adapter
        
        # Intent-specific settings
        self.template_collection_name = self.intent_config.get('template_collection_name', 'intent_query_templates')
        self.confidence_threshold = self.intent_config.get('confidence_threshold', 0.1)
        self.max_templates = self.intent_config.get('max_templates', 5)
        
        # Debug configuration values if verbose is enabled
        if self.verbose:
            logger.info(f"Intent config loaded - confidence_threshold: {self.confidence_threshold}, template_collection_name: {self.template_collection_name}, max_templates: {self.max_templates}")
            logger.info(f"Intent config keys: {list(self.intent_config.keys())}")
        
        # Initialize service clients
        self.embedding_client = None
        self.inference_client = None
        self.store_manager = None
        self.template_store = None
        
        # Domain-aware components
        self.parameter_extractor = None
        self.response_generator = None
        self.template_reranker = None
        self.template_processor: Optional[TemplateProcessor] = None
    
    def _get_store_config(self) -> Dict[str, Any]:
        """Get store configuration from stores.yaml based on store_name."""
        if not self.store_manager or not self.store_manager._config:
            raise ValueError(f"Store manager not initialized. Cannot retrieve store configuration for '{self.store_name}'")

        # Get vector stores configuration
        vector_stores = self.store_manager._config.get('vector_stores', {})

        # Find the store configuration
        if self.store_name not in vector_stores:
            raise ValueError(f"Store '{self.store_name}' not found in stores.yaml configuration")

        store_config = vector_stores[self.store_name]
        if not store_config.get('enabled', True):
            raise ValueError(f"Store '{self.store_name}' is disabled in stores.yaml configuration")

        # Get connection params and other settings directly from store config
        connection_params = store_config.get('connection_params', {}).copy()

        # Add collection name to connection params
        connection_params['collection_name'] = self.template_collection_name

        return {
            'type': self.store_name,
            'connection_params': connection_params,
            'pool_size': store_config.get('pool_size', 5),
            'timeout': store_config.get('timeout', 30),
            'ephemeral': connection_params.get('ephemeral', False),
            'auto_cleanup': store_config.get('auto_cleanup', True)
        }
    
    async def initialize(self) -> None:
        """Initialize intent-specific features and database connection."""
        try:
            logger.info(f"Initializing {self.__class__.__name__} for intent-based queries")

            # Ensure datasource is initialized (connection will be obtained automatically via property)
            await self._ensure_datasource_initialized()
            
            # Initialize embedding client
            await self._initialize_embedding_client()
            
            # Initialize inference client
            await self._initialize_inference_client()
            
            # Initialize vector store for template storage
            await self._initialize_vector_store()
            
            # Load templates into vector store
            await self._load_templates()
            
            # Initialize domain-aware components
            domain_config = self.domain_adapter.get_domain_config()

            # Get domain strategy once for all components
            from ..implementations.intent.domain_strategies.registry import DomainStrategyRegistry
            from ..implementations.intent.domain import DomainConfig

            # Ensure domain_config is a DomainConfig object
            if isinstance(domain_config, dict):
                domain_config = DomainConfig(domain_config)

            domain_strategy = DomainStrategyRegistry.get_strategy(
                domain_config.domain_name,
                domain_config,
            )

            # Pass the domain_strategy to avoid redundant registry lookups
            self.parameter_extractor = DomainParameterExtractor(self.inference_client, domain_config, domain_strategy)
            self.response_generator = DomainResponseGenerator(domain_config, domain_strategy)
            self.template_reranker = TemplateReranker(domain_config, domain_strategy)
            self.template_processor = TemplateProcessor(domain_config)
            
            if self.verbose:
                logger.info(f"{self.__class__.__name__} initialization complete")
                
        except Exception as e:
            logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _initialize_embedding_client(self):
        """Initialize embedding client with fallback support."""
        embedding_provider = self.datasource_config.get('embedding_provider')
        
        if not embedding_provider or embedding_provider == 'null':
            embedding_provider = self.config.get('embedding', {}).get('provider')
            logger.info(f"Using global embedding provider: {embedding_provider}")
        else:
            logger.info(f"Using datasource-specific embedding provider: {embedding_provider}")
        
        from embeddings.base import EmbeddingServiceFactory
        
        try:
            if embedding_provider:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, embedding_provider)
            else:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config)
            
            # Only initialize if not already initialized (singleton may be pre-initialized)
            if not self.embedding_client.initialized:
                await self.embedding_client.initialize()
                logger.info(f"Successfully initialized {embedding_provider} embedding provider")
            else:
                logger.debug(f"Embedding service already initialized, skipping initialization")
            
        except Exception as e:
            logger.warning(f"Failed to initialize {embedding_provider}: {e}")
            logger.info("Falling back to Ollama embedding provider")
            
            try:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, 'ollama')
                # Only initialize if not already initialized (singleton may be pre-initialized)
                if not self.embedding_client.initialized:
                    await self.embedding_client.initialize()
                    logger.info("Successfully initialized Ollama fallback embedding provider")
                else:
                    logger.debug(f"Ollama embedding service already initialized, skipping initialization")
            except Exception as fallback_error:
                logger.error(f"Failed to initialize fallback embedding provider: {fallback_error}")
                raise Exception("Unable to initialize any embedding provider")
    
    async def _initialize_inference_client(self):
        """Initialize inference client with adapter-specific override support."""
        from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory
        
        # Check if there's an inference_provider override in the config
        # This would be set by the DynamicAdapterManager when it loads the adapter
        inference_provider = self.config.get('inference_provider')
        
        if inference_provider:
            logger.info(f"Using adapter-specific inference provider: {inference_provider}")
            self.inference_client = ProviderFactory.create_provider_by_name(inference_provider, self.config)
        else:
            # Fall back to default provider
            logger.info("Using default inference provider from config")
            self.inference_client = ProviderFactory.create_provider(self.config)
        
        await self.inference_client.initialize()
    
    async def _initialize_vector_store(self):
        """Initialize vector store for template storage using the StoreManager."""
        try:
            # Import store components
            from vector_stores.base.store_manager import StoreManager
            from vector_stores.services.template_embedding_store import TemplateEmbeddingStore
            
            # Initialize store manager if not already available
            if not self.store_manager:
                self.store_manager = StoreManager()
                # Load configuration from the main config
                if hasattr(self.config, 'get') and self.config.get('stores'):
                    # If stores config is in main config, use it
                    self.store_manager._config = self.config.get('stores', {})
                else:
                    # Try to load from stores.yaml file
                    import yaml
                    from pathlib import Path
                    stores_config_path = Path('config/stores.yaml')
                    if stores_config_path.exists():
                        with open(stores_config_path, 'r') as f:
                            self.store_manager._config = yaml.safe_load(f)
                    else:
                        raise ValueError("stores.yaml configuration file not found and no stores config in main config")
            
            # Get store configuration from stores.yaml
            store_config = self._get_store_config()
            
            if self.verbose:
                logger.info(f"Using store '{self.store_name}' with type '{store_config.get('type', 'chroma')}'")
            
            # Create template embedding store with store manager
            self.template_store = TemplateEmbeddingStore(
                store_name=f'intent_templates_{self.store_name}',
                store_type=store_config.get('type', 'chroma'),
                collection_name=self.template_collection_name,
                config=store_config.get('connection_params', {}),
                store_manager=self.store_manager
            )
            
            # Initialize the template store
            if hasattr(self.template_store, 'initialize'):
                await self.template_store.initialize()
                
            # Clear existing templates if they have wrong dimensions
            try:
                # Get the expected dimension from current embedding client
                test_embedding = await self.embedding_client.embed_query("test")
                expected_dim = len(test_embedding) if test_embedding else 768
                logger.info(f"Expected embedding dimension from current client: {expected_dim}")
                
                stats = await self.template_store.get_statistics()
                existing_dim = stats.get('collection_metadata', {}).get('dimension')
                
                if existing_dim and existing_dim != expected_dim:
                    logger.warning(f"Existing collection has wrong dimension ({existing_dim}), expected {expected_dim}, recreating collection")
                    
                    # Delete the collection entirely and recreate with correct dimension
                    if hasattr(self.template_store, '_vector_store'):
                        vector_store = self.template_store._vector_store
                        collection_name = self.template_store.collection_name
                        
                        # Delete the collection
                        if await vector_store.collection_exists(collection_name):
                            await vector_store.delete_collection(collection_name)
                            logger.info(f"Deleted collection {collection_name}")
                        
                        # Recreate with correct dimension
                        await vector_store.create_collection(collection_name, dimension=expected_dim)
                        logger.info(f"Recreated collection {collection_name} with dimension {expected_dim}")
                        
            except Exception as e:
                logger.warning(f"Could not check/clear collection dimensions: {e}")
            
            # Set the embedding client if the store supports it
            if hasattr(self.template_store, 'set_embedding_client'):
                self.template_store.set_embedding_client(self.embedding_client)
            
            # Initialize the domain adapter embeddings if it supports it
            if hasattr(self.domain_adapter, 'initialize_embeddings'):
                # Pass the template store directly since we don't have a store manager
                await self.domain_adapter.initialize_embeddings()
            
            logger.info(f"Initialized vector store for template collection: {self.template_collection_name}")
            
        except ImportError as e:
            logger.error(f"Vector store system not available: {e}")
            raise Exception(f"Intent adapter requires vector store support. Install required dependencies.") from e
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
            raise Exception(f"Intent adapter requires a properly configured vector store. Failed to initialize store '{self.store_name}'.") from e
    
    async def _load_templates(self):
        """Load SQL templates from the adapter into vector store."""
        try:
            if not self.template_store:
                logger.warning("Template store not initialized, skipping template loading")
                return
            
            templates = self.domain_adapter.get_all_templates()
            
            if not templates:
                logger.warning("No templates found in template library")
                return
            
            logger.info(f"Loading {len(templates)} templates into vector store")
            
            # Check if we should reload templates
            force_reload = self.intent_config.get('force_reload_templates', False)
            reload_on_start = self.intent_config.get('reload_templates_on_start', True)
            
            # Also force reload if dimensions have changed
            dimension_changed = False
            try:
                stats = await self.template_store.get_statistics()
                existing_dim = stats.get('collection_metadata', {}).get('dimension')
                test_embedding = await self.embedding_client.embed_query("test")
                expected_dim = len(test_embedding) if test_embedding else 768
                if existing_dim and existing_dim != expected_dim:
                    dimension_changed = True
                    logger.info(f"Dimension changed from {existing_dim} to {expected_dim}, forcing reload")
            except:
                pass
            
            if not force_reload and not reload_on_start and not dimension_changed:
                # Check if templates already exist
                try:
                    stats = await self.template_store.get_statistics()
                    existing_count = stats.get('total_templates', 0)
                    if existing_count > 0:
                        logger.info(f"Found {existing_count} existing templates, skipping reload")
                        return
                except:
                    pass
            
            # Load templates into the template store
            loaded_count = 0
            
            # Prepare templates for batch embedding
            valid_templates = []
            embedding_texts = []
            
            for template in templates:
                if not isinstance(template, dict):
                    continue
                    
                template_id = template.get('id')
                if not template_id:
                    continue
                
                # Create embedding text for the template
                embedding_text = self._create_embedding_text(template)
                valid_templates.append(template)
                embedding_texts.append(embedding_text)
            
            # Batch generate embeddings for all templates
            embeddings = []
            if embedding_texts:
                try:
                    logger.info(f"Generating embeddings for {len(embedding_texts)} templates in batch...")
                    embeddings = await self.embedding_client.embed_documents(embedding_texts)
                    logger.info(f"Successfully generated {len(embeddings)} embeddings")
                except Exception as e:
                    logger.error(f"Failed to batch generate embeddings: {e}")
                    logger.info("Falling back to individual embedding generation...")
                    # Fallback to individual generation
                    for text in embedding_texts:
                        try:
                            embedding = await self.embedding_client.embed_query(text)
                            embeddings.append(embedding)
                        except Exception as e2:
                            logger.error(f"Failed to generate embedding: {e2}")
                            embeddings.append(None)
            
            # Prepare templates with embeddings
            templates_with_embeddings = []
            for i, (template, embedding) in enumerate(zip(valid_templates, embeddings)):
                if embedding:
                    template_id = template.get('id')
                    template_data = {
                        'sql': template.get('sql', ''),
                        'description': template.get('description', ''),
                        'category': template.get('category', 'general'),
                        'parameters': template.get('parameters', []),
                        'examples': template.get('nl_examples', [])
                    }
                    templates_with_embeddings.append((template_id, template_data, embedding))
            
            # Batch add templates to the store
            if templates_with_embeddings:
                try:
                    if self.verbose:
                        logger.info(f"Adding {len(templates_with_embeddings)} templates with embeddings to store")
                    results = await self.template_store.batch_add_templates(templates_with_embeddings)
                    loaded_count = sum(1 for success in results.values() if success)
                    logger.info(f"Successfully loaded {loaded_count} templates into vector store")
                    
                    # Verify the templates are actually in the store
                    if self.verbose:
                        try:
                            post_stats = await self.template_store.get_statistics()
                            logger.info(f"Vector store now contains {post_stats.get('total_templates', 0)} templates")
                        except Exception as e:
                            logger.debug(f"Could not get post-load stats: {e}")
                        
                except Exception as e:
                    logger.error(f"Failed to add templates to store: {e}")
                    logger.error(traceback.format_exc())
            
            if loaded_count == 0:
                logger.warning("No templates were loaded into vector store")
                if self.verbose and templates:
                    logger.info(f"Found {len(templates)} templates from adapter but none were loaded")
            else:
                logger.info(f"Template loading complete: {loaded_count} templates loaded")
            
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            logger.error(traceback.format_exc())
    
    def _create_embedding_text(self, template: Dict[str, Any]) -> str:
        """Create text for embedding from template."""
        # Extract only string tags (ignore dict tags which contain function metadata)
        tags = template.get('tags', [])
        string_tags = [tag for tag in tags if isinstance(tag, str)]

        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(string_tags)
        ]
        
        param_names = [p['name'].replace('_', ' ') for p in template.get('parameters', [])]
        parts.extend(param_names)
        
        if 'semantic_tags' in template:
            tags = template['semantic_tags']
            parts.append(tags.get('action', ''))
            primary_entity = tags.get('primary_entity', '')
            parts.append(primary_entity)
            if tags.get('secondary_entity'):
                parts.append(tags['secondary_entity'])
            parts.extend(tags.get('qualifiers', []))
            
            domain_config = self.domain_adapter.get_domain_config()
            if domain_config and primary_entity:
                vocabulary = domain_config.get('vocabulary', {})
                entity_synonyms = vocabulary.get('entity_synonyms', {})
                if primary_entity in entity_synonyms:
                    parts.extend(entity_synonyms[primary_entity])
        
        return ' '.join(filter(None, parts))
    
    def _create_template_metadata(self, template: Dict[str, Any]) -> Dict[str, Any]:
        """Create metadata for ChromaDB storage."""
        metadata = {
            'template_id': template.get('id', ''),
            'description': template.get('description', ''),
            'category': template.get('category', 'general'),
            'complexity': template.get('complexity', 'medium')
        }
        
        if 'semantic_tags' in template:
            for key, value in template['semantic_tags'].items():
                metadata[f'semantic_{key}'] = str(value)
        
        return metadata
    
    async def get_relevant_context(self, query: str, api_key: Optional[str] = None,
                                 collection_name: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Process a natural language query using intent-based SQL translation."""
        try:
            if self.verbose:
                logger.info(f"Processing intent query: {query}")
            
            # Find best matching template
            templates = await self._find_best_templates(query)
            
            if not templates:
                logger.warning("No matching templates found")
                return [{
                    "content": "I couldn't find a matching query pattern for your request.",
                    "metadata": {"source": "intent", "error": "no_matching_template"},
                    "confidence": 0.0
                }]
            
            # Rerank templates using domain-specific rules
            if self.template_reranker:
                templates = self.template_reranker.rerank_templates(templates, query)
            
            # Try templates in order of relevance
            for template_info in templates:
                template = template_info['template']
                similarity = template_info['similarity']
                
                if similarity < self.confidence_threshold:
                    continue
                
                if self.verbose:
                    logger.info(f"Trying template: {template.get('id')} (similarity: {similarity:.2%})")
                
                # Extract parameters
                if self.parameter_extractor:
                    parameters = await self.parameter_extractor.extract_parameters(query, template)
                    validation_errors = self.parameter_extractor.validate_parameters(parameters)
                    if validation_errors:
                        if self.verbose:
                            logger.debug(f"Parameter validation failed for template {template.get('id')}: {validation_errors}")
                        continue
                else:
                    parameters = await self._extract_parameters(query, template)
                
                # Execute template
                results, error = await self._execute_template(template, parameters)

                if error:
                    if self.verbose:
                        logger.debug(f"Template {template.get('id')} execution failed: {error}")
                    continue

                # Track original count before any truncation
                original_result_count = len(results) if results else 0
                was_truncated = False

                if self.verbose and results:
                    logger.info(f"SQL query returned {original_result_count} rows from database")

                # Apply truncation if needed
                if results and self.return_results is not None and len(results) > self.return_results:
                    logger.info(f"Truncating result set from {len(results)} to {self.return_results} results based on adapter config (return_results={self.return_results})")
                    results = results[:self.return_results]
                    was_truncated = True

                # Format response using domain-aware generator
                if self.response_generator:
                    formatted_data = self.response_generator.format_response_data(results, template)

                    # Create content string from formatted data
                    content_parts = []
                    if formatted_data.get("message"):
                        content_parts.append(formatted_data["message"])

                    # Add summary or table based on format
                    if formatted_data.get("summary"):
                        content_parts.append(formatted_data["summary"])
                    elif formatted_data.get("table") and formatted_data["table"].get("rows"):
                        # Format a simple table representation
                        table_data = formatted_data["table"]
                        columns = table_data["columns"]
                        rows = table_data["rows"][:self.return_results] if self.return_results else table_data["rows"]

                        table_text = " | ".join(columns) + "\n"
                        table_text += "-" * len(table_text) + "\n"
                        for row in rows:
                            table_text += " | ".join(str(v) for v in row) + "\n"

                        # Show truncation status in message
                        if was_truncated:
                            result_message = f"Showing {len(results)} of {original_result_count} total results (truncated):\n{table_text}"
                        else:
                            result_message = f"Found {formatted_data['result_count']} results:\n{table_text}"

                        content_parts.append(result_message)

                    if not content_parts:
                        # Fallback to simple result summary
                        if was_truncated:
                            content_parts.append(f"Query executed successfully. Showing {len(results)} of {original_result_count} total results.")
                        else:
                            content_parts.append(f"Query executed successfully. Found {len(results)} results.")

                    content = "\n\n".join(content_parts)

                    if self.verbose:
                        logger.info(f"Generated content for LLM context (length: {len(content)}):\n{content}")
                        if was_truncated:
                            logger.info(f"Note: LLM will only see {len(results)} of {original_result_count} records")

                    return [{
                        "content": content,
                        "metadata": {
                            "source": "intent",
                            "template_id": template.get('id'),
                            "query_intent": template.get('description', ''),
                            "parameters_used": parameters,
                            "formatted_data": formatted_data,
                            "similarity": similarity,
                            "result_count": len(results),  # Actual count passed to LLM
                            "total_available": original_result_count,  # Total from SQL
                            "truncated": was_truncated,  # Truncation flag
                            "domain_aware": True
                        },
                        "confidence": similarity
                    }]
                else:
                    # Pass original count and truncation info to fallback formatter
                    formatted_results = self._format_sql_results(
                        results, template, parameters, similarity,
                        original_count=original_result_count,
                        was_truncated=was_truncated
                    )
                    if formatted_results:
                        return formatted_results
            
            return [{
                "content": "I found potential matches but couldn't extract the required information.",
                "metadata": {"source": "intent", "error": "parameter_extraction_failed"},
                "confidence": 0.0
            }]
            
        except Exception as e:
            logger.error(f"Error in intent-based retrieval: {e}")
            logger.error(traceback.format_exc())
            return [{
                "content": f"An error occurred while processing your query: {e}",
                "metadata": {"source": "intent", "error": str(e)},
                "confidence": 0.0
            }]
    
    async def _find_best_templates(self, query: str) -> List[Dict[str, Any]]:
        """Find best matching templates for the query."""
        try:
            if not self.template_store:
                logger.warning("Template store not available, cannot perform similarity search")
                return []
            
            # Check template store stats
            if self.verbose:
                try:
                    stats = await self.template_store.get_statistics()
                    total_templates = stats.get('total_templates', 0)
                    cached_templates = stats.get('cached_templates', 0)
                    collection_name = stats.get('collection_name', 'unknown')
                    logger.info(f"Template store stats - total: {total_templates}, cached: {cached_templates}, collection: {collection_name}")
                except Exception as e:
                    logger.debug(f"Could not get template store stats: {e}")
            
            # Get query embedding
            query_embedding = await self.embedding_client.embed_query(query)
            if not query_embedding:
                logger.error("Failed to get query embedding")
                return []
            
            if self.verbose:
                logger.info(f"Query embedding generated with {len(query_embedding)} dimensions")
            
            # Check dimension compatibility
            try:
                stats = await self.template_store.get_statistics()
                collection_dim = stats.get('collection_metadata', {}).get('dimension')
                if collection_dim and collection_dim != len(query_embedding):
                    logger.error(f"Dimension mismatch: query embedding has {len(query_embedding)} dims, collection has {collection_dim} dims")
                    logger.error("This will prevent similarity search from working. Collection needs to be recreated with matching dimensions.")
                    return []
            except Exception as e:
                logger.debug(f"Could not verify dimension compatibility: {e}")
            
            # Search for similar templates
            search_results = await self.template_store.search_similar_templates(
                query_embedding=query_embedding,
                limit=self.max_templates,
                threshold=self.confidence_threshold
            )
            
            if self.verbose:
                if search_results:
                    scores = [f"{result.get('score', 0):.3f}" for result in search_results]
                    scores_str = ", ".join(scores)
                    logger.info(f"Similarity search with threshold {self.confidence_threshold} returned {len(search_results)} results with scores: [{scores_str}]")
                else:
                    logger.info(f"Similarity search with threshold {self.confidence_threshold} returned 0 results")
            
            if not search_results:
                return []
            
            templates = []
            for result in search_results:
                template_id = result.get('template_id')
                template = self.domain_adapter.get_template_by_id(template_id)
                if template:
                    # Merge template data with search result
                    templates.append({
                        'template': template,
                        'similarity': result.get('score', 0),
                        'embedding_text': result.get('description', '')
                    })
                else:
                    if self.verbose:
                        logger.warning(f"Template {template_id} not found in adapter")
            
            if self.verbose:
                logger.info(f"Found {len(templates)} matching templates for query")
            return templates
            
        except Exception as e:
            logger.error(f"Error finding templates: {e}")
            logger.error(traceback.format_exc())
            return []
    
    async def _extract_parameters(self, query: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from the query using LLM."""
        try:
            parameters = {}
            required_params = template.get('parameters', [])
            
            if not required_params:
                return parameters
            
            param_descriptions = []
            for param in required_params:
                desc = f"- {param['name']} ({param['type']}): {param['description']}"
                if 'example' in param:
                    desc += f" (Example: {param['example']})"
                if 'allowed_values' in param:
                    desc += f" - Allowed values: {', '.join(param['allowed_values'])}"
                param_descriptions.append(desc)
            
            extraction_prompt = f"""Extract the following parameters from the user query.
Return ONLY a valid JSON object with the extracted values.
Use null for parameters that cannot be found.

Parameters needed:
{chr(10).join(param_descriptions)}

User query: "{query}"

JSON:"""
            
            response = await self.inference_client.generate(extraction_prompt)
            
            import re
            import json
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parameters = json.loads(json_match.group())
            
            for param in required_params:
                # Apply default if parameter is missing or None
                if (param['name'] not in parameters or parameters[param['name']] is None) and 'default' in param:
                    parameters[param['name']] = param['default']
            
            if self.verbose:
                logger.info(f"Extracted parameters: {parameters}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting parameters: {e}")
            return {}
    
    async def _execute_template(self, template: Dict[str, Any], parameters: Dict[str, Any]) -> Tuple[List[Dict], Optional[str]]:
        """Execute SQL template with parameters."""
        try:
            sql_template = template.get('sql_template', template.get('sql', ''))

            if not sql_template:
                return [], "Template has no SQL query"

            formatted_parameters = parameters.copy()
            for param_name, param_value in formatted_parameters.items():
                if param_value and isinstance(param_value, str) and 'name' in param_name.lower() and 'LIKE' in sql_template.upper():
                    cleaned_value = param_value.strip().strip('"').strip("'")
                    formatted_parameters[param_name] = f"%{cleaned_value}%"

            sql_query = self._process_sql_template(sql_template, formatted_parameters)

            if self.verbose:
                logger.info(f"Executing SQL: {sql_query}")

            # Check for different parameter formats
            has_named_params = bool(re.search(r'%\((\w+)\)s', sql_query))
            has_duckdb_named_params = bool(re.search(r':(\w+)', sql_query))
            has_positional_params = '?' in sql_query
            
            param_list = template.get('parameters', [])
            
            if has_named_params:
                # PostgreSQL-style named parameters: %(name)s
                # Ensure all referenced parameters are in the dict (even if None)
                param_names_in_sql = re.findall(r'%\((\w+)\)s', sql_query)
                for param_name in param_names_in_sql:
                    if param_name not in formatted_parameters:
                        # Try to get from template defaults
                        param_def = next((p for p in param_list if p.get('name') == param_name), None)
                        if param_def and 'default' in param_def:
                            formatted_parameters[param_name] = param_def['default']
                        else:
                            formatted_parameters[param_name] = None
                # Use dict for named parameters
                results = await self.execute_query(sql_query, formatted_parameters)
            elif has_duckdb_named_params:
                # DuckDB/SQLite-style named parameters: :name
                # Ensure all referenced parameters are in the dict (even if None)
                param_names_in_sql = re.findall(r':(\w+)', sql_query)
                for param_name in param_names_in_sql:
                    if param_name not in formatted_parameters:
                        # Try to get from template defaults
                        param_def = next((p for p in param_list if p.get('name') == param_name), None)
                        if param_def and 'default' in param_def:
                            formatted_parameters[param_name] = param_def['default']
                        else:
                            formatted_parameters[param_name] = None
                # Use dict for named parameters (DuckDB retriever will convert :name to ?)
                results = await self.execute_query(sql_query, formatted_parameters)
            elif has_positional_params and param_list:
                # SQLite-style positional parameters: ?
                # Build tuple in order of template parameters (preserving duplicates)
                param_tuple = tuple(formatted_parameters.get(p['name'], p.get('default')) for p in param_list)
                results = await self.execute_query(sql_query, param_tuple)
            else:
                # No parameters or unknown format, use the dict
                results = await self.execute_query(sql_query, formatted_parameters)

            return results, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing template: {error_msg}")
            return [], error_msg
    
    def _process_sql_template(self, sql_template: str, parameters: Dict[str, Any]) -> str:
        """Process SQL template with parameter substitution."""
        try:
            if self.template_processor:
                rendered = self.template_processor.render_sql(
                    sql_template,
                    parameters=parameters,
                    preserve_unknown=False,
                )
                if '{{' in rendered or '{%' in rendered:
                    logger.debug("Rendered SQL still contains unresolved delimiters: %s", rendered)
                return rendered

            def replace_if_block(match):
                param_name = match.group(1).strip()
                content = match.group(2)
                
                if param_name in parameters and parameters[param_name] is not None:
                    return content
                else:
                    return ""
            
            pattern = r'{% *if +([^%]+) *%}(.*?){% *endif *%}'
            processed_sql = re.sub(pattern, replace_if_block, sql_template, flags=re.DOTALL)
            
            return processed_sql.strip()
            
        except Exception as e:
            logger.warning(f"Error processing SQL template: {e}")
            return sql_template
    
    def _format_sql_results(self, results: List[Dict], template: Dict, parameters: Dict, similarity: float,
                           original_count: int = None, was_truncated: bool = False) -> List[Dict[str, Any]]:
        """Format SQL results into context documents."""
        if not results:
            return [{
                "content": "No results found for your query.",
                "metadata": {
                    "source": "intent",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0,
                    "total_available": 0,
                    "truncated": False
                },
                "confidence": similarity
            }]

        import json

        # Set original count if not provided
        if original_count is None:
            original_count = len(results)

        formatted_doc = self.domain_adapter.format_document(
            raw_doc=json.dumps(results, default=str),
            metadata={
                "source": "intent",
                "template_id": template.get('id'),
                "query_intent": template.get('description', ''),
                "parameters_used": parameters,
                "results": results,
                "similarity": similarity,
                "result_count": len(results),  # Actual count passed to LLM
                "total_available": original_count,  # Total from SQL
                "truncated": was_truncated  # Truncation flag
            }
        )

        formatted_doc["confidence"] = similarity

        return [formatted_doc]
    
    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection/table for intent-based queries.
        
        Args:
            collection_name: Name of the table to use for SQL execution
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
            
        # Set the collection name (this affects SQL execution context)
        self.collection = collection_name
        if self.verbose:
            logger.info(f"{self.__class__.__name__} switched to collection (table): {collection_name}")

    async def close(self) -> None:
        """
        Close adapter-specific resources (embedding, inference, template store).
        
        Note: Database connections are managed by the datasource registry with
        reference counting. They should NOT be closed here - the registry will
        close them when the reference count reaches 0.
        """
        errors = []
        
        # DO NOT close database connection here - it's managed by datasource registry
        # The datasource registry uses reference counting and will close the connection
        # when all adapters using it are removed (reference count reaches 0).
        # Closing it here would break other adapters sharing the same datasource.
        
        # Close embedding client
        if self.embedding_client:
            try:
                # Try aclose() first (httpx AsyncClient uses aclose)
                aclose_method = getattr(self.embedding_client, 'aclose', None)
                if aclose_method and callable(aclose_method):
                    await aclose_method()
                else:
                    # Try close() method
                    close_method = getattr(self.embedding_client, 'close', None)
                    if close_method and callable(close_method):
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
            except AttributeError as e:
                # Client doesn't have close method - this is okay, just log it
                logger.debug(f"Embedding client {type(self.embedding_client).__name__} doesn't have close/aclose method: {e}")
            except Exception as e:
                errors.append(f"embedding: {e}")
                logger.warning(f"Error closing embedding client in {self.__class__.__name__}: {e}")
        
        # Close inference client
        if self.inference_client:
            try:
                # Try aclose() first (httpx AsyncClient uses aclose)
                aclose_method = getattr(self.inference_client, 'aclose', None)
                if aclose_method and callable(aclose_method):
                    await aclose_method()
                else:
                    # Try close() method
                    close_method = getattr(self.inference_client, 'close', None)
                    if close_method and callable(close_method):
                        if asyncio.iscoroutinefunction(close_method):
                            await close_method()
                        else:
                            close_method()
            except AttributeError as e:
                # Client doesn't have close method - this is okay, just log it
                logger.debug(f"Inference client {type(self.inference_client).__name__} doesn't have close/aclose method: {e}")
            except Exception as e:
                errors.append(f"inference: {e}")
                logger.warning(f"Error closing inference client in {self.__class__.__name__}: {e}")
        
        # Close template store if it exists
        if hasattr(self, 'template_store') and self.template_store:
            try:
                if hasattr(self.template_store, 'close'):
                    if asyncio.iscoroutinefunction(self.template_store.close):
                        await self.template_store.close()
                    else:
                        self.template_store.close()
            except Exception as e:
                errors.append(f"template_store: {e}")
                logger.warning(f"Error closing template store in {self.__class__.__name__}: {e}")
        
        if errors:
            logger.error(f"Errors closing {self.__class__.__name__}: {'; '.join(errors)}")
