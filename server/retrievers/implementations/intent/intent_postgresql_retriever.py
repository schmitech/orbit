"""
Intent-based PostgreSQL retriever that translates natural language queries to SQL
"""

import logging
import traceback
import chromadb
from chromadb.config import Settings
import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import os
import yaml

from ..relational.postgresql_retriever import PostgreSQLRetriever
from ...base.base_retriever import RetrieverFactory
from ...adapters.intent.intent_adapter import IntentAdapter
from .domain_aware_extractor import DomainAwareParameterExtractor
from .domain_aware_response_generator import DomainAwareResponseGenerator
from .template_reranker import TemplateReranker
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class IntentPostgreSQLRetriever(PostgreSQLRetriever):
    """
    Intent-based PostgreSQL retriever that acts as a meta-retriever.
    
    This retriever translates natural language queries into SQL queries by:
    1. Finding the best matching SQL template using semantic search
    2. Extracting parameters from the user query using LLM
    3. Building and executing the final SQL query
    4. Formatting the results
    """
    
    def __init__(self, 
                config: Dict[str, Any],
                domain_adapter=None,
                connection: Any = None,
                **kwargs):
        """
        Initialize Intent PostgreSQL retriever.
        
        Args:
            config: Configuration dictionary containing intent-specific settings
            domain_adapter: Optional domain adapter (will create IntentAdapter if not provided)
            connection: Optional PostgreSQL connection
            **kwargs: Additional arguments
        """
        # Get intent-specific configuration
        intent_config = config.get('config', {})
        
        # Create IntentAdapter if not provided
        if not domain_adapter:
            domain_adapter = IntentAdapter(
                domain_config_path=intent_config.get('domain_config_path'),
                template_library_path=intent_config.get('template_library_path'),
                confidence_threshold=intent_config.get('confidence_threshold', 0.75),
                verbose=config.get('verbose', False),
                config=intent_config
            )
        
        # Call parent constructor
        super().__init__(config=config, connection=connection, domain_adapter=domain_adapter, **kwargs)
        
        # Intent-specific settings
        self.template_collection_name = intent_config.get('template_collection_name', 'intent_query_templates')
        self.confidence_threshold = intent_config.get('confidence_threshold', 0.75)
        self.max_templates = intent_config.get('max_templates', 5)
        
        # Initialize service clients (will be set up in initialize)
        self.embedding_client = None
        self.inference_client = None
        self.chroma_client = None
        self.template_collection = None
        
        # Initialize domain-aware components
        self.parameter_extractor = None
        self.response_generator = None
        self.template_reranker = None
        
        # Cache for domain configuration
        self._domain_config = None
        self._template_library = None
        
        logger.info(f"IntentPostgreSQLRetriever initialized with template_collection={self.template_collection_name}")
    
    async def initialize(self) -> None:
        """Initialize intent-specific features and load templates."""
        try:
            logger.info(f"Initializing Intent PostgreSQL retriever for domain-based queries")
            
            # Initialize PostgreSQL connection first if not provided
            if not self.connection:
                logger.info("Creating PostgreSQL connection for intent retriever")
                self.connection = self._create_postgres_connection()
            
            # Initialize embedding client with fallback support
            # Check datasource config first, then fall back to global config
            embedding_provider = self.datasource_config.get('embedding_provider')
            
            # If datasource embedding_provider is None or not set, use global config
            if not embedding_provider or embedding_provider == 'null':
                embedding_provider = self.config.get('embedding', {}).get('provider')
                logger.info(f"Using global embedding provider: {embedding_provider}")
            else:
                logger.info(f"Using datasource-specific embedding provider: {embedding_provider}")
            
            from embeddings.base import EmbeddingServiceFactory
            
            # Try to initialize the preferred embedding provider
            try:
                if embedding_provider:
                    self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, embedding_provider)
                else:
                    # Let factory use default from config
                    self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config)
                
                # Initialize the embedding client
                await self.embedding_client.initialize()
                logger.info(f"Successfully initialized {embedding_provider} embedding provider")
                
            except Exception as e:
                logger.warning(f"Failed to initialize {embedding_provider} embedding provider: {str(e)}")
                logger.info("Falling back to Ollama embedding provider")
                
                # Fallback to Ollama which is more likely to be available locally
                try:
                    self.embedding_client = EmbeddingServiceFactory.create_embedding_service(self.config, 'ollama')
                    await self.embedding_client.initialize()
                    logger.info("Successfully initialized Ollama fallback embedding provider")
                except Exception as fallback_error:
                    logger.error(f"Failed to initialize fallback embedding provider: {str(fallback_error)}")
                    raise Exception("Unable to initialize any embedding provider. Please check your configuration.")
            
            # Initialize inference client
            from inference.pipeline.providers.provider_factory import ProviderFactory
            self.inference_client = ProviderFactory.create_provider(self.config)
            await self.inference_client.initialize()
            
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
                logger.info("Intent retriever initialization complete")
                
        except Exception as e:
            logger.error(f"Failed to initialize Intent PostgreSQL retriever: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_postgres_connection(self):
        """Create PostgreSQL connection using datasource configuration."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            import os
            
            # Get PostgreSQL configuration
            postgres_conf = self.datasource_config
            
            # Extract connection parameters with environment variable fallback
            def get_config_value(key, default):
                """Get config value with environment variable fallback"""
                value = postgres_conf.get(key, default)
                
                # If the value looks like an environment variable placeholder, resolve it
                if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                    env_var_name = value[2:-1]
                    env_value = os.environ.get(env_var_name)
                    if env_value is not None:
                        return env_value
                    else:
                        logger.warning(f"Environment variable {env_var_name} not found, using default: {default}")
                        return default
                
                return value
            
            # Extract connection parameters with proper environment variable resolution
            host = get_config_value('host', 'localhost')
            port = get_config_value('port', 5432)
            database = get_config_value('database', 'postgres')
            username = get_config_value('username', 'postgres')
            password = get_config_value('password', '')
            sslmode = get_config_value('sslmode', 'prefer')
            
            # Convert port to int if it's a string
            if isinstance(port, str):
                try:
                    port = int(port)
                except ValueError:
                    logger.warning(f"Invalid port value '{port}', using default port 5432")
                    port = 5432
            
            if self.verbose:
                logger.info(f"Connecting to PostgreSQL: {host}:{port}/{database} (user: {username})")
                logger.debug(f"PostgreSQL config from datasource: {postgres_conf}")
            
            # Create connection
            connection = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=username,
                password=password,
                sslmode=sslmode,
                cursor_factory=RealDictCursor  # Use dict cursor for easier result handling
            )
            
            # Test the connection
            cursor = connection.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()
            cursor.close()
            
            if version and self.verbose:
                logger.info(f"PostgreSQL connection successful: {version['version']}")
            
            return connection
            
        except ImportError:
            logger.error("psycopg2 not available. Install with: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL database: {str(e)}")
            logger.error(f"Connection details: {host}:{port}/{database} (user: {username})")
            raise
    
    def _initialize_chromadb(self):
        """Initialize ChromaDB for template storage."""
        try:
            # Get ChromaDB settings from config
            intent_config = self.config.get('config', {})
            chroma_persist = intent_config.get('chroma_persist', False)
            chroma_persist_path = intent_config.get('chroma_persist_path', './chroma_db')
            
            if chroma_persist:
                # Create persistent ChromaDB client
                self.chroma_client = chromadb.PersistentClient(
                    path=chroma_persist_path,
                    settings=Settings(anonymized_telemetry=False)
                )
                logger.info(f"Initialized persistent ChromaDB at: {chroma_persist_path}")
            else:
                # Create in-memory ChromaDB client
                self.chroma_client = chromadb.Client(Settings(
                    is_persistent=False,
                    anonymized_telemetry=False
                ))
                logger.info("Initialized in-memory ChromaDB")
            
            # Create or get collection for templates
            self.template_collection = self.chroma_client.get_or_create_collection(
                name=self.template_collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info(f"Initialized ChromaDB collection: {self.template_collection_name}")
            
        except Exception as e:
            logger.error(f"Error initializing ChromaDB: {str(e)}")
            raise
    
    async def _load_templates(self):
        """Load SQL templates from the adapter into ChromaDB."""
        try:
            # Check if we already have templates loaded (for persistent storage)
            intent_config = self.config.get('config', {})
            chroma_persist = intent_config.get('chroma_persist', False)
            force_reload = intent_config.get('force_reload_templates', False)
            
            if chroma_persist and not force_reload:
                # Check if templates are already loaded
                existing_count = self.template_collection.count()
                if existing_count > 0:
                    logger.info(f"Found {existing_count} existing templates in persistent ChromaDB")
                    if not intent_config.get('reload_templates_on_start', True):
                        logger.info("Skipping template reload (reload_templates_on_start=False)")
                        return
            
            # Get templates from adapter
            templates = self.domain_adapter.get_all_templates()
            
            if self.verbose:
                logger.info(f"Domain adapter returned {len(templates) if templates else 0} templates")
                if templates and len(templates) > 0:
                    logger.info(f"First template ID: {templates[0].get('id', 'no-id')}")
            
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
                # Handle case where template might be a string or other type
                if not isinstance(template, dict):
                    logger.warning(f"Skipping template of type {type(template)}: {template}")
                    continue
                    
                template_id = template.get('id')
                if not template_id:
                    logger.warning(f"Skipping template without ID: {template}")
                    continue
                
                # Create embedding text from template
                embedding_text = self._create_embedding_text(template)
                
                try:
                    # Get embedding
                    embedding = await self.embedding_client.embed_query(embedding_text)
                    
                    if embedding:
                        ids.append(template_id)
                        embeddings.append(embedding)
                        documents.append(embedding_text)
                        metadatas.append(self._create_template_metadata(template))
                except Exception as e:
                    logger.error(f"Failed to get embedding for template {template_id}: {str(e)}")
                    # Continue with next template instead of failing completely
                    continue
            
            # Add to ChromaDB
            if ids:
                self.template_collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Successfully loaded {len(ids)} templates into ChromaDB")
            else:
                logger.warning("No valid templates found to load into ChromaDB")
            
        except Exception as e:
            logger.error(f"Error loading templates: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _create_embedding_text(self, template: Dict[str, Any]) -> str:
        """Create text for embedding from template."""
        parts = [
            template.get('description', ''),
            ' '.join(template.get('nl_examples', [])),
            ' '.join(template.get('tags', []))
        ]
        
        # Add parameter names
        param_names = [p['name'].replace('_', ' ') for p in template.get('parameters', [])]
        parts.extend(param_names)
        
        # Add semantic tags if available
        if 'semantic_tags' in template:
            tags = template['semantic_tags']
            parts.append(tags.get('action', ''))
            primary_entity = tags.get('primary_entity', '')
            parts.append(primary_entity)
            if tags.get('secondary_entity'):
                parts.append(tags['secondary_entity'])
            parts.extend(tags.get('qualifiers', []))

            # Add entity synonyms from domain vocabulary
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
        
        # Add semantic tags if available
        if 'semantic_tags' in template:
            for key, value in template['semantic_tags'].items():
                metadata[f'semantic_{key}'] = str(value)
        
        return metadata

    def _dump_results_to_file(self, results: List[Dict[str, Any]]):
        """Dump query results to a timestamped JSON file."""
        try:
            from datetime import datetime
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = log_dir / f"query_results_{timestamp}.json"
            
            with open(file_path, 'w') as f:
                json.dump(results, f, indent=2)
            
            logger.info(f"Query results saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to dump query results to file: {e}")

    def _convert_row_types(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert PostgreSQL types to standard Python types."""
        from decimal import Decimal
        from datetime import datetime, date
        
        converted = {}
        for key, value in row.items():
            if isinstance(value, Decimal):
                converted[key] = float(value)
            elif isinstance(value, (datetime, date)):
                converted[key] = value.isoformat()
            else:
                converted[key] = value
        return converted

    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Execute a SQL query and return a list of dictionaries.
        This method overrides the parent's implementation to correctly handle RealDictCursor.
        """
        if not self.connection:
            raise Exception("PostgreSQL connection is not initialized.")
        
        cursor = None
        try:
            # Use a new cursor for each execution for thread safety
            cursor = self.connection.cursor()
            
            logger.info(f"Executing PostgreSQL query: {query}")
            logger.info(f"Parameters: {params}")
            
            cursor.execute(query, params)
            
            if query.strip().upper().startswith("SELECT"):
                results = cursor.fetchall()
                # RealDictCursor returns a list of dict-like objects.
                # We convert them to standard dicts and handle special data types.
                converted_results = [self._convert_row_types(dict(row)) for row in results]
                if self.verbose:
                    # Dump to file instead of logging
                    self._dump_results_to_file(converted_results)
                return converted_results
            else:
                # For non-SELECT queries, commit and return affected row count
                self.connection.commit()
                return [{"affected_rows": cursor.rowcount}]
                
        except Exception as e:
            logger.error(f"Error executing PostgreSQL query: {e}")
            logger.error(f"SQL: {query}, Params: {params}")
            if self.connection:
                self.connection.rollback()
            # Re-raise the exception to be handled by the caller
            raise
        finally:
            if cursor:
                cursor.close()
    
    async def get_relevant_context(self, 
                                 query: str, 
                                 api_key: Optional[str] = None,
                                 collection_name: Optional[str] = None,
                                 **kwargs) -> List[Dict[str, Any]]:
        """
        Process a natural language query using intent-based SQL translation.
        
        Args:
            query: The user's natural language query
            api_key: Optional API key
            collection_name: Optional collection name (not used for intent-based queries)
            **kwargs: Additional parameters
            
        Returns:
            List of formatted result documents
        """
        try:
            if self.verbose:
                logger.info(f"Processing intent query: {query}")
            
            # Step 1: Find best matching template
            templates = await self._find_best_templates(query)
            
            if not templates:
                logger.warning("No matching templates found")
                return [{
                    "content": "I couldn't find a matching query pattern for your request.",
                    "metadata": {
                        "source": "intent",
                        "error": "no_matching_template"
                    },
                    "confidence": 0.0
                }]
            
            # Step 2: Rerank templates using domain-specific rules
            if self.template_reranker:
                templates = self.template_reranker.rerank_templates(templates, query)
                if self.verbose:
                    logger.info("Templates reranked using domain-specific rules")
            
            # Step 3: Try templates in order of relevance
            for template_info in templates:
                template = template_info['template']
                similarity = template_info['similarity']
                
                if similarity < self.confidence_threshold:
                    continue
                
                if self.verbose:
                    logger.info(f"Trying template: {template.get('id')} (similarity: {similarity:.2%})")
                
                # Step 4: Extract parameters using domain-aware extractor
                if self.parameter_extractor:
                    parameters = await self.parameter_extractor.extract_parameters(query, template)
                    # Validate parameters
                    is_valid, validation_errors = self.parameter_extractor.validate_parameters(parameters, template)
                    if not is_valid:
                        logger.warning(f"Parameter validation failed: {validation_errors}")
                        continue
                else:
                    parameters = await self._extract_parameters(query, template)
                
                # Step 5: Build and execute SQL
                results, error = await self._execute_template(template, parameters)
                
                if error:
                    logger.warning(f"Template execution failed: {error}")
                    continue
                
                # Step 6: Generate domain-aware response
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
                    # Fallback to basic formatting
                    formatted_results = self._format_sql_results(results, template, parameters, similarity)
                
                if formatted_results:
                    return formatted_results
            
            # No template worked
            return [{
                "content": "I found potential matches but couldn't extract the required information from your query.",
                "metadata": {
                    "source": "intent",
                    "error": "parameter_extraction_failed"
                },
                "confidence": 0.0
            }]
            
        except Exception as e:
            logger.error(f"Error in intent-based retrieval: {str(e)}")
            logger.error(traceback.format_exc())
            return [{
                "content": f"An error occurred while processing your query: {str(e)}",
                "metadata": {
                    "source": "intent",
                    "error": str(e)
                },
                "confidence": 0.0
            }]
    
    async def _find_best_templates(self, query: str) -> List[Dict[str, Any]]:
        """Find best matching templates for the query."""
        try:
            # Get query embedding
            try:
                query_embedding = await self.embedding_client.embed_query(query)
            except Exception as e:
                logger.error(f"Failed to get query embedding: {str(e)}")
                logger.warning("Falling back to simple text matching")
                # Fall back to simple text matching if embedding fails
                return self._fallback_template_matching(query)
            
            if not query_embedding:
                logger.error("Failed to get query embedding")
                return self._fallback_template_matching(query)
            
            # Search in ChromaDB
            results = self.template_collection.query(
                query_embeddings=[query_embedding],
                n_results=self.max_templates,
                include=['metadatas', 'distances', 'documents']
            )
            
            if not results['ids'] or not results['ids'][0]:
                return []
            
            # Convert results to template format
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
            logger.error(f"Error finding templates: {str(e)}")
            return []
    
    def _fallback_template_matching(self, query: str) -> List[Dict[str, Any]]:
        """Fallback template matching using simple text similarity when embeddings fail."""
        try:
            query_lower = query.lower()
            templates = self.domain_adapter.get_all_templates()
            matches = []
            
            for template in templates:
                if not isinstance(template, dict):
                    continue
                    
                score = 0.0
                # Check nl_examples
                for example in template.get('nl_examples', []):
                    if self._calculate_simple_similarity(query_lower, example.lower()) > 0.5:
                        score = max(score, 0.7)
                
                # Check description
                description = template.get('description', '')
                if description and self._calculate_simple_similarity(query_lower, description.lower()) > 0.5:
                    score = max(score, 0.6)
                
                # Check tags
                tags = ' '.join(template.get('tags', []))
                if tags and self._calculate_simple_similarity(query_lower, tags.lower()) > 0.3:
                    score = max(score, 0.5)
                
                if score > 0:
                    matches.append({
                        'template': template,
                        'similarity': score,
                        'embedding_text': self._create_embedding_text(template)
                    })
            
            # Sort by score and return top matches
            matches.sort(key=lambda x: x['similarity'], reverse=True)
            return matches[:self.max_templates]
            
        except Exception as e:
            logger.error(f"Error in fallback template matching: {str(e)}")
            return []
    
    def _calculate_simple_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity based on word overlap."""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    async def _extract_parameters(self, query: str, template: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from the query using LLM."""
        try:
            parameters = {}
            required_params = template.get('parameters', [])
            
            if not required_params:
                return parameters
            
            # Build parameter extraction prompt
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
            
            # Get LLM response
            response = await self.inference_client.generate(extraction_prompt)
            
            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parameters = json.loads(json_match.group())
                
            # Apply defaults for missing parameters
            for param in required_params:
                if param['name'] not in parameters and 'default' in param:
                    parameters[param['name']] = param['default']
            
            if self.verbose:
                logger.info(f"Extracted parameters: {parameters}")
            
            return parameters
            
        except Exception as e:
            logger.error(f"Error extracting parameters: {str(e)}")
            return {}
    
    async def _execute_template(self, template: Dict[str, Any], parameters: Dict[str, Any]) -> Tuple[List[Dict], Optional[str]]:
        """Execute SQL template with parameters."""
        try:
            # Get SQL template
            sql_template = template.get('sql_template', template.get('sql', ''))
            
            if not sql_template:
                return [], "Template has no SQL query"
            
            # FIX: Add wildcards for LIKE queries with name parameters
            formatted_parameters = parameters.copy()
            for param_name, param_value in formatted_parameters.items():
                if param_value and isinstance(param_value, str) and 'name' in param_name.lower() and 'LIKE' in sql_template.upper():
                    # Clean the parameter value by stripping whitespace and quotes
                    cleaned_value = param_value.strip().strip('"').strip("'")
                    # Add wildcards for LIKE queries to enable partial matching
                    formatted_parameters[param_name] = f"%{cleaned_value}%"
                    if self.verbose:
                        logger.info(f"Added wildcards to parameter {param_name}: '{param_value}' -> '{formatted_parameters[param_name]}'")
            
            # Process the SQL template with parameters
            sql_query = self._process_sql_template(sql_template, formatted_parameters)
            
            if self.verbose:
                logger.info(f"Executing SQL: {sql_query}")
            
            # Log template information
            template_id = template.get('id', 'unknown')
            template_description = template.get('description', 'no description')
            logger.info(f"Using template: {template_id} - {template_description}")
            
            # Execute query using parent class method with formatted parameters
            results = await self.execute_query(sql_query, formatted_parameters)
            
            return results, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error executing template: {error_msg}")
            return [], error_msg
    
    def _process_sql_template(self, sql_template: str, parameters: Dict[str, Any]) -> str:
        """Process SQL template with parameter substitution."""
        try:
            # Simple template processing for conditional blocks
            import re
            
            # Process {% if param_name %} blocks
            def replace_if_block(match):
                param_name = match.group(1).strip()
                content = match.group(2)
                
                # Check if parameter exists and has a truthy value
                if param_name in parameters and parameters[param_name] is not None:
                    return content
                else:
                    return ""
            
            # Pattern to match {% if param_name %}content{% endif %}
            pattern = r'{% *if +([^%]+) *%}(.*?){% *endif *%}'
            processed_sql = re.sub(pattern, replace_if_block, sql_template, flags=re.DOTALL)
            
            return processed_sql.strip()
            
        except Exception as e:
            logger.warning(f"Error processing SQL template: {e}, using original")
            return sql_template
    
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
            logger.info(f"Intent retriever switched to collection (table): {collection_name}")
            
        # For intent retrieval, we don't need to verify actual database tables
        # since we work with SQL templates that will be executed by the target system
        # If a connection is available, we can optionally verify the table exists
        if self.connection:
            try:
                cursor = self.connection.cursor()
                cursor.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = %s
                """, (collection_name,))
                
                if not cursor.fetchone():
                    # For intent retrieval, this might not be an error
                    # The table might exist in the target system that executes the SQL
                    logger.warning(f"Table '{collection_name}' not found in current database connection")
                else:
                    if self.verbose:
                        logger.info(f"Verified table '{collection_name}' exists in database")
                        
            except Exception as e:
                logger.warning(f"Could not verify table existence: {str(e)} (this may be normal for intent retrieval)")
        else:
            if self.verbose:
                logger.info(f"No database connection available - collection '{collection_name}' set for template-based queries")
    
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
        
        # Use domain adapter to format the results
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


# Register the intent retriever with the factory
RetrieverFactory.register_retriever('intent', IntentPostgreSQLRetriever)