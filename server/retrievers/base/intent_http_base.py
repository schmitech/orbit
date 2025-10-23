"""
Base HTTP retriever for intent-based HTTP datasources (Elasticsearch, Solr, REST APIs, etc.)

This base class provides HTTP transport and intent-based query translation for all HTTP-based
data sources, following the same architecture as IntentSQLRetriever but for HTTP endpoints.
"""

import logging
import traceback
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple
from abc import abstractmethod

from .base_retriever import BaseRetriever
from retrievers.implementations.intent.domain.extraction import DomainParameterExtractor
from retrievers.implementations.intent.domain.response import DomainResponseGenerator
from retrievers.implementations.intent.template_reranker import TemplateReranker
from retrievers.implementations.intent.template_processor import TemplateProcessor

logger = logging.getLogger(__name__)


class IntentHTTPRetriever(BaseRetriever):
    """
    Unified base class for intent-based HTTP retrievers.

    This class combines intent functionality with HTTP operations, similar to how
    IntentSQLRetriever works for SQL databases. It provides:
    - HTTP client management with authentication
    - Vector store integration for template matching
    - Natural language to HTTP request translation
    - Response processing and formatting

    Subclasses should implement:
    - _execute_http_request: Execute the actual HTTP request
    - _format_http_response: Format the HTTP response
    - _process_http_template: Process template-specific HTTP configurations
    """

    def __init__(self, config: Dict[str, Any], domain_adapter=None,
                 datasource: Any = None, **kwargs):
        """
        Initialize Intent HTTP retriever.

        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter
            datasource: Optional datasource instance
            **kwargs: Additional arguments
        """
        super().__init__(config=config, domain_adapter=domain_adapter, **kwargs)

        # Get intent-specific configuration from standardized key
        self.intent_config = config.get('adapter_config', {})

        # Store configuration for vector store
        self.store_name = self.intent_config.get('store_name')
        if not self.store_name:
            raise ValueError("store_name is required in adapter configuration. Please specify a store from stores.yaml")
        self.store_manager = None

        # HTTP configuration
        self.base_url = self.intent_config.get('base_url')
        if not self.base_url:
            raise ValueError("base_url is required in adapter configuration")

        self.timeout = self.intent_config.get('timeout', 30)
        self.verify_ssl = self.intent_config.get('verify_ssl', True)
        self.auth_config = self.intent_config.get('auth', {})

        # HTTP client (will be initialized during initialize())
        self.http_client: Optional[httpx.AsyncClient] = None

        # Create domain adapter if not provided
        if not domain_adapter:
            from adapters.factory import DocumentAdapterFactory
            adapter_type = self.intent_config.get('adapter_type', 'http')
            domain_adapter = DocumentAdapterFactory.create_adapter(
                adapter_type,
                domain_config_path=self.intent_config.get('domain_config_path'),
                template_library_path=self.intent_config.get('template_library_path'),
                confidence_threshold=self.intent_config.get('confidence_threshold', 0.75),
                verbose=config.get('verbose', False),
                config=self.intent_config
            )

        self.domain_adapter = domain_adapter

        # Intent-specific settings
        self.template_collection_name = self.intent_config.get('template_collection_name',
                                                               'intent_http_templates')
        self.confidence_threshold = self.intent_config.get('confidence_threshold', 0.1)
        self.max_templates = self.intent_config.get('max_templates', 5)

        # Debug configuration
        if self.verbose:
            logger.info(f"Intent HTTP config loaded - confidence_threshold: {self.confidence_threshold}, "
                       f"template_collection_name: {self.template_collection_name}, "
                       f"max_templates: {self.max_templates}")

        # Initialize service clients
        self.embedding_client = None
        self.inference_client = None
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

        vector_stores = self.store_manager._config.get('vector_stores', {})

        if self.store_name not in vector_stores:
            raise ValueError(f"Store '{self.store_name}' not found in stores.yaml configuration")

        store_config = vector_stores[self.store_name]
        if not store_config.get('enabled', True):
            raise ValueError(f"Store '{self.store_name}' is disabled in stores.yaml configuration")

        connection_params = store_config.get('connection_params', {}).copy()
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
        """Initialize HTTP client and intent-specific features."""
        try:
            logger.info(f"Initializing {self.__class__.__name__} for intent-based HTTP queries")

            # Initialize HTTP client
            await self._initialize_http_client()

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

            from retrievers.implementations.intent.domain_strategies.registry import DomainStrategyRegistry
            from retrievers.implementations.intent.domain import DomainConfig

            if isinstance(domain_config, dict):
                domain_config = DomainConfig(domain_config)

            domain_strategy = DomainStrategyRegistry.get_strategy(
                domain_config.domain_name,
                domain_config,
            )

            self.parameter_extractor = DomainParameterExtractor(
                self.inference_client, domain_config, domain_strategy)
            self.response_generator = DomainResponseGenerator(domain_config, domain_strategy)
            self.template_reranker = TemplateReranker(domain_config, domain_strategy)
            self.template_processor = TemplateProcessor(domain_config)

            if self.verbose:
                logger.info(f"{self.__class__.__name__} initialization complete")

        except Exception as e:
            logger.error(f"Failed to initialize {self.__class__.__name__}: {e}")
            logger.error(traceback.format_exc())
            raise

    async def _initialize_http_client(self):
        """Initialize HTTP client with authentication and SSL settings."""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'ORBIT-Intent-Retriever/1.0'
        }

        # Add authentication headers
        auth_headers = self._build_auth_headers()
        headers.update(auth_headers)

        # Create HTTP client with connection pooling
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )

        logger.info(f"HTTP client initialized for base URL: {self.base_url}")

    def _build_auth_headers(self, template: Optional[Dict] = None) -> Dict[str, str]:
        """
        Build authentication headers based on configuration.

        Supports: basic_auth, api_key, bearer_token
        """
        headers = {}
        auth_type = self.auth_config.get('type', 'none')

        if auth_type == 'basic_auth':
            import os
            import base64
            username_env = self.auth_config.get('username_env', 'HTTP_USERNAME')
            password_env = self.auth_config.get('password_env', 'HTTP_PASSWORD')

            username = os.getenv(username_env)
            password = os.getenv(password_env)

            if username and password:
                credentials = f"{username}:{password}"
                encoded = base64.b64encode(credentials.encode()).decode()
                headers['Authorization'] = f'Basic {encoded}'

        elif auth_type == 'api_key':
            import os
            api_key_env = self.auth_config.get('api_key_env', 'HTTP_API_KEY')
            api_key = os.getenv(api_key_env)
            header_name = self.auth_config.get('header_name', 'X-API-Key')
            if api_key:
                headers[header_name] = api_key

        elif auth_type == 'bearer_token':
            import os
            token_env = self.auth_config.get('token_env', 'HTTP_TOKEN')
            token = os.getenv(token_env)
            if token:
                headers['Authorization'] = f'Bearer {token}'

        return headers

    async def _initialize_embedding_client(self):
        """Initialize embedding client with fallback support."""
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
                logger.info(f"Successfully initialized {embedding_provider} embedding provider")
            else:
                logger.debug("Embedding service already initialized, skipping initialization")

        except Exception as e:
            logger.warning(f"Failed to initialize {embedding_provider}: {e}")
            logger.info("Falling back to Ollama embedding provider")

            try:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(
                    self.config, 'ollama')
                if not self.embedding_client.initialized:
                    await self.embedding_client.initialize()
                    logger.info("Successfully initialized Ollama fallback embedding provider")
            except Exception as fallback_error:
                logger.error(f"Failed to initialize fallback embedding provider: {fallback_error}")
                raise Exception("Unable to initialize any embedding provider")

    async def _initialize_inference_client(self):
        """Initialize inference client with adapter-specific override support."""
        from inference.pipeline.providers import UnifiedProviderFactory as ProviderFactory

        inference_provider = self.config.get('inference_provider')

        if inference_provider:
            logger.info(f"Using adapter-specific inference provider: {inference_provider}")
            self.inference_client = ProviderFactory.create_provider_by_name(
                inference_provider, self.config)
        else:
            logger.info("Using default inference provider from config")
            self.inference_client = ProviderFactory.create_provider(self.config)

        await self.inference_client.initialize()

    async def _initialize_vector_store(self):
        """Initialize vector store for template storage using the StoreManager."""
        try:
            from vector_stores.base.store_manager import StoreManager
            from vector_stores.services.template_embedding_store import TemplateEmbeddingStore

            if not self.store_manager:
                self.store_manager = StoreManager()
                if hasattr(self.config, 'get') and self.config.get('stores'):
                    self.store_manager._config = self.config.get('stores', {})
                else:
                    import yaml
                    from pathlib import Path
                    stores_config_path = Path('config/stores.yaml')
                    if stores_config_path.exists():
                        with open(stores_config_path, 'r') as f:
                            self.store_manager._config = yaml.safe_load(f)
                    else:
                        raise ValueError("stores.yaml configuration file not found")

            store_config = self._get_store_config()

            if self.verbose:
                logger.info(f"Using store '{self.store_name}' with type '{store_config.get('type', 'chroma')}'")

            self.template_store = TemplateEmbeddingStore(
                store_name=f'intent_http_templates_{self.store_name}',
                store_type=store_config.get('type', 'chroma'),
                collection_name=self.template_collection_name,
                config=store_config.get('connection_params', {}),
                store_manager=self.store_manager
            )

            if hasattr(self.template_store, 'initialize'):
                await self.template_store.initialize()

            # Clear existing templates if they have wrong dimensions
            try:
                test_embedding = await self.embedding_client.embed_query("test")
                expected_dim = len(test_embedding) if test_embedding else 768
                logger.info(f"Expected embedding dimension from current client: {expected_dim}")

                stats = await self.template_store.get_statistics()
                existing_dim = stats.get('collection_metadata', {}).get('dimension')

                if existing_dim and existing_dim != expected_dim:
                    logger.warning(f"Existing collection has wrong dimension ({existing_dim}), "
                                 f"expected {expected_dim}, recreating collection")

                    if hasattr(self.template_store, '_vector_store'):
                        vector_store = self.template_store._vector_store
                        collection_name = self.template_store.collection_name

                        if await vector_store.collection_exists(collection_name):
                            await vector_store.delete_collection(collection_name)
                            logger.info(f"Deleted collection {collection_name}")

                        await vector_store.create_collection(collection_name, dimension=expected_dim)
                        logger.info(f"Recreated collection {collection_name} with dimension {expected_dim}")

            except Exception as e:
                logger.warning(f"Could not check/clear collection dimensions: {e}")

            # Set the embedding client
            if hasattr(self.template_store, 'set_embedding_client'):
                self.template_store.set_embedding_client(self.embedding_client)

            logger.info(f"Initialized vector store for template collection: {self.template_collection_name}")

        except ImportError as e:
            logger.error(f"Vector store system not available: {e}")
            raise Exception("Intent adapter requires vector store support") from e
        except Exception as e:
            logger.error(f"Error initializing vector store: {e}")
            raise Exception(f"Intent adapter requires a properly configured vector store. "
                          f"Failed to initialize store '{self.store_name}'.") from e

    async def _load_templates(self):
        """Load HTTP templates from the adapter into vector store."""
        try:
            if not self.template_store:
                logger.warning("Template store not initialized, skipping template loading")
                return

            templates = self.domain_adapter.get_all_templates()

            if not templates:
                logger.warning("No templates found in template library")
                return

            logger.info(f"Loading {len(templates)} templates into vector store")

            force_reload = self.intent_config.get('force_reload_templates', False)
            reload_on_start = self.intent_config.get('reload_templates_on_start', True)

            # Check if we should reload
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
                try:
                    stats = await self.template_store.get_statistics()
                    existing_count = stats.get('total_templates', 0)
                    if existing_count > 0:
                        logger.info(f"Found {existing_count} existing templates, skipping reload")
                        return
                except:
                    pass

            # Prepare templates for batch embedding
            valid_templates = []
            embedding_texts = []

            for template in templates:
                if not isinstance(template, dict):
                    continue

                template_id = template.get('id')
                if not template_id:
                    continue

                embedding_text = self._create_embedding_text(template)
                valid_templates.append(template)
                embedding_texts.append(embedding_text)

            # Batch generate embeddings
            embeddings = []
            if embedding_texts:
                try:
                    logger.info(f"Generating embeddings for {len(embedding_texts)} templates in batch...")
                    embeddings = await self.embedding_client.embed_documents(embedding_texts)
                    logger.info(f"Successfully generated {len(embeddings)} embeddings")
                except Exception as e:
                    logger.error(f"Failed to batch generate embeddings: {e}")
                    logger.info("Falling back to individual embedding generation...")
                    for text in embedding_texts:
                        try:
                            embedding = await self.embedding_client.embed_query(text)
                            embeddings.append(embedding)
                        except Exception as e2:
                            logger.error(f"Failed to generate embedding: {e2}")
                            embeddings.append(None)

            # Prepare templates with embeddings
            templates_with_embeddings = []
            for template, embedding in zip(valid_templates, embeddings):
                if embedding:
                    template_id = template.get('id')
                    # Store the appropriate template field based on type
                    template_field = template.get('query_dsl') or template.get('http_request') or template.get('endpoint_template', '')
                    template_data = {
                        'query_dsl': template_field,  # Generic field for any HTTP template
                        'description': template.get('description', ''),
                        'category': template.get('category', 'general'),
                        'parameters': template.get('parameters', []),
                        'examples': template.get('nl_examples', [])
                    }
                    templates_with_embeddings.append((template_id, template_data, embedding))

            # Batch add templates
            if templates_with_embeddings:
                try:
                    if self.verbose:
                        logger.info(f"Adding {len(templates_with_embeddings)} templates with embeddings to store")
                    results = await self.template_store.batch_add_templates(templates_with_embeddings)
                    loaded_count = sum(1 for success in results.values() if success)
                    logger.info(f"Successfully loaded {loaded_count} templates into vector store")

                    if self.verbose:
                        try:
                            post_stats = await self.template_store.get_statistics()
                            logger.info(f"Vector store now contains {post_stats.get('total_templates', 0)} templates")
                        except Exception as e:
                            logger.debug(f"Could not get post-load stats: {e}")

                except Exception as e:
                    logger.error(f"Failed to add templates to store: {e}")
                    logger.error(traceback.format_exc())

        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            logger.error(traceback.format_exc())

    def _create_embedding_text(self, template: Dict[str, Any]) -> str:
        """Create text for embedding from template."""
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

    async def get_relevant_context(self, query: str, api_key: Optional[str] = None,
                                   collection_name: Optional[str] = None,
                                   **kwargs) -> List[Dict[str, Any]]:
        """Process a natural language query using intent-based HTTP translation."""
        try:
            if self.verbose:
                logger.info(f"Processing intent query: {query}")

            # Find best matching templates
            templates = await self._find_best_templates(query)

            if not templates:
                logger.warning("No matching templates found")
                return [{
                    "content": "I couldn't find a matching query pattern for your request.",
                    "metadata": {"source": "intent_http", "error": "no_matching_template"},
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

                # Format response using domain-aware generator
                if self.response_generator:
                    formatted_data = self.response_generator.format_response_data(results, template)

                    content_parts = []
                    if formatted_data.get("message"):
                        content_parts.append(formatted_data["message"])

                    if formatted_data.get("summary"):
                        content_parts.append(formatted_data["summary"])
                    elif formatted_data.get("table") and formatted_data["table"].get("rows"):
                        table_data = formatted_data["table"]
                        columns = table_data["columns"]
                        rows = table_data["rows"][:10]

                        table_text = " | ".join(columns) + "\n"
                        table_text += "-" * len(table_text) + "\n"
                        for row in rows:
                            table_text += " | ".join(str(v) for v in row) + "\n"

                        content_parts.append(f"Found {formatted_data['result_count']} results:\n{table_text}")

                    if not content_parts:
                        content_parts.append(f"Query executed successfully. Found {len(results)} results.")

                    return [{
                        "content": "\n\n".join(content_parts),
                        "metadata": {
                            "source": "intent_http",
                            "template_id": template.get('id'),
                            "query_intent": template.get('description', ''),
                            "parameters_used": parameters,
                            "formatted_data": formatted_data,
                            "similarity": similarity,
                            "result_count": len(results),
                            "domain_aware": True
                        },
                        "confidence": similarity
                    }]
                else:
                    formatted_results = self._format_http_results(
                        results, template, parameters, similarity)
                    if formatted_results:
                        return formatted_results

            return [{
                "content": "I found potential matches but couldn't extract the required information.",
                "metadata": {"source": "intent_http", "error": "parameter_extraction_failed"},
                "confidence": 0.0
            }]

        except Exception as e:
            logger.error(f"Error in intent-based retrieval: {e}")
            logger.error(traceback.format_exc())
            return [{
                "content": f"An error occurred while processing your query: {e}",
                "metadata": {"source": "intent_http", "error": str(e)},
                "confidence": 0.0
            }]

    async def _find_best_templates(self, query: str) -> List[Dict[str, Any]]:
        """Find best matching templates for the query."""
        try:
            if not self.template_store:
                logger.warning("Template store not available, cannot perform similarity search")
                return []

            if self.verbose:
                try:
                    stats = await self.template_store.get_statistics()
                    total_templates = stats.get('total_templates', 0)
                    logger.info(f"Template store contains {total_templates} templates")
                except Exception as e:
                    logger.debug(f"Could not get template store stats: {e}")

            query_embedding = await self.embedding_client.embed_query(query)
            if not query_embedding:
                logger.error("Failed to get query embedding")
                return []

            if self.verbose:
                logger.info(f"Query embedding generated with {len(query_embedding)} dimensions")

            search_results = await self.template_store.search_similar_templates(
                query_embedding=query_embedding,
                limit=self.max_templates,
                threshold=self.confidence_threshold
            )

            if self.verbose:
                if search_results:
                    scores = [f"{result.get('score', 0):.3f}" for result in search_results]
                    logger.info(f"Found {len(search_results)} results with scores: [{', '.join(scores)}]")
                else:
                    logger.info("Similarity search returned 0 results")

            if not search_results:
                return []

            templates = []
            for result in search_results:
                template_id = result.get('template_id')
                template = self.domain_adapter.get_template_by_id(template_id)
                if template:
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
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parameters = json.loads(json_match.group())

            for param in required_params:
                if (param['name'] not in parameters or
                    parameters[param['name']] is None) and 'default' in param:
                    parameters[param['name']] = param['default']

            if self.verbose:
                logger.info(f"Extracted parameters: {parameters}")

            return parameters

        except Exception as e:
            logger.error(f"Error extracting parameters: {e}")
            return {}

    @abstractmethod
    async def _execute_template(self, template: Dict[str, Any],
                               parameters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """
        Execute HTTP template with parameters.

        Subclasses must implement this to handle their specific HTTP request format.
        """
        pass

    @abstractmethod
    def _format_http_results(self, results: Any, template: Dict,
                            parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """
        Format HTTP results into context documents.

        Subclasses must implement this to format their specific response format.
        """
        pass

    async def _execute_http_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """
        Execute HTTP request using the configured client.

        This is a helper method that can be used by subclasses.
        """
        try:
            response = await self.http_client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            raise

    async def set_collection(self, collection_name: str) -> None:
        """
        Set the current collection/index for HTTP queries.

        Args:
            collection_name: Name of the collection/index to use
        """
        if not collection_name:
            raise ValueError("Collection name cannot be empty")
        self.collection = collection_name
        if self.verbose:
            logger.info(f"{self.__class__.__name__} switched to collection: {collection_name}")

    async def close(self) -> None:
        """Close all connections and services."""
        try:
            # Close HTTP client
            if self.http_client:
                await self.http_client.aclose()

            # Close embedding client
            if self.embedding_client:
                await self.embedding_client.close()

            # Close inference client
            if self.inference_client:
                await self.inference_client.close()

        except Exception as e:
            logger.error(f"Error closing {self.__class__.__name__}: {e}")
