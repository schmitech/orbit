"""
Unified Intent SQL Retriever base class that combines intent functionality
with database-specific implementations to reduce duplication.
"""

import logging
import traceback
import chromadb
from chromadb.config import Settings
from typing import Dict, Any, List, Optional, Tuple
from abc import abstractmethod

from .base_sql_database import BaseSQLDatabaseRetriever
from server.retrievers.adapters.intent.intent_adapter import IntentAdapter
from server.retrievers.implementations.intent.domain_aware_extractor import DomainAwareParameterExtractor
from server.retrievers.implementations.intent.domain_aware_response_generator import DomainAwareResponseGenerator
from server.retrievers.implementations.intent.template_reranker import TemplateReranker

logger = logging.getLogger(__name__)


class IntentSQLRetriever(BaseSQLDatabaseRetriever):
    """
    Unified base class for intent-based SQL retrievers.
    Combines intent functionality with database operations.
    """
    
    def __init__(self, config: Dict[str, Any], domain_adapter=None, connection: Any = None, **kwargs):
        """
        Initialize Intent SQL retriever.
        
        Args:
            config: Configuration dictionary
            domain_adapter: Optional domain adapter
            connection: Optional database connection
            **kwargs: Additional arguments
        """
        super().__init__(config=config, connection=connection, **kwargs)
        
        # Get intent-specific configuration
        self.intent_config = config.get('config', {})
        
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
        self.confidence_threshold = self.intent_config.get('confidence_threshold', 0.75)
        self.max_templates = self.intent_config.get('max_templates', 5)
        
        # Initialize service clients
        self.embedding_client = None
        self.inference_client = None
        self.chroma_client = None
        self.template_collection = None
        
        # Domain-aware components
        self.parameter_extractor = None
        self.response_generator = None
        self.template_reranker = None
    
    async def initialize(self) -> None:
        """Initialize intent-specific features and database connection."""
        try:
            logger.info(f"Initializing {self.__class__.__name__} for intent-based queries")
            
            # Initialize database connection using parent method
            if not self.connection:
                self.connection = await self.create_connection()
            
            # Initialize embedding client
            await self._initialize_embedding_client()
            
            # Initialize inference client
            await self._initialize_inference_client()
            
            # Initialize ChromaDB for template storage
            self._initialize_chromadb()
            
            # Load templates into ChromaDB
            await self._load_templates()
            
            # Initialize domain-aware components
            domain_config = self.domain_adapter.get_domain_config()
            self.parameter_extractor = DomainAwareParameterExtractor(self.inference_client, domain_config)
            self.response_generator = DomainAwareResponseGenerator(self.inference_client, domain_config)
            self.template_reranker = TemplateReranker(domain_config)
            
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
            
            await self.embedding_client.initialize()
            logger.info(f"Successfully initialized {embedding_provider} embedding provider")
            
        except Exception as e:
            logger.warning(f"Failed to initialize {embedding_provider}: {e}")
            logger.info("Falling back to Ollama embedding provider")
            
            try:
                self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, 'ollama')
                await self.embedding_client.initialize()
                logger.info("Successfully initialized Ollama fallback embedding provider")
            except Exception as fallback_error:
                logger.error(f"Failed to initialize fallback embedding provider: {fallback_error}")
                raise Exception("Unable to initialize any embedding provider")
    
    async def _initialize_inference_client(self):
        """Initialize inference client."""
        from inference.pipeline.providers.provider_factory import ProviderFactory
        self.inference_client = ProviderFactory.create_provider(self.config)
        await self.inference_client.initialize()
    
    def _initialize_chromadb(self):
        """Initialize ChromaDB for template storage."""
        try:
            chroma_persist = self.intent_config.get('chroma_persist', False)
            chroma_persist_path = self.intent_config.get('chroma_persist_path', './chroma_db')
            
            if chroma_persist:
                self.chroma_client = chromadb.PersistentClient(
                    path=chroma_persist_path,
                    settings=Settings(anonymized_telemetry=False)
                )
                logger.info(f"Initialized persistent ChromaDB at: {chroma_persist_path}")
            else:
                self.chroma_client = chromadb.Client(Settings(
                    is_persistent=False,
                    anonymized_telemetry=False
                ))
                logger.info("Initialized in-memory ChromaDB")
            
            self.template_collection = self.chroma_client.get_or_create_collection(
                name=self.template_collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"Initialized ChromaDB collection: {self.template_collection_name}")
            
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {e}")
            raise
    
    async def _load_templates(self):
        """Load SQL templates from the adapter into ChromaDB."""
        try:
            chroma_persist = self.intent_config.get('chroma_persist', False)
            force_reload = self.intent_config.get('force_reload_templates', False)
            
            if chroma_persist and not force_reload:
                existing_count = self.template_collection.count()
                if existing_count > 0:
                    logger.info(f"Found {existing_count} existing templates in persistent ChromaDB")
                    if not self.intent_config.get('reload_templates_on_start', True):
                        logger.info("Skipping template reload")
                        return
            
            templates = self.domain_adapter.get_all_templates()
            
            if not templates:
                logger.warning("No templates found in template library")
                return
            
            logger.info(f"Loading {len(templates)} templates into ChromaDB")
            
            # Clear existing templates
            try:
                all_ids = self.template_collection.get()['ids']
                if all_ids:
                    self.template_collection.delete(ids=all_ids)
                    logger.info(f"Cleared {len(all_ids)} existing templates")
            except:
                pass
            
            # Prepare data for ChromaDB
            ids = []
            embeddings = []
            documents = []
            metadatas = []
            
            for template in templates:
                if not isinstance(template, dict):
                    continue
                    
                template_id = template.get('id')
                if not template_id:
                    continue
                
                embedding_text = self._create_embedding_text(template)
                
                try:
                    embedding = await self.embedding_client.embed_query(embedding_text)
                    
                    if embedding:
                        ids.append(template_id)
                        embeddings.append(embedding)
                        documents.append(embedding_text)
                        metadatas.append(self._create_template_metadata(template))
                except Exception as e:
                    logger.error(f"Failed to get embedding for template {template_id}: {e}")
                    continue
            
            if ids:
                self.template_collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Successfully loaded {len(ids)} templates into ChromaDB")
            
        except Exception as e:
            logger.error(f"Error loading templates: {e}")
            logger.error(traceback.format_exc())
    
    def _create_embedding_text(self, template: Dict[str, Any]) -> str:
        """Create text for embedding from template."""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
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
                    is_valid, validation_errors = self.parameter_extractor.validate_parameters(parameters, template)
                    if not is_valid:
                        logger.warning(f"Parameter validation failed: {validation_errors}")
                        continue
                else:
                    parameters = await self._extract_parameters(query, template)
                
                # Execute template
                results, error = await self._execute_template(template, parameters)
                
                if error:
                    logger.warning(f"Template execution failed: {error}")
                    continue
                
                # Generate response
                if self.response_generator:
                    response = await self.response_generator.generate_response(
                        query, results, template, error=None
                    )
                    
                    return [{
                        "content": response,
                        "metadata": {
                            "source": "intent",
                            "template_id": template.get('id'),
                            "query_intent": template.get('description', ''),
                            "parameters_used": parameters,
                            "results": results,
                            "similarity": similarity,
                            "result_count": len(results),
                            "domain_aware": True
                        },
                        "confidence": similarity
                    }]
                else:
                    formatted_results = self._format_sql_results(results, template, parameters, similarity)
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
            query_embedding = await self.embedding_client.embed_query(query)
            
            if not query_embedding:
                logger.error("Failed to get query embedding")
                return []
            
            results = self.template_collection.query(
                query_embeddings=[query_embedding],
                n_results=self.max_templates,
                include=['metadatas', 'distances', 'documents']
            )
            
            if not results['ids'] or not results['ids'][0]:
                return []
            
            templates = []
            for i, template_id in enumerate(results['ids'][0]):
                template = self.domain_adapter.get_template_by_id(template_id)
                if template:
                    similarity = 1 - results['distances'][0][i]
                    templates.append({
                        'template': template,
                        'similarity': similarity,
                        'embedding_text': results['documents'][0][i]
                    })
            
            return templates
            
        except Exception as e:
            logger.error(f"Error finding templates: {e}")
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
                if param['name'] not in parameters and 'default' in param:
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
            
            results = await self.execute_query(sql_query, formatted_parameters)
            
            return results, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing template: {error_msg}")
            return [], error_msg
    
    def _process_sql_template(self, sql_template: str, parameters: Dict[str, Any]) -> str:
        """Process SQL template with parameter substitution."""
        try:
            import re
            
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
    
    def _format_sql_results(self, results: List[Dict], template: Dict, parameters: Dict, similarity: float) -> List[Dict[str, Any]]:
        """Format SQL results into context documents."""
        if not results:
            return [{
                "content": "No results found for your query.",
                "metadata": {
                    "source": "intent",
                    "template_id": template.get('id'),
                    "parameters_used": parameters,
                    "similarity": similarity,
                    "result_count": 0
                },
                "confidence": similarity
            }]
        
        import json
        formatted_doc = self.domain_adapter.format_document(
            raw_doc=json.dumps(results, default=str),
            metadata={
                "source": "intent",
                "template_id": template.get('id'),
                "query_intent": template.get('description', ''),
                "parameters_used": parameters,
                "results": results,
                "similarity": similarity,
                "result_count": len(results)
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
        """Close all connections and services."""
        try:
            # Close database connection
            await super().close()
            
            # Close embedding client
            if self.embedding_client:
                await self.embedding_client.close()
            
            # Close inference client
            if self.inference_client:
                await self.inference_client.close()
                
        except Exception as e:
            logger.error(f"Error closing {self.__class__.__name__}: {e}")