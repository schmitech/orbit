"""
Open Inference Server
==================

A modular FastAPI server that provides a chat endpoint with Ollama LLM integration
and Chroma vector database for retrieval augmented generation.

This implementation follows object-oriented principles to create a maintainable
and well-structured application.

Usage:
    python main.py

Features:
    - Chat endpoint with context-aware responses
    - Health check endpoint
    - ChromaDB integration for document retrieval
    - Ollama integration for embeddings and LLM responses
    - Safety check for user queries using GuardrailService
    - HTTPS support using provided certificates
    - API key management
    - MCP protocol compatibility for universal client support
"""

import os
import ssl
import logging
import logging.handlers
import json
import asyncio
import time
import uuid
from typing import Dict, Any, Optional, List, Callable, Awaitable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import chromadb
from langchain_ollama import OllamaEmbeddings
from dotenv import load_dotenv
from pythonjsonlogger import jsonlogger
from bson import ObjectId

# Load environment variables
load_dotenv()

# Import local modules (ensure these exist in your project structure)
from config.config_manager import load_config, _is_true_value
from models.schema import ChatMessage, ApiKeyCreate, ApiKeyResponse, ApiKeyDeactivate, SystemPromptCreate, SystemPromptUpdate, SystemPromptResponse, ApiKeyPromptAssociate
from models.schema import MCPJsonRpcRequest, MCPJsonRpcResponse, MCPJsonRpcError
from models import ChatMessage
from services import ChatService, LoggerService, GuardrailService, RerankerService, ApiKeyService, PromptService
from services.mongodb_service import MongoDBService
from inference import LLMClientFactory
from utils.text_utils import mask_api_key
from embeddings.base import EmbeddingServiceFactory
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.adapters.registry import ADAPTER_REGISTRY
from utils.mongodb_utils import configure_mongodb_logging

# Configure MongoDB logging
configure_mongodb_logging()

class InferenceServer:
    """
    A modular inference server built with FastAPI that provides chat endpoints
    with LLM integration and vector database retrieval capabilities.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the InferenceServer with optional custom configuration path.
        
        Args:
            config_path: Optional path to a custom configuration file
        """
        # Initialize basic logging until proper configuration is loaded
        self._setup_initial_logging()
        
        # Load configuration
        self.config = load_config(config_path)
        
        # Configure proper logging with loaded configuration
        self._setup_logging()
        
        # Thread pool for blocking I/O operations
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        # Initialize FastAPI app with lifespan manager
        self.app = FastAPI(
            title="Open Inference Server",
            description="A FastAPI server with chat endpoint and RAG capabilities",
            version="1.0.0",
            lifespan=self._create_lifespan_manager()
        )
        
        # Initialize application state
        self.services = {}
        self.clients = {}
        
        # Configure middleware and routes
        self._configure_middleware()
        self._configure_routes()
        
        self.logger.info("InferenceServer initialized")

    def _setup_initial_logging(self) -> None:
        """Set up basic logging configuration before loading the full config."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        )
        self.logger = logging.getLogger(__name__)
        
        # Set specific logger levels for more detailed debugging
        logging.getLogger('clients.ollama_client').setLevel(logging.DEBUG)

    def _setup_logging(self) -> None:
        """Configure logging based on the application configuration."""
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        
        # Create logs directory if it doesn't exist
        log_dir = log_config.get('file', {}).get('directory', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Create formatters
        json_formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
        text_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Configure console logging
        if _is_true_value(log_config.get('console', {}).get('enabled', True)):
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(
                json_formatter if log_config.get('console', {}).get('format') == 'json' else text_formatter
            )
            console_handler.setLevel(log_level)
            root_logger.addHandler(console_handler)
        
        # Configure file logging
        if _is_true_value(log_config.get('file', {}).get('enabled', True)):
            file_config = log_config['file']
            log_file = os.path.join(log_dir, file_config.get('filename', 'server.log'))
            
            # Set up rotating file handler
            if file_config.get('rotation') == 'midnight':
                file_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=log_file,
                    when='midnight',
                    interval=1,
                    backupCount=file_config.get('backup_count', 30),
                    encoding='utf-8'
                )
            else:
                file_handler = logging.handlers.RotatingFileHandler(
                    filename=log_file,
                    maxBytes=file_config.get('max_size_mb', 10) * 1024 * 1024,
                    backupCount=file_config.get('backup_count', 30),
                    encoding='utf-8'
                )
            
            file_handler.setFormatter(
                json_formatter if file_config.get('format') == 'json' else text_formatter
            )
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        
        # Capture warnings if configured
        if _is_true_value(log_config.get('capture_warnings', True)):
            logging.captureWarnings(True)
        
        # Set propagation
        root_logger.propagate = log_config.get('propagate', False)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Logging configuration completed")
        
        # Handle verbose setting consistently
        verbose_value = self.config.get('general', {}).get('verbose', False)
        if _is_true_value(verbose_value):
            self.logger.debug("Verbose logging enabled")

    def _create_lifespan_manager(self):
        """
        Create an asynccontextmanager for the FastAPI application lifespan.
        This manages initialization and cleanup of resources.
        
        Returns:
            An asynccontextmanager function for the FastAPI app
        """
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            self.logger.info("Starting up FastAPI application")
            
            # Initialize services and clients
            try:
                await self._initialize_services(app)
                self._log_configuration_summary()
                self.logger.info("Startup complete")
            except Exception as e:
                self.logger.error(f"Failed to initialize services: {str(e)}")
                raise
            
            yield
            
            # Cleanup resources
            try:
                self.logger.info("Shutting down services...")
                await self._shutdown_services(app)
                self.logger.info("Services shut down successfully")
            except Exception as e:
                self.logger.error(f"Error during shutdown: {str(e)}")
        
        return lifespan

    def _resolve_datasource_embedding_provider(self, datasource_name: str) -> str:
        """
        Resolve embedding provider for a specific datasource.
        This implements the inheritance with override capability.
        
        Args:
            datasource_name: The name of the datasource ('chroma', 'milvus', etc.)
            
        Returns:
            The embedding provider name to use for this datasource
        """
        # Get the main embedding provider from embedding settings
        main_provider = self.config['embedding'].get('provider', 'ollama')
        
        # Check if there's a provider override for this datasource
        datasource_config = self.config.get('datasources', {}).get(datasource_name, {})
        provider_override = datasource_config.get('embedding_provider')
        
        # If there's a valid override, use it; otherwise inherit from main provider
        if provider_override and provider_override in self.config.get('embeddings', {}):
            provider = provider_override
            self.logger.info(f"{datasource_name.capitalize()} uses custom embedding provider: {provider}")
        else:
            provider = main_provider
            self.logger.info(f"{datasource_name.capitalize()} inherits embedding provider from embedding config: {provider}")
        
        return provider
    
    def _resolve_provider_configs(self) -> None:
        """
        Resolve provider configurations and ensure backward compatibility.
        This method maps the selected providers to the legacy config structure
        to minimize changes to existing code.
        """
        # Get selected providers
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        datasource_provider = self.config['general'].get('datasource_provider', 'chroma')
        embedding_provider = self.config['embedding'].get('provider', 'ollama')
        
        # Resolve providers for safety and reranker components
        safety_provider = self._resolve_component_provider('safety')
        reranker_provider = self._resolve_component_provider('reranker')
        
        # Resolve models for safety and reranker
        safety_model = self._resolve_component_model('safety', safety_provider)
        reranker_model = self._resolve_component_model('reranker', reranker_provider)
        
        # Update safety and reranker configurations with resolved values
        if 'safety' in self.config:
            self.config['safety']['resolved_provider'] = safety_provider
            self.config['safety']['resolved_model'] = safety_model
        
        if 'reranker' in self.config:
            self.config['reranker']['resolved_provider'] = reranker_provider
            self.config['reranker']['resolved_model'] = reranker_model
        
        # # For backward compatibility, copy selected inference provider config to the old location
        # if inference_provider in self.config.get('inference', {}):
        #     self.config['ollama'] = self.config['inference'][inference_provider]
        
        # # For backward compatibility, copy selected datasource provider config to the old location
        # if datasource_provider in self.config.get('datasources', {}):
        #     self.config['chroma'] = self.config['datasources'][datasource_provider]
        
        # Handle mongodb settings for backward compatibility
        if 'internal_services' in self.config and 'mongodb' in self.config['internal_services']:
            self.config['mongodb'] = self.config['internal_services']['mongodb']
        
        # Handle elasticsearch settings for backward compatibility
        if 'internal_services' in self.config and 'elasticsearch' in self.config['internal_services']:
            self.config['elasticsearch'] = self.config['internal_services']['elasticsearch']
        
        self.logger.info(f"Using inference provider: {inference_provider}")
        self.logger.info(f"Using datasource provider: {datasource_provider}")
        self.logger.info(f"Using embedding provider: {embedding_provider}")
        self.logger.info(f"Using safety provider: {safety_provider}")
        self.logger.info(f"Using reranker provider: {reranker_provider}")
    
    def _resolve_component_provider(self, component_name: str) -> str:
        """
        Resolve the provider for a specific component (safety, reranker).
        This implements the inheritance with override capability.
        
        Args:
            component_name: The name of the component ('safety' or 'reranker')
            
        Returns:
            The provider name to use for this component
        """
        # Get the main inference provider from general settings
        main_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Check if there's a component-specific override
        component_config = self.config.get(component_name, {})
        
        # For safety component, check for 'moderator'
        if component_name == 'safety':
            moderator = component_config.get('moderator')
            if moderator:
                self.logger.info(f"{component_name.capitalize()} uses moderator: {moderator}")
                return moderator
        else:
            # For reranker, continue using provider_override
            provider_override = component_config.get('provider_override')
            if provider_override and provider_override in self.config.get('inference', {}):
                self.logger.info(f"{component_name.capitalize()} uses custom provider: {provider_override}")
                return provider_override
        
        # If no override found, inherit from main provider
        self.logger.info(f"{component_name.capitalize()} inherits provider from general: {main_provider}")
        return main_provider

    def _resolve_component_model(self, component_name: str, provider: str) -> str:
        """
        Resolve the model for a specific component (safety, reranker).
        Handles model specification and suffix addition.
        
        Args:
            component_name: The name of the component ('safety' or 'reranker')
            provider: The provider name for this component
            
        Returns:
            The model name to use for this component
        """
        component_config = self.config.get(component_name, {})
        
        # Get the base model from the provider configuration
        provider_model = self.config['inference'].get(provider, {}).get('model', '')
        
        # Check if the component has its own model specified
        component_model = component_config.get('model')
        
        # Check if there's a model suffix to add
        model_suffix = component_config.get('model_suffix')
        
        # Determine the final model name
        if component_model:
            # Component has its own model specification
            model = component_model
        else:
            # Inherit from provider's model
            model = provider_model
        
        # Add suffix if specified
        if model_suffix and model:
            model = f"{model}{model_suffix}"
        
        self.logger.info(f"{component_name.capitalize()} using model: {model}")
        return model

    def _initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client
        """
        if provider == 'sqlite':
            # SQLite implementation
            import sqlite3
            sqlite_config = self.config['datasources']['sqlite']
            db_path = sqlite_config.get('db_path', '../utils/sqllite/rag_database.db')
            self.logger.info(f"Initializing SQLite connection to {db_path}")
            try:
                # Return a SQLite connection
                return sqlite3.connect(db_path)
            except Exception as e:
                self.logger.error(f"Failed to connect to SQLite database: {str(e)}")
                return None
        elif provider == 'postgres':
            # Example implementation for PostgreSQL
            postgres_conf = self.config['datasources']['postgres']
            # Return a PostgreSQL client implementation
            self.logger.info(f"PostgreSQL datasource not yet implemented")
            return None
        elif provider == 'milvus':
            # Example implementation for Milvus
            milvus_conf = self.config['datasources']['milvus']
            # Return a Milvus client implementation
            self.logger.info(f"Milvus datasource not yet implemented")
            return None
        else:
            self.logger.warning(f"Unknown datasource provider: {provider}, falling back to ChromaDB")
            # Default to ChromaDB
            chroma_conf = self.config['datasources']['chroma']
            use_local = chroma_conf.get('use_local', False)
            
            if use_local:
                # Use PersistentClient for local filesystem access
                import os
                from pathlib import Path
                
                db_path = chroma_conf.get('db_path', '../localdb_db')
                db_path = Path(db_path).resolve()
                
                # Ensure the directory exists
                os.makedirs(db_path, exist_ok=True)
                
                self.logger.info(f"Using local ChromaDB at path: {db_path}")
                return chromadb.PersistentClient(path=str(db_path))
            else:
                # Use HttpClient for remote server access
                self.logger.info(f"Connecting to ChromaDB at {chroma_conf['host']}:{chroma_conf['port']}...")
                return chromadb.HttpClient(
                    host=chroma_conf['host'],
                    port=int(chroma_conf['port'])
                )
    
    async def _initialize_services(self, app: FastAPI) -> None:
        """
        Initialize all services and clients required by the application.
        
        Args:
            app: The FastAPI application to attach services to
        """
        # Store config in app state
        app.state.config = self.config
        
        # Resolve provider configurations
        self._resolve_provider_configs()
        
        # Initialize shared MongoDB service
        app.state.mongodb_service = MongoDBService(self.config)
        self.logger.info("Initializing shared MongoDB service...")
        try:
            await app.state.mongodb_service.initialize()
            self.logger.info("Shared MongoDB service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize shared MongoDB service: {str(e)}")
            raise
        
        # Initialize API Key Service with shared MongoDB service
        app.state.api_key_service = ApiKeyService(self.config, app.state.mongodb_service)
        self.logger.info("Initializing API Key Service...")
        try:
            await app.state.api_key_service.initialize()
            self.logger.info("API Key Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize API Key Service: {str(e)}")
            raise
        
        # Initialize Prompt Service with shared MongoDB service
        app.state.prompt_service = PromptService(self.config, app.state.mongodb_service)
        self.logger.info("Initializing Prompt Service...")
        try:
            await app.state.prompt_service.initialize()
            self.logger.info("Prompt Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Prompt Service: {str(e)}")
            raise
        
        # Set up lazy loading for datasource client
        datasource_provider = self.config['general'].get('datasource_provider', 'chroma')
        self.logger.info(f"Setting up lazy loading for {datasource_provider} datasource client")
        
        # Import LazyLoader utility
        from utils.lazy_loader import LazyLoader
        
        if datasource_provider == 'chroma':
            # Create a factory function for ChromaDB client
            def create_chroma_client():
                chroma_conf = self.config['datasources']['chroma']
                use_local = chroma_conf.get('use_local', False)
                
                if use_local:
                    # Use PersistentClient for local filesystem access
                    import os
                    from pathlib import Path
                    
                    db_path = chroma_conf.get('db_path', '../utils/chroma/chroma_db')
                    db_path = Path(db_path).resolve()
                    
                    # Ensure the directory exists
                    os.makedirs(db_path, exist_ok=True)
                    
                    self.logger.info(f"Initializing local ChromaDB at path: {db_path}")
                    return chromadb.PersistentClient(path=str(db_path))
                else:
                    # Use HttpClient for remote server access
                    self.logger.info(f"Connecting to ChromaDB at {chroma_conf['host']}:{chroma_conf['port']}...")
                    return chromadb.HttpClient(
                        host=chroma_conf['host'],
                        port=int(chroma_conf['port'])
                    )
            
            # Create a lazy loader for ChromaDB
            app.state.chroma_client_loader = LazyLoader(create_chroma_client, "ChromaDB client")
            
            # Create a proxy class that lazily loads the client
            class LazyChromaClient:
                def __getattr__(self, name):
                    client = app.state.chroma_client_loader.get_instance()
                    return getattr(client, name)
            
            app.state.chroma_client = LazyChromaClient()
        else:
            # Create a factory function for the selected datasource client
            def create_datasource_client():
                self.logger.info(f"Initializing {datasource_provider} datasource client...")
                return self._initialize_datasource_client(datasource_provider)
            
            # Create a lazy loader for the datasource client
            app.state.datasource_client_loader = LazyLoader(create_datasource_client, f"{datasource_provider} client")
            
            # Create a proxy class that lazily loads the client
            class LazyDatasourceClient:
                def __getattr__(self, name):
                    client = app.state.datasource_client_loader.get_instance()
                    return getattr(client, name)
            
            app.state.datasource_client = LazyDatasourceClient()
        
        # Check if embedding services are enabled
        embedding_enabled = _is_true_value(self.config['embedding'].get('enabled', True))
        
        if embedding_enabled:
            # Determine embedding provider for the datasource
            embedding_provider = self._resolve_datasource_embedding_provider(datasource_provider)
            self.logger.info(f"Using {embedding_provider} for embeddings with {datasource_provider}")
            
            # Initialize embedding service
            try:
                app.state.embedding_service = EmbeddingServiceFactory.create_embedding_service(
                    self.config,
                    provider_name=embedding_provider
                )
                
                # Initialize the embedding service
                self.logger.info(f"Initializing {embedding_provider} embedding service...")
                if not await app.state.embedding_service.initialize():
                    self.logger.error(f"Failed to initialize {embedding_provider} embedding service")
                    raise Exception(f"Failed to initialize {embedding_provider} embedding service")
                
                # Verify embedding service works by testing a simple query
                self.logger.info("Testing embedding service with a sample query...")
                test_embedding = await app.state.embedding_service.embed_query("test query")
                if not test_embedding or len(test_embedding) == 0:
                    self.logger.error(f"Embedding service returned empty embedding for test query")
                    raise Exception(f"Embedding service test failed - empty embedding returned")
                else:
                    self.logger.info(f"Embedding service test succeeded: generated {len(test_embedding)} dimensional embedding")
            except Exception as e:
                self.logger.error(f"Error initializing embedding service: {str(e)}")
                if self.config['embedding'].get('fail_on_error', False):
                    raise
                self.logger.warning("Continuing without embeddings service due to initialization error")
                app.state.embedding_service = None
        else:
            # Skip embedding initialization
            self.logger.info("Embedding services disabled in configuration")
            app.state.embedding_service = None
        
        # Set up lazy-loaded retriever for the configured datasource provider
        try:
            # Get the adapter configuration
            adapter_configs = self.config.get('adapters', [])
            if not adapter_configs:
                raise ValueError("No adapter configurations found in config")
            
            # Get the configured adapter name from general settings
            configured_adapter_name = self.config['general'].get('adapter', '')
            if not configured_adapter_name:
                raise ValueError("No adapter specified in general.adapter")
            
            # Find the matching adapter configuration by name
            retriever_config = next(
                (cfg for cfg in adapter_configs 
                 if cfg.get('name') == configured_adapter_name),
                None
            )
            
            if not retriever_config:
                raise ValueError(f"No matching adapter configuration found for {configured_adapter_name}")
            
            # Extract adapter details
            implementation = retriever_config.get('implementation')
            datasource = retriever_config.get('datasource')
            adapter_type = retriever_config.get('adapter')
            
            if not implementation or not datasource or not adapter_type:
                raise ValueError("Missing required adapter fields (implementation, datasource, or adapter)")
            
            self.logger.info(f"Setting up lazy loading for {datasource} retriever with {adapter_type} adapter")
            
            # Register a factory function for lazy loading the specified retriever
            def create_configured_retriever():
                """Factory function to create the properly configured retriever when needed"""
                # Import the specific retriever class
                try:
                    module_path, class_name = implementation.rsplit('.', 1)
                    module = __import__(module_path, fromlist=[class_name])
                    retriever_class = getattr(module, class_name)
                except (ImportError, AttributeError) as e:
                    self.logger.error(f"Could not load retriever class from {implementation}: {str(e)}")
                    raise ValueError(f"Failed to load retriever implementation: {str(e)}")
                
                # Create the domain adapter using the registry
                try:
                    # Create adapter using registry with the full config
                    adapter_config = retriever_config.get('config', {})
                    domain_adapter = ADAPTER_REGISTRY.create(
                        adapter_type='retriever',
                        datasource=datasource,
                        adapter_name=adapter_type,
                        **adapter_config  # Pass config values as kwargs
                    )
                    self.logger.info(f"Successfully created {adapter_type} domain adapter with config: {adapter_config}")
                except Exception as adapter_error:
                    self.logger.error(f"Error creating domain adapter: {str(adapter_error)}")
                    raise ValueError(f"Failed to create domain adapter: {str(adapter_error)}")
                
                # Prepare appropriate arguments based on the provider type
                retriever_kwargs = {
                    'config': self.config, 
                    'domain_adapter': domain_adapter
                }
                
                # Add appropriate client/connection based on the provider type
                if datasource == 'chroma':
                    retriever_kwargs['embeddings'] = app.state.embedding_service
                    if hasattr(app.state, 'chroma_client'):
                        retriever_kwargs['collection'] = app.state.chroma_client
                elif datasource == 'sqlite':
                    if hasattr(app.state, 'datasource_client'):
                        retriever_kwargs['connection'] = app.state.datasource_client
                
                # Create and return the retriever instance
                self.logger.info(f"Creating {datasource} retriever instance")
                return retriever_class(**retriever_kwargs)
            
            # Register the factory function with the RetrieverFactory
            RetrieverFactory.register_lazy_retriever(datasource, create_configured_retriever)
            
            # Create a lazy retriever accessor for the app state
            class LazyRetrieverAccessor:
                def __init__(self, retriever_type):
                    self.retriever_type = retriever_type
                    self._retriever = None
                
                def __getattr__(self, name):
                    # Initialize the retriever on first access
                    if self._retriever is None:
                        self._retriever = RetrieverFactory.create_retriever(self.retriever_type)
                    # Delegate attribute access to the actual retriever
                    return getattr(self._retriever, name)
            
            # Set the lazy retriever accessor in app state
            app.state.retriever = LazyRetrieverAccessor(datasource)
            self.logger.info(f"Successfully set up lazy loading for {datasource} retriever")
            
        except Exception as e:
            self.logger.error(f"Error setting up lazy loading for retriever: {str(e)}")
            self.logger.warning("Will attempt to initialize default retriever on first request")
            
            # Create a simple lazy factory that will attempt to create a fallback retriever on first access
            def create_fallback_retriever():
                try:
                    from retrievers.implementations.chroma import ChromaRetriever
                    
                    # Create a default QA adapter
                    domain_adapter = ADAPTER_REGISTRY.create(
                        adapter_type='qa',
                        config=self.config
                    )
                    
                    return ChromaRetriever(
                        config=self.config,
                        embeddings=app.state.embedding_service,
                        domain_adapter=domain_adapter
                    )
                except Exception as fallback_error:
                    self.logger.error(f"Failed to initialize fallback retriever: {str(fallback_error)}")
                    raise
            
            # Register the fallback retriever factory
            RetrieverFactory.register_lazy_retriever('fallback', create_fallback_retriever)
            
            # Create a lazy accessor that uses the fallback retriever
            class FallbackRetrieverAccessor:
                def __init__(self):
                    self._retriever = None
                
                def __getattr__(self, name):
                    if self._retriever is None:
                        self._retriever = RetrieverFactory.create_retriever('fallback')
                    return getattr(self._retriever, name)
            
            app.state.retriever = FallbackRetrieverAccessor()
        
        # Initialize GuardrailService only if safety is enabled
        if _is_true_value(self.config.get('safety', {}).get('enabled', False)):
            app.state.guardrail_service = GuardrailService(self.config)
            self.logger.info("Initializing GuardrailService...")
            try:
                await app.state.guardrail_service.initialize()
                self.logger.info("GuardrailService initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize GuardrailService: {str(e)}")
                raise
        else:
            app.state.guardrail_service = None
            self.logger.info("Safety is disabled, skipping GuardrailService initialization")
        
        # Load no results message
        no_results_message = self._load_no_results_message()
        
        # Initialize reranker service if enabled
        if _is_true_value(self.config.get('reranker', {}).get('enabled', False)):
            app.state.reranker_service = RerankerService(self.config)
        else:
            app.state.reranker_service = None
        
        # Create LLM client using the factory
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Use a lazy-loading proxy for the retriever to ensure it's only initialized when needed
        class LazyRetrieverProxy:
            def __init__(self, retriever_accessor):
                self.retriever_accessor = retriever_accessor
            
            def __getattr__(self, name):
                # This will trigger the lazy loading in the accessor when needed
                return getattr(self.retriever_accessor, name)
        
        app.state.llm_client = LLMClientFactory.create_llm_client(
            self.config, 
            LazyRetrieverProxy(app.state.retriever),  # Wrap in proxy to ensure lazy loading
            guardrail_service=app.state.guardrail_service,
            reranker_service=app.state.reranker_service,
            prompt_service=app.state.prompt_service,
            no_results_message=no_results_message
        )
        
        app.state.logger_service = LoggerService(self.config)

        # Log datasource domain adapter settings
        datasource_provider = self.config['general'].get('datasource_provider', 'chroma')
        datasource_config = self.config.get('datasources', {}).get(datasource_provider, {})
        domain_adapter = datasource_config.get('domain_adapter', 'qa')
        adapter_params = datasource_config.get('adapter_params', {})

        self.logger.info(f"  {datasource_provider.capitalize()} Retriever: " +
                    f"domain_adapter={domain_adapter}, " +
                    f"confidence_threshold={datasource_config.get('confidence_threshold', 0.85)}")

        if adapter_params:
            adapter_params_str = ", ".join([f"{k}={v}" for k, v in adapter_params.items()])
            self.logger.info(f"  Adapter params: {adapter_params_str}")
        
        # Initialize all services concurrently
        init_tasks = [
            app.state.llm_client.initialize(),
            app.state.logger_service.initialize_elasticsearch()
        ]
        
        # Only add guardrail service initialization if it exists
        if app.state.guardrail_service is not None:
            init_tasks.append(app.state.guardrail_service.initialize())
        
        # The retriever will be initialized on first access with lazy loading
        # No need to initialize it here
        
        # Only initialize reranker if enabled
        if app.state.reranker_service:
            init_tasks.append(app.state.reranker_service.initialize())
        
        await asyncio.gather(*init_tasks)
        
        # Verify LLM connection
        if not await app.state.llm_client.verify_connection():
            self.logger.error(f"Failed to connect to {inference_provider}. Exiting...")
            raise Exception(f"Failed to connect to {inference_provider}")
        
        # Initialize remaining services
        app.state.chat_service = ChatService(self.config, app.state.llm_client, app.state.logger_service)

    def _load_no_results_message(self) -> str:
        """
        Get the no results message from the configuration.
        
        Returns:
            The message to show when no results are found
        """
        return self.config.get('messages', {}).get('no_results_response', 
            "I'm sorry, but I don't have any specific information about that topic in my knowledge base.")

    async def _shutdown_services(self, app: FastAPI) -> None:
        """
        Shut down all services and clients.
        
        Args:
            app: The FastAPI application containing services
        """
        self.logger.info("Shutting down services...")
        
        # Create a list to collect shutdown tasks
        shutdown_tasks = []
        
        # Helper function to safely add shutdown task
        def add_shutdown_task(service, service_name):
            if service is not None and hasattr(service, 'close'):
                try:
                    if asyncio.iscoroutinefunction(service.close):
                        shutdown_tasks.append(service.close())
                    else:
                        service.close()
                except Exception as e:
                    self.logger.error(f"Error preparing shutdown for {service_name}: {str(e)}")
        
        # Add services to shutdown tasks if they exist and have close methods
        if hasattr(app.state, 'llm_client'):
            add_shutdown_task(app.state.llm_client, 'LLM Client')
        
        if hasattr(app.state, 'logger_service'):
            add_shutdown_task(app.state.logger_service, 'Logger Service')
        
        # Handle lazy-loaded retriever closure
        if hasattr(app.state, 'retriever'):
            if hasattr(app.state.retriever, '_retriever') and app.state.retriever._retriever is not None:
                add_shutdown_task(app.state.retriever._retriever, 'Retriever')
            else:
                self.logger.info("Retriever was never initialized, no need to close")
        
        if hasattr(app.state, 'guardrail_service'):
            add_shutdown_task(app.state.guardrail_service, 'Guardrail Service')
        
        if hasattr(app.state, 'prompt_service'):
            # PromptService doesn't have a close method, so we skip it
            self.logger.info("Skipping PromptService shutdown (no close method)")
        
        if hasattr(app.state, 'reranker_service'):
            add_shutdown_task(app.state.reranker_service, 'Reranker Service')
        
        if hasattr(app.state, 'api_key_service'):
            add_shutdown_task(app.state.api_key_service, 'API Key Service')
        
        if hasattr(app.state, 'embedding_service'):
            add_shutdown_task(app.state.embedding_service, 'Embedding Service')
            
        # Close shared MongoDB service
        if hasattr(app.state, 'mongodb_service'):
            add_shutdown_task(app.state.mongodb_service, 'MongoDB Service')
        
        # Only run asyncio.gather if there are tasks to gather
        if shutdown_tasks:
            try:
                # Wait for all shutdown tasks to complete with a timeout
                await asyncio.wait_for(asyncio.gather(*shutdown_tasks, return_exceptions=True), timeout=30.0)
                self.logger.info("Services shut down successfully")
            except asyncio.TimeoutError:
                self.logger.error("Timeout while shutting down services")
            except Exception as e:
                self.logger.error(f"Error during shutdown of services: {str(e)}")
        else:
            self.logger.info("No services to shut down")

    def _log_configuration_summary(self) -> None:
        """Log a summary of the server configuration."""
        self.logger.info("=" * 50)
        self.logger.info("Server Configuration Summary")
        self.logger.info("=" * 50)
        
        # Get selected providers
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Get embedding configuration
        embedding_config = self.config.get('embedding', {})
        embedding_enabled = _is_true_value(embedding_config.get('enabled', True))
        embedding_provider = embedding_config.get('provider', 'ollama')
        
        # Get safety configuration
        safety_config = self.config.get('safety', {})
        safety_enabled = _is_true_value(safety_config.get('enabled', True))
        safety_moderator = safety_config.get('moderator', 'ollama')
        safety_mode = safety_config.get('mode', 'strict')
        
        # Get session ID configuration
        session_config = self.config.get('general', {}).get('session_id', {})
        session_enabled = _is_true_value(session_config.get('enabled', False))
        session_header = session_config.get('header_name', 'X-Session-ID')
        
        # Get API key configuration
        api_key_config = self.config.get('api_keys', {})
        api_key_enabled = _is_true_value(api_key_config.get('enabled', True))
        api_key_header = api_key_config.get('header_name', 'X-API-Key')
        require_for_health = _is_true_value(api_key_config.get('require_for_health', False))
        
        self.logger.info(f"Inference provider: {inference_provider}")
        self.logger.info(f"Embedding: {'enabled' if embedding_enabled else 'disabled'}")
        self.logger.info(f"Session ID: {'enabled' if session_enabled else 'disabled'} (header: {session_header})")
        self.logger.info(f"API Key: {'enabled' if api_key_enabled else 'disabled'} (header: {api_key_header}, required for health: {require_for_health})")
        
        # Log safety information
        self.logger.info(f"Safety: {'enabled' if safety_enabled else 'disabled'}")
        if safety_enabled:
            self.logger.info(f"Safety moderator: {safety_moderator}")
            self.logger.info(f"Safety mode: {safety_mode}")
            
            # Log moderator-specific information if available
            if safety_moderator in self.config.get('moderators', {}):
                moderator_config = self.config['moderators'][safety_moderator]
                model = moderator_config.get('model', 'unknown')
                self.logger.info(f"Moderation model: {model}")
        
        if embedding_enabled:
            self.logger.info(f"Embedding provider: {embedding_provider}")
            # Log embedding model information
            if embedding_provider in self.config.get('embeddings', {}):
                embed_model = self.config['embeddings'][embedding_provider].get('model', 'unknown')
                self.logger.info(f"Embedding model: {embed_model}")
        
        # Log model information based on the selected inference provider
        if inference_provider in self.config.get('inference', {}):
            model_name = self.config['inference'][inference_provider].get('model', 'unknown')
            self.logger.info(f"Server running with {model_name} model")
        
        # Log datasource configuration
        if hasattr(self.app.state, 'retriever'):
            self.logger.info(f"Confidence threshold: {self.app.state.retriever.confidence_threshold}")
        
        self.logger.info(f"Verbose mode: {_is_true_value(self.config['general'].get('verbose', False))}")
        
        # Log API endpoints
        self.logger.info("API Endpoints:")
        self.logger.info("  - MCP protocol: POST /v1/chat")
        self.logger.info("  - Health check: GET /health")

    def _configure_middleware(self) -> None:
        """Configure middleware for the FastAPI application."""
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Allows all origins
            allow_credentials=True,
            allow_methods=["*"],  # Allows all methods
            allow_headers=["*"],  # Allows all headers
        )

    def _configure_routes(self) -> None:
        """Configure routes and endpoints for the FastAPI application."""
        # Define dependencies
        async def get_chat_service(request: Request):
            return request.app.state.chat_service

        async def get_health_service(request: Request):
            return request.app.state.health_service

        async def get_guardrail_service(request: Request):
            return request.app.state.guardrail_service

        async def get_api_key_service(request: Request):
            return request.app.state.api_key_service

        async def get_prompt_service(request: Request):
            return request.app.state.prompt_service

        async def validate_session_id(request: Request) -> str:
            """
            Validate the session ID from the request header.
            Requires clients to provide their own session ID if session_id.enabled is true.
            
            Args:
                request: The incoming request
                
            Returns:
                The validated session ID or None if session validation is disabled
            
            Raises:
                HTTPException: If session ID is missing or empty when session validation is enabled
            """
            # Check if session ID validation is enabled
            session_enabled = _is_true_value(request.app.state.config.get('general', {}).get('session_id', {}).get('enabled', False))
            
            if not session_enabled:
                # If session validation is disabled, return None
                return None
            
            # Get session ID header name from config
            session_header = request.app.state.config['general']['session_id']['header_name']
            session_id = request.headers.get(session_header)
            
            if not session_id or not session_id.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"Session ID is required. Please provide a non-empty string in the {session_header} header."
                )
            
            return session_id.strip()

        async def get_api_key(
            request: Request,
            api_key_service = Depends(get_api_key_service)
        ) -> tuple[Optional[str], Optional[ObjectId]]:
            """
            Extract API key from request headers and validate it
            
            Args:
                request: The incoming request
                api_key_service: The API key service
                
            Returns:
                Tuple of (collection_name, system_prompt_id) associated with the API key
            """
            # Get API key from header
            header_name = self.config.get('api_keys', {}).get('header_name', 'X-API-Key')
            api_key = request.headers.get(header_name)
            
            # Validate API key and get collection name and system prompt ID
            try:
                collection_name, system_prompt_id = await api_key_service.get_collection_for_api_key(api_key)
                return collection_name, system_prompt_id
            except HTTPException as e:
                # Allow health check without API key if configured
                if (request.url.path == "/health" and 
                    not self.config.get('api_keys', {}).get('require_for_health', False)):
                    return "default", None
                raise e
                
        # MCP protocol endpoint
        @self.app.post("/v1/chat")
        async def mcp_chat_endpoint(
            request: Request,
            chat_service = Depends(get_chat_service),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(get_api_key),
            session_id: str = Depends(validate_session_id)
        ):
            """
            Process an MCP protocol chat request and return a response
            
            This endpoint implements the MCP protocol using JSON-RPC 2.0 format
            with the tools/call method and chat tool.
            """
            collection_name, system_prompt_id = api_key_result
            
            # Extract the API key and client info
            api_key = request.headers.get("X-API-Key")
            masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
            client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
            
            # Enhanced verbose logging
            if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                self.logger.debug("=" * 50)
                self.logger.debug("Incoming MCP Request Details:")
                self.logger.debug(f"Session ID: {session_id}")
                self.logger.debug(f"Client IP: {client_ip}")
                self.logger.debug(f"Collection: {collection_name}")
                self.logger.debug(f"System Prompt ID: {system_prompt_id}")
                self.logger.debug(f"API Key: {masked_api_key}")
                self.logger.debug(f"Request Method: {request.method}")
                self.logger.debug(f"Request URL: {request.url}")
                self.logger.debug("Request Headers:")
                for header, value in request.headers.items():
                    if header.lower() == "x-api-key":
                        self.logger.debug(f"  {header}: {masked_api_key}")
                    else:
                        self.logger.debug(f"  {header}: {value}")
            
            # Get request body
            try:
                body = await request.json()
                if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                    self.logger.debug("Request Body:")
                    self.logger.debug(json.dumps(body, indent=2))
            except Exception as e:
                self.logger.error(f"Failed to parse request body for session {session_id}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid request body: {str(e)}")
            
            # Validate JSON-RPC request format
            if not all(key in body for key in ["jsonrpc", "method", "params", "id"]):
                self.logger.error("Invalid request format: missing required JSON-RPC fields")
                raise HTTPException(status_code=400, detail="Invalid request format: missing required JSON-RPC fields")
            
            try:
                jsonrpc_request = MCPJsonRpcRequest(**body)
                # Enhanced verbose logging for JSON-RPC request
                if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                    self.logger.debug("JSON-RPC Request Details:")
                    self.logger.debug(f"  Method: {jsonrpc_request.method}")
                    self.logger.debug(f"  ID: {jsonrpc_request.id}")
                    self.logger.debug("  Params:")
                    self.logger.debug(json.dumps(jsonrpc_request.params, indent=2))
            except Exception as e:
                self.logger.error(f"Failed to parse JSON-RPC request: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")
            
            try:
                # Handle the tools/call method for chat
                if jsonrpc_request.method == "tools/call":
                    # Validate tool name is "chat"
                    tool_name = jsonrpc_request.params.get("name", "")
                    if tool_name != "chat":
                        if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                            self.logger.debug(f"Unsupported tool requested: {tool_name}")
                        return MCPJsonRpcResponse(
                            jsonrpc="2.0",
                            error={
                                "code": -32601,
                                "message": f"Tool not supported: {tool_name}"
                            },
                            id=jsonrpc_request.id
                        )
                    
                    # Extract arguments
                    arguments = jsonrpc_request.params.get("arguments", {})
                    messages = arguments.get("messages", [])
                    
                    if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                        self.logger.debug("Chat Arguments:")
                        self.logger.debug(f"  Stream: {arguments.get('stream', False)}")
                        self.logger.debug(f"  Message Count: {len(messages)}")
                        self.logger.debug("  Messages:")
                        for msg in messages:
                            self.logger.debug(f"    Role: {msg.get('role')}")
                            self.logger.debug(f"    Content Length: {len(msg.get('content', ''))}")
                    
                    if not messages:
                        self.logger.error("No messages provided in request")
                        return MCPJsonRpcResponse(
                            jsonrpc="2.0",
                            error={
                                "code": -32602,
                                "message": "Invalid params: missing messages"
                            },
                            id=jsonrpc_request.id
                        )
                    
                    # Extract the last user message
                    user_messages = [m for m in messages if m.get("role") == "user"]
                    if not user_messages:
                        self.logger.error("No user message found in request")
                        return MCPJsonRpcResponse(
                            jsonrpc="2.0",
                            error={
                                "code": -32602,
                                "message": "Invalid params: no user message found"
                            },
                            id=jsonrpc_request.id
                        )
                    
                    # Get the last user message content
                    last_user_message = user_messages[-1].get("content", "")
                    
                    if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                        self.logger.debug(f"Processing user message (length: {len(last_user_message)})")
                    
                    # Check for streaming parameter
                    stream = arguments.get("stream", False)
                    
                    if _is_true_value(self.config.get('general', {}).get('verbose', False)):
                        self.logger.debug(f"Streaming mode: {'enabled' if stream else 'disabled'}")

                    # Handle streaming if requested
                    if stream:
                        # Implement streaming response
                        async def stream_generator():
                            try:
                                # Send the first chunk to establish the stream
                                start_response = {
                                    "jsonrpc": "2.0", 
                                    "id": jsonrpc_request.id,
                                    "result": {
                                        "type": "start"
                                    }
                                }
                                yield f'data: {json.dumps(start_response)}\n\n'
                                
                                # Process message in streaming mode
                                buffer = ""
                                async for chunk in chat_service.process_chat_stream(
                                    message=last_user_message,
                                    client_ip=client_ip,
                                    collection_name=collection_name,
                                    system_prompt_id=system_prompt_id,
                                    api_key=api_key
                                ):
                                    # Parse chunk data
                                    try:
                                        if chunk.startswith("data: "):
                                            chunk = chunk[6:].strip()  # Remove "data: " prefix
                                        
                                        chunk_data = json.loads(chunk)
                                        
                                        # Skip done messages
                                        if chunk_data.get("done", False):
                                            continue
                                            
                                        # Extract content
                                        content = chunk_data.get("response", "")
                                        if content:
                                            # Add to buffer
                                            buffer += content
                                            
                                            # Format response as per MCP
                                            chunk_response = {
                                                "jsonrpc": "2.0", 
                                                "id": jsonrpc_request.id,
                                                "result": {
                                                    "name": "chat",
                                                    "type": "chunk",
                                                    "chunk": {
                                                        "content": content,
                                                        "role": "assistant"
                                                    }
                                                }
                                            }
                                            
                                            yield f"data: {json.dumps(chunk_response)}\n\n"
                                    except json.JSONDecodeError:
                                        # If not valid JSON, try to extract text content directly
                                        if chunk:
                                            buffer += chunk
                                            chunk_response = {
                                                "jsonrpc": "2.0", 
                                                "id": jsonrpc_request.id,
                                                "result": {
                                                    "name": "chat",
                                                    "type": "chunk",
                                                    "chunk": {
                                                        "content": chunk,
                                                        "role": "assistant"
                                                    }
                                                }
                                            }
                                            yield f"data: {json.dumps(chunk_response)}\n\n"
                            
                                # Send final message with complete response
                                final_response = {
                                    "jsonrpc": "2.0",
                                    "id": jsonrpc_request.id,
                                    "result": {
                                        "name": "chat",
                                        "type": "complete",
                                        "output": {
                                            "messages": [
                                                {
                                                    "role": "assistant",
                                                    "content": buffer
                                                }
                                            ]
                                        }
                                    }
                                }
                                
                                yield f"data: {json.dumps(final_response)}\n\n"
                                yield f"data: [DONE]\n\n"
                                
                            except Exception as e:
                                self.logger.error(f"Error in MCP streaming: {str(e)}")
                                error_response = {
                                    "jsonrpc": "2.0",
                                    "id": jsonrpc_request.id,
                                    "error": {
                                        "code": -32603,
                                        "message": f"Internal error: {str(e)}"
                                    }
                                }
                                yield f"data: {json.dumps(error_response)}\n\n"
                                yield f"data: [DONE]\n\n"
                        
                        return StreamingResponse(
                            stream_generator(),
                            media_type="text/event-stream"
                        )
                    else:
                        # Process the chat message (non-streaming)
                        result = await chat_service.process_chat(
                            message=last_user_message,
                            client_ip=client_ip,
                            collection_name=collection_name,
                            system_prompt_id=system_prompt_id,
                            api_key=api_key
                        )
                        
                        if "error" in result:
                            return MCPJsonRpcResponse(
                                jsonrpc="2.0",
                                error={
                                    "code": -32603,
                                    "message": result["error"]
                                },
                                id=jsonrpc_request.id
                            )
                        
                        # Format the response as per MCP
                        return MCPJsonRpcResponse(
                            jsonrpc="2.0",
                            result={
                                "name": "chat",
                                "output": {
                                    "messages": [
                                        {
                                            "role": "assistant",
                                            "content": result.get("response", "")
                                        }
                                    ]
                                }
                            },
                            id=jsonrpc_request.id
                        )
                else:
                    # Method not supported
                    return MCPJsonRpcResponse(
                        jsonrpc="2.0",
                        error={
                            "code": -32601,
                            "message": f"Method not found: {jsonrpc_request.method}"
                        },
                        id=jsonrpc_request.id
                    )
                
            except Exception as e:
                self.logger.error(f"Error in MCP endpoint: {str(e)}")
                return MCPJsonRpcResponse(
                    jsonrpc="2.0",
                    error={
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    },
                    id=jsonrpc_request.id
                )

        # API Key management routes
        @self.app.post("/admin/api-keys", response_model=ApiKeyResponse)
        async def create_api_key(
            api_key_data: ApiKeyCreate,
            api_key_service = Depends(get_api_key_service)
        ):
            """
            Create a new API key associated with a specific collection
            
            This is an admin-only endpoint and should be properly secured in production.
            """
            # In production, add authentication middleware to restrict access to admin endpoints
            
            api_key_response = await api_key_service.create_api_key(
                api_key_data.collection_name,
                api_key_data.client_name,
                api_key_data.notes
            )
            
            # Log with masked API key
            masked_api_key = f"***{api_key_response['api_key'][-4:]}" if api_key_response.get('api_key') else "***"
            self.logger.info(f"Created API key for collection '{api_key_data.collection_name}': {masked_api_key}")
            
            return api_key_response

        @self.app.get("/admin/api-keys")
        async def list_api_keys(
            api_key_service = Depends(get_api_key_service)
        ):
            """
            List all API keys
            
            This is an admin-only endpoint and should be properly secured in production.
            """
            # In production, add authentication middleware to restrict access to admin endpoints
            
            try:
                # Ensure service is initialized
                if not api_key_service._initialized:
                    await api_key_service.initialize()
                
                # Retrieve all API keys
                cursor = api_key_service.api_keys_collection.find({})
                api_keys = await cursor.to_list(length=100)  # Limit to 100 keys
                
                # Convert _id to string representation and mask API keys
                for key in api_keys:
                    key["_id"] = str(key["_id"])
                    if "api_key" in key:
                        key["api_key"] = f"***{key['api_key'][-4:]}" if key["api_key"] else "***"
                
                return api_keys
                
            except Exception as e:
                self.logger.error(f"Error listing API keys: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")

        @self.app.get("/admin/api-keys/{api_key}/status")
        async def get_api_key_status(
            api_key: str,
            api_key_service = Depends(get_api_key_service)
        ):
            """
            Get the status of a specific API key
            
            This is an admin-only endpoint and should be properly secured in production.
            """
            status = await api_key_service.get_api_key_status(api_key)
            # Log with masked API key
            masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
            self.logger.info(f"Checked status for API key: {masked_api_key}")
            return status

        @self.app.post("/admin/api-keys/deactivate")
        async def deactivate_api_key(
            data: ApiKeyDeactivate,
            api_key_service = Depends(get_api_key_service)
        ):
            """
            Deactivate an API key
            
            This is an admin-only endpoint and should be properly secured in production.
            """
            # In production, add authentication middleware to restrict access to admin endpoints
            
            success = await api_key_service.deactivate_api_key(data.api_key)
            
            if not success:
                raise HTTPException(status_code=404, detail="API key not found")
            
            # Log with masked API key
            masked_api_key = f"***{data.api_key[-4:]}" if data.api_key else "***"
            self.logger.info(f"Deactivated API key: {masked_api_key}")
                
            return {"status": "success", "message": "API key deactivated"}

        @self.app.delete("/admin/api-keys/{api_key}")
        async def delete_api_key(
            api_key: str,
            api_key_service = Depends(get_api_key_service)
        ):
            """
            Delete an API key
            
            This is an admin-only endpoint and should be properly secured in production.
            """
            # In production, add authentication middleware to restrict access to admin endpoints
            
            success = await api_key_service.delete_api_key(api_key)
            
            if not success:
                raise HTTPException(status_code=404, detail="API key not found")
            
            # Log with masked API key
            masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
            self.logger.info(f"Deleted API key: {masked_api_key}")
                
            return {"status": "success", "message": "API key deleted"}

        # Health check endpoint
        @self.app.get("/health")
        async def health_check(
            health_service = Depends(get_health_service),
            collection_name: str = Depends(get_api_key)
        ):
            """Check the health of the application and its dependencies"""
            health = await health_service.get_health_status(collection_name)
            return health

        # System Prompts management routes
        @self.app.post("/admin/prompts", response_model=SystemPromptResponse)
        async def create_prompt(
            prompt_data: SystemPromptCreate,
            prompt_service = Depends(get_prompt_service)
        ):
            """Create a new system prompt"""
            prompt_id = await prompt_service.create_prompt(
                prompt_data.name,
                prompt_data.prompt,
                prompt_data.version
            )
            
            prompt = await prompt_service.get_prompt_by_id(prompt_id)
            
            if not prompt:
                raise HTTPException(status_code=500, detail="Failed to retrieve created prompt")
                
            # Format the response according to the model
            return {
                "id": str(prompt_id),
                "name": prompt.get("name"),
                "prompt": prompt.get("prompt"),
                "version": prompt.get("version"),
                "created_at": prompt.get("created_at").timestamp() if prompt.get("created_at") else 0,
                "updated_at": prompt.get("updated_at").timestamp() if prompt.get("updated_at") else 0
            }

        @self.app.get("/admin/prompts")
        async def list_prompts(
            prompt_service = Depends(get_prompt_service)
        ):
            """List all system prompts"""
            return await prompt_service.list_prompts()

        @self.app.get("/admin/prompts/{prompt_id}")
        async def get_prompt(
            prompt_id: str,
            prompt_service = Depends(get_prompt_service)
        ):
            """Get a system prompt by ID"""
            prompt = await prompt_service.get_prompt_by_id(prompt_id)
            
            if not prompt:
                raise HTTPException(status_code=404, detail="Prompt not found")
                
            # Convert ObjectId to string and datetime to timestamp
            prompt["_id"] = str(prompt["_id"])
            if "created_at" in prompt:
                prompt["created_at"] = prompt["created_at"].timestamp()
            if "updated_at" in prompt:
                prompt["updated_at"] = prompt["updated_at"].timestamp()
                
            return prompt

        @self.app.put("/admin/prompts/{prompt_id}", response_model=SystemPromptResponse)
        async def update_prompt(
            prompt_id: str,
            prompt_data: SystemPromptUpdate,
            prompt_service = Depends(get_prompt_service)
        ):
            """Update a system prompt"""
            success = await prompt_service.update_prompt(
                prompt_id,
                prompt_data.prompt,
                prompt_data.version
            )
            
            if not success:
                raise HTTPException(status_code=404, detail="Prompt not found or not updated")
                
            prompt = await prompt_service.get_prompt_by_id(prompt_id)
            
            if not prompt:
                raise HTTPException(status_code=404, detail="Failed to retrieve updated prompt")
                
            # Format the response according to the model
            return {
                "id": str(prompt_id),
                "name": prompt.get("name"),
                "prompt": prompt.get("prompt"),
                "version": prompt.get("version"),
                "created_at": prompt.get("created_at").timestamp() if prompt.get("created_at") else 0,
                "updated_at": prompt.get("updated_at").timestamp() if prompt.get("updated_at") else 0
            }

        @self.app.delete("/admin/prompts/{prompt_id}")
        async def delete_prompt(
            prompt_id: str,
            prompt_service = Depends(get_prompt_service)
        ):
            """Delete a system prompt"""
            success = await prompt_service.delete_prompt(prompt_id)
            
            if not success:
                raise HTTPException(status_code=404, detail="Prompt not found")
                
            return {"status": "success", "message": "Prompt deleted"}

        @self.app.post("/admin/api-keys/{api_key}/prompt")
        async def associate_prompt_with_api_key(
            api_key: str,
            data: ApiKeyPromptAssociate,
            api_key_service = Depends(get_api_key_service)
        ):
            """Associate a system prompt with an API key"""
            success = await api_key_service.update_api_key_system_prompt(api_key, data.prompt_id)
            
            if not success:
                raise HTTPException(status_code=404, detail="API key not found or prompt not associated")
            
            return {"status": "success", "message": "System prompt associated with API key"}
    
    def create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """
        Create an SSL context from certificate and key files.
        
        Returns:
            An SSL context if HTTPS is enabled, None otherwise
        """
        if not _is_true_value(self.config.get('general', {}).get('https', {}).get('enabled', False)):
            return None
        
        try:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(
                certfile=self.config['general']['https']['cert_file'],
                keyfile=self.config['general']['https']['key_file']
            )
            return ssl_context
        except Exception as e:
            self.logger.error(f"Failed to create SSL context: {str(e)}")
            raise

    def run(self) -> None:
        """Run the FastAPI application with the configured settings."""
        # Get server settings from config
        port = int(self.config.get('general', {}).get('port', 3000))
        host = self.config.get('general', {}).get('host', '0.0.0.0')

        # Use HTTPS if enabled in config
        https_enabled = _is_true_value(self.config.get('general', {}).get('https', {}).get('enabled', False))
        
        if https_enabled:
            try:
                ssl_keyfile = self.config['general']['https']['key_file']
                ssl_certfile = self.config['general']['https']['cert_file']
                https_port = int(self.config['general']['https'].get('port', 3443))
                
                self.logger.info(f"Starting HTTPS server on {host}:{https_port}")
                
                # Run without reload option - this is handled by the start script
                uvicorn.run(
                    self.app,
                    host=host,
                    port=https_port,
                    ssl_keyfile=ssl_keyfile,
                    ssl_certfile=ssl_certfile
                )
            except Exception as e:
                self.logger.error(f"Failed to start HTTPS server: {str(e)}")
                import sys
                sys.exit(1)
        else:
            self.logger.info(f"Starting HTTP server on {host}:{port}")
            # Run without reload option - this is handled by the start script
            uvicorn.run(
                self.app,
                host=host,
                port=port
            )

# Create a global app instance for direct use by uvicorn in development mode
app = FastAPI(
    title="ORBIT Open Inference Server",
    description="Open source inference server with chat endpoint and RAG capabilities",
    version="1.0.0"
)


# Factory function for creating app instances in multi-worker mode
def create_app() -> FastAPI:
    """
    Factory function to create a FastAPI application instance.
    This is useful for uvicorn's multiple worker mode.
    
    This function looks for a config path in the OIS_CONFIG_PATH environment variable.
    
    Returns:
        A configured FastAPI application
    """
    # Check for config path in environment variables
    config_path = os.environ.get('OIS_CONFIG_PATH')
    
    # Create server instance
    server = InferenceServer(config_path=config_path)
    
    # Return just the FastAPI app instance
    return server.app


# Example of usage directly in this file
if __name__ == "__main__":
    server = InferenceServer()
    server.run()