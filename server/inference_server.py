import os
import ssl
import logging
import logging.handlers
import json
import asyncio
import time
import atexit
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request, Depends, HTTPException, Response
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
from services.mongodb_service import MongoDBService
from inference import LLMClientFactory
from utils.text_utils import mask_api_key
from retrievers.base.base_retriever import RetrieverFactory
from retrievers.adapters.registry import ADAPTER_REGISTRY
from utils.mongodb_utils import configure_mongodb_logging
from services.chat_service import ChatService
from services.chat_history_service import ChatHistoryService
from utils.http_utils import close_all_aiohttp_sessions

class InferenceServer:
    """
    A modular inference server built with FastAPI that provides chat endpoints
    with LLM integration and vector database retrieval capabilities.

    This class serves as the main entry point for the Open Inference Server application.
    It manages the application lifecycle, including initialization, configuration,
    service management, and graceful shutdown.

    Key Responsibilities:
        - Configuration loading and validation
        - Service initialization and management
        - Route configuration and middleware setup
        - API endpoint implementation
        - Resource cleanup and graceful shutdown

    The server supports two main modes:
        1. Full Mode: Includes RAG capabilities with vector database integration
        2. Inference-Only Mode: Basic chat functionality without RAG features

    Service Management:
        - Chat Service: Handles chat interactions and message processing
        - Health Service: Monitors system health and dependencies
        - Guardrail Service: Provides content safety checks
        - API Key Service: Manages API key authentication and access control
        - Prompt Service: Handles system prompts and templates
        - Logger Service: Manages application logging
        - Retriever Service: Handles document retrieval for RAG
        - Reranker Service: Ranks retrieved documents by relevance

    Configuration:
        The server can be configured using a YAML configuration file that specifies:
        - Server settings (host, port, HTTPS)
        - Provider configurations (LLM, embedding, vector database)
        - Service settings (safety, reranker, logging)
        - API settings (key management, session handling)
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the InferenceServer with optional custom configuration path.
        
        This method sets up the basic server infrastructure, including:
        - Basic logging configuration
        - Configuration loading
        - Thread pool for I/O operations
        - FastAPI application initialization
        - Middleware and route configuration
        
        Args:
            config_path: Optional path to a custom configuration file.
                        If not provided, uses default configuration.
        
        Raises:
            FileNotFoundError: If the specified config file doesn't exist
            ValueError: If the configuration is invalid
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
        """
        Set up basic logging configuration before loading the full config.
        
        This method initializes a basic logging configuration that will be used
        until the full configuration is loaded. It ensures that critical startup
        messages are properly logged.
        
        The basic configuration includes:
        - Console output
        - Timestamp formatting
        - Log level set to INFO
        - Basic log format
        
        This is a temporary setup that will be replaced by the full logging
        configuration once the config is loaded.
        """
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        )
        self.logger = logging.getLogger(__name__)
        
        # Set specific logger levels for more detailed debugging
        logging.getLogger('clients.ollama_client').setLevel(logging.DEBUG)

    def _setup_logging(self) -> None:
        """
        Configure logging based on the application configuration.
        
        This method sets up the full logging configuration based on the loaded
        configuration file. It supports:
        - Console and file logging
        - JSON and text formats
        - Log rotation
        - Custom log levels
        - Warning capture
        
        Configuration options include:
        - Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        - Log format (JSON or text)
        - Log file settings (path, rotation, size limits)
        - Console output settings
        - Warning capture settings
        
        The configuration is applied to the root logger and can be overridden
        for specific loggers if needed.
        """
        log_config = self.config.get('logging', {})
        log_level = getattr(logging, log_config.get('level', 'INFO').upper())
        
        # Configure root logger first
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.propagate = False  # Disable propagation immediately
        
        # Clear existing handlers to prevent duplicates
        root_logger.handlers.clear()
        
        # Create formatters based on configuration
        text_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        json_formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
        
        # Configure console logging
        console_enabled = _is_true_value(log_config.get('console', {}).get('enabled', True))
        if console_enabled:
            console_handler = logging.StreamHandler()
            console_format = log_config.get('console', {}).get('format', 'text')
            console_handler.setFormatter(json_formatter if console_format == 'json' else text_formatter)
            console_handler.setLevel(log_level)
            root_logger.addHandler(console_handler)
        
        # Configure file logging
        file_enabled = _is_true_value(log_config.get('file', {}).get('enabled', True))
        if file_enabled:
            file_config = log_config.get('file', {})
            log_dir = file_config.get('directory', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, file_config.get('filename', 'orbit.log'))
            
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
            
            file_format = file_config.get('format', 'text')
            file_handler.setFormatter(json_formatter if file_format == 'json' else text_formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        
        # Configure specific loggers
        if 'loggers' in log_config:
            for logger_name, logger_config in log_config['loggers'].items():
                logger = logging.getLogger(logger_name)
                logger_level = getattr(logging, logger_config.get('level', 'INFO').upper())
                logger.setLevel(logger_level)
                logger.propagate = False  # Disable propagation for all loggers
        
        # Capture warnings if configured
        if _is_true_value(log_config.get('capture_warnings', True)):
            logging.captureWarnings(True)
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("Logging configuration completed")
        
        # Handle verbose setting consistently
        verbose_value = self.config.get('general', {}).get('verbose', False)
        if _is_true_value(verbose_value):
            self.logger.debug("Verbose logging enabled")

    def _create_lifespan_manager(self):
        """
        Create an asynccontextmanager for the FastAPI application lifespan.
        
        This method creates a lifespan manager that handles the initialization and cleanup
        of all server resources. It ensures proper startup and shutdown of services,
        including:
        - Service initialization
        - Configuration validation
        - Resource allocation
        - Graceful shutdown of services
        
        The lifespan manager is used by FastAPI to manage the application lifecycle.
        It runs during server startup and shutdown.
        
        Returns:
            An asynccontextmanager function that handles the FastAPI app lifecycle
        
        Raises:
            Exception: If service initialization fails
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
        
        This method implements a provider resolution system that supports:
        - Inheritance from main embedding provider
        - Datasource-specific overrides
        - Fallback to default provider
        
        The resolution process:
        1. Gets the main embedding provider from config
        2. Checks for datasource-specific override
        3. Validates the provider exists in config
        4. Returns the appropriate provider name
        
        Args:
            datasource_name: The name of the datasource ('chroma', 'milvus', etc.)
            
        Returns:
            The embedding provider name to use for this datasource
            
        Note:
            If the specified provider override is not found in the config,
            the method falls back to the main provider.
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
        
        This method handles the resolution of all provider configurations in the system,
        including:
        - Inference provider (LLM)
        - Embedding provider
        - Datasource provider
        - Safety provider
        - Reranker provider
        
        The resolution process:
        1. Checks for inference-only mode
        2. Resolves each provider configuration
        3. Updates component-specific settings
        4. Handles backward compatibility
        
        The method supports:
        - Provider inheritance
        - Component-specific overrides
        - Model resolution
        - Backward compatibility mapping
        
        Note:
            In inference-only mode, only the inference provider is resolved.
            Other providers are skipped to minimize resource usage.
        """
        # Check if inference_only is enabled
        inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
        
        # Get selected providers
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Only resolve embedding and datasource providers if not in inference_only mode
        if not inference_only:
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
            
            # Handle mongodb settings for backward compatibility
            if 'internal_services' in self.config and 'mongodb' in self.config['internal_services']:
                self.config['mongodb'] = self.config['internal_services']['mongodb']
            
            # Handle elasticsearch settings for backward compatibility
            if 'internal_services' in self.config and 'elasticsearch' in self.config['internal_services']:
                self.config['elasticsearch'] = self.config['internal_services']['elasticsearch']
            
            self.logger.info(f"Using datasource provider: {datasource_provider}")
            self.logger.info(f"Using embedding provider: {embedding_provider}")
            self.logger.info(f"Using safety provider: {safety_provider}")
            self.logger.info(f"Using reranker provider: {reranker_provider}")
        else:
            # In inference_only mode, only log the inference provider
            self.logger.info(f"Using inference provider: {inference_provider}")
    
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
            db_path = sqlite_config.get('db_path', 'sqlite_db.db')
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
        
        This method is responsible for setting up all the services needed by the server,
        including:
        - Configuration resolution and validation
        - Service initialization based on configuration
        - Client setup for external services
        - Lazy loading of optional services
        
        The initialization process is mode-aware:
        - In full mode: Initializes all services including RAG capabilities
        - In inference-only mode: Initializes only essential services
        
        Services initialized include:
        - MongoDB service for data persistence
        - Redis service for caching
        - API key service for authentication
        - Prompt service for system prompts
        - Retriever service for document retrieval
        - Logger service for application logging
        - Guardrail service for content safety
        - Reranker service for document ranking
        - LLM client for model inference
        - Chat service for message handling
        - Health service for monitoring
        
        Args:
            app: The FastAPI application instance
            
        Raises:
            Exception: If any service fails to initialize
        """
        # Store config in app state
        app.state.config = self.config
        
        # Resolve provider configurations
        self._resolve_provider_configs()
        
        # Check if inference_only is enabled
        inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
        
        # Initialize MongoDB service regardless of mode
        from services.mongodb_service import MongoDBService
        app.state.mongodb_service = MongoDBService(self.config)
        self.logger.info("Initializing shared MongoDB service...")
        try:
            await app.state.mongodb_service.initialize()
            self.logger.info("Shared MongoDB service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize shared MongoDB service: {str(e)}")
            raise

        # Initialize Redis service if enabled (independent of inference_only mode)
        redis_enabled = _is_true_value(self.config.get('internal_services', {}).get('redis', {}).get('enabled', False))
        if redis_enabled:
            from services.redis_service import RedisService
            app.state.redis_service = RedisService(self.config)
            self.logger.info("Initializing Redis service...")
            try:
                if await app.state.redis_service.initialize():
                    self.logger.info("Redis service initialized successfully")
                else:
                    self.logger.warning("Redis service initialization failed - service will be disabled")
                    app.state.redis_service = None
            except Exception as e:
                self.logger.error(f"Failed to initialize Redis service: {str(e)}")
                app.state.redis_service = None
        else:
            app.state.redis_service = None
            self.logger.info("Redis service is disabled in configuration")

        # Initialize Chat History Service only in inference_only mode
        chat_history_enabled = _is_true_value(self.config.get('chat_history', {}).get('enabled', True))
        if chat_history_enabled and inference_only:
            from services.chat_history_service import ChatHistoryService
            app.state.chat_history_service = ChatHistoryService(
                self.config, 
                app.state.mongodb_service, 
                app.state.redis_service
            )
            self.logger.info("Initializing Chat History Service...")
            try:
                await app.state.chat_history_service.initialize()
                self.logger.info("Chat History Service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Chat History Service: {str(e)}")
                # Don't raise - chat history is optional
                app.state.chat_history_service = None
        else:
            app.state.chat_history_service = None
            self.logger.info("Chat history is disabled")

        if inference_only:
            self.logger.info("Inference-only mode enabled - skipping unnecessary service initialization")
            app.state.retriever = None
            app.state.embedding_service = None
            app.state.guardrail_service = None
            app.state.reranker_service = None
            app.state.api_key_service = None
            app.state.prompt_service = None
            # Note: We keep MongoDB, Redis, and Chat History services only in inference-only mode
            self.logger.info("Keeping MongoDB, Redis, and Chat History services for chat history tracking")
        else:
            # Lazy import and initialize API Key Service
            from services.api_key_service import ApiKeyService
            app.state.api_key_service = ApiKeyService(self.config, app.state.mongodb_service)
            self.logger.info("Initializing API Key Service...")
            try:
                await app.state.api_key_service.initialize()
                self.logger.info("API Key Service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize API Key Service: {str(e)}")
                raise
            
            # Lazy import and initialize Prompt Service
            from services.prompt_service import PromptService
            app.state.prompt_service = PromptService(self.config, app.state.mongodb_service)
            self.logger.info("Initializing Prompt Service...")
            try:
                await app.state.prompt_service.initialize()
                self.logger.info("Prompt Service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Prompt Service: {str(e)}")
                raise
            
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
                        # Only add embeddings if not in inference_only mode
                        if not inference_only and hasattr(app.state, 'embedding_service'):
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
                        from retrievers.implementations.qa_chroma_retriever import ChromaRetriever
                        
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
        
        # Always import Logger Service since it's always needed
        from services.logger_service import LoggerService
        app.state.logger_service = LoggerService(self.config)
        
        # Lazy import GuardrailService only if safety is enabled
        if _is_true_value(self.config.get('safety', {}).get('enabled', False)):
            from services.guardrail_service import GuardrailService
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
        
        # Lazy import reranker service only if enabled and not in inference_only mode
        if not inference_only and _is_true_value(self.config.get('reranker', {}).get('enabled', False)):
            from services.reranker_service import RerankerService
            app.state.reranker_service = RerankerService(self.config)
        else:
            app.state.reranker_service = None
        
        # Create LLM client using the factory
        inference_provider = self.config['general'].get('inference_provider', 'ollama')
        
        # Create LLM client with all required services
        app.state.llm_client = LLMClientFactory.create_llm_client(
            self.config, 
            None if inference_only else app.state.retriever,  # Pass None if inference_only is true
            guardrail_service=app.state.guardrail_service,  # Always pass guardrail service if it exists
            reranker_service=app.state.reranker_service,
            prompt_service=None if inference_only else app.state.prompt_service,
            no_results_message=no_results_message
        )
        
        # Initialize all services concurrently
        init_tasks = [
            app.state.llm_client.initialize(),
            app.state.logger_service.initialize_elasticsearch()
        ]
        
        # Only add guardrail service initialization if it exists
        if app.state.guardrail_service is not None:
            init_tasks.append(app.state.guardrail_service.initialize())
        
        # Only initialize reranker if enabled and not in inference_only mode
        if not inference_only and app.state.reranker_service:
            init_tasks.append(app.state.reranker_service.initialize())
        
        await asyncio.gather(*init_tasks)
        
        # Verify LLM connection
        if not await app.state.llm_client.verify_connection():
            self.logger.error(f"Failed to connect to {inference_provider}. Exiting...")
            raise Exception(f"Failed to connect to {inference_provider}")
        
        # Initialize remaining services - ChatService is always needed
        # Check if chat history service is available (only in inference_only mode)
        chat_history_service = getattr(app.state, 'chat_history_service', None)
        app.state.chat_service = ChatService(
            self.config, 
            app.state.llm_client, 
            app.state.logger_service,
            chat_history_service
        )

        # Lazy import Health Service
        from services.health_service import HealthService
        app.state.health_service = HealthService(
            config=self.config,
            datasource_client=app.state.datasource_client if hasattr(app.state, 'datasource_client') else None,
            llm_client=app.state.llm_client
        )

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

        # Close Redis service
        if hasattr(app.state, 'redis_service'):
            add_shutdown_task(app.state.redis_service, 'Redis Service')
        
        # Close Chat History service
        if hasattr(app.state, 'chat_history_service'):
            add_shutdown_task(app.state.chat_history_service, 'Chat History Service')
        
        # Close all tracked aiohttp sessions
        shutdown_tasks.append(close_all_aiohttp_sessions())
        
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
        """
        Log a summary of the server configuration.
        
        This method provides a comprehensive overview of the server's configuration
        by logging key settings and their values. It includes:
        - Server mode (Full/Inference-only)
        - Provider configurations
        - Service settings
        - API settings
        - Model information
        - Endpoint information
        
        The summary is formatted for easy reading and includes:
        - Clear section headers
        - Grouped related settings
        - Enabled/disabled status
        - Provider and model details
        
        This summary is logged at server startup to help with:
        - Configuration verification
        - Debugging
        - System monitoring
        - Documentation
        """
        self.logger.info("=" * 50)
        self.logger.info("Server Configuration Summary")
        self.logger.info("=" * 50)
        
        # Check if inference_only is enabled
        inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
        
        # Log mode first and prominently
        self.logger.info(f"Mode: {'INFERENCE-ONLY' if inference_only else 'FULL'} (RAG {'disabled' if inference_only else 'enabled'})")
        self.logger.info("-" * 50)
        
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
        
        # Get language detection configuration
        language_detection_enabled = _is_true_value(self.config.get('general', {}).get('language_detection', True))
        
        # Get session ID configuration
        session_config = self.config.get('general', {}).get('session_id', {})
        session_enabled = _is_true_value(session_config.get('required', False))
        session_header = session_config.get('header_name', 'X-Session-ID')
        
        # Get API key configuration
        api_key_config = self.config.get('api_keys', {})
        api_key_enabled = _is_true_value(api_key_config.get('enabled', True))
        api_key_header = api_key_config.get('header_name', 'X-API-Key')
        require_for_health = _is_true_value(api_key_config.get('require_for_health', False))
        
        self.logger.info(f"Inference provider: {inference_provider}")
        
        # Only log embedding info if not in inference_only mode
        if not inference_only:
            self.logger.info(f"Embedding: {'enabled' if embedding_enabled else 'disabled'}")
            if embedding_enabled:
                self.logger.info(f"Embedding provider: {embedding_provider}")
                if embedding_provider in self.config.get('embeddings', {}):
                    embed_model = self.config['embeddings'][embedding_provider].get('model', 'unknown')
                    self.logger.info(f"Embedding model: {embed_model}")
        
        self.logger.info(f"Language Detection: {'enabled' if language_detection_enabled else 'disabled'}")
        self.logger.info(f"Session ID: {'enabled' if session_enabled else 'disabled'} (header: {session_header})")
        self.logger.info(f"API Key: {'enabled' if api_key_enabled else 'disabled'} (header: {api_key_header})")
        
        # Only log chat history information if in inference_only mode
        if inference_only:
            chat_history_config = self.config.get('chat_history', {})
            chat_history_enabled = _is_true_value(chat_history_config.get('enabled', True))
            self.logger.info(f"Chat History: {'enabled' if chat_history_enabled else 'disabled'}")
            if chat_history_enabled:
                self.logger.info(f"  - Default message limit: {chat_history_config.get('default_limit', 50)}")
                self.logger.info(f"  - Store metadata: {chat_history_config.get('store_metadata', True)}")
                self.logger.info(f"  - Retention days: {chat_history_config.get('retention_days', 90)}")
                self.logger.info(f"  - Session auto-generate: {chat_history_config.get('session', {}).get('auto_generate', True)}")
                self.logger.info(f"  - Cache max messages: {chat_history_config.get('cache', {}).get('max_cached_messages', 100)}")
                self.logger.info(f"  - Cache max sessions: {chat_history_config.get('cache', {}).get('max_cached_sessions', 1000)}")
        
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
        
        # Log model information based on the selected inference provider
        if inference_provider in self.config.get('inference', {}):
            model_name = self.config['inference'][inference_provider].get('model', 'unknown')
            self.logger.info(f"Server running with {model_name} model")
        
        # Log retriever information only if not in inference_only mode and retriever exists
        if not inference_only and hasattr(self.app.state, 'retriever') and self.app.state.retriever is not None:
            try:
                self.logger.info(f"Confidence threshold: {self.app.state.retriever.confidence_threshold}")
            except AttributeError:
                # Skip logging if retriever is not fully initialized
                pass
        
        self.logger.info(f"Verbose mode: {_is_true_value(self.config['general'].get('verbose', False))}")
        
        # Log API endpoints
        self.logger.info("API Endpoints:")
        self.logger.info("  - MCP Completion Endpoint: POST /v1/chat")
        self.logger.info("  - Health check: GET /health")

    def _configure_middleware(self) -> None:
        """
        Configure middleware for the FastAPI application.
        
        This method sets up:
        - CORS middleware for cross-origin requests
        - Custom logging middleware for request/response tracking
        
        The CORS middleware is configured to allow all origins, methods, and headers
        for development. In production, this should be restricted to specific origins.
        """
        # Add CORS middleware with permissive settings for development
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # TODO: Restrict in production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add request logging middleware
        @self.app.middleware("http")
        async def log_requests(request: Request, call_next):
            start_time = time.time()
            response = await call_next(request)
            process_time = time.time() - start_time
            self.logger.info(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} - {request.client.host} - {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
            return response

    def _configure_routes(self) -> None:
        """
        Configure routes and endpoints for the FastAPI application.
        
        This method sets up all the API endpoints and their dependencies, including:
        - Chat endpoint with MCP protocol support
        - Health check endpoint
        - API key management endpoints
        - System prompt management endpoints
        
        Each endpoint is configured with appropriate:
        - Request validation
        - Authentication checks
        - Response formatting
        - Error handling
        
        The endpoints support:
        - Streaming responses for chat
        - JSON-RPC protocol for chat
        - REST API for management functions
        - Health monitoring
        - API key management
        - System prompt management
        
        Dependencies are lazy-loaded to improve startup time and resource usage.
        """
        # Define dependencies with lazy imports
        async def get_chat_service(request: Request):
            if not hasattr(request.app.state, 'chat_service'):
                from services.chat_service import ChatService
                # Get chat history service if available
                chat_history_service = getattr(request.app.state, 'chat_history_service', None)
                request.app.state.chat_service = ChatService(
                    request.app.state.config, 
                    request.app.state.llm_client, 
                    request.app.state.logger_service,
                    chat_history_service
                )
            return request.app.state.chat_service

        async def get_health_service(request: Request):
            if not hasattr(request.app.state, 'health_service'):
                from services.health_service import HealthService
                request.app.state.health_service = HealthService(
                    config=request.app.state.config,
                    datasource_client=getattr(request.app.state, 'datasource_client', None),
                    llm_client=request.app.state.llm_client
                )
            return request.app.state.health_service

        async def get_guardrail_service(request: Request):
            return request.app.state.guardrail_service

        async def get_api_key_service(request: Request):
            return request.app.state.api_key_service

        async def get_prompt_service(request: Request):
            return request.app.state.prompt_service

        # Add favicon.ico handler to return 204 No Content
        @self.app.get("/favicon.ico")
        async def favicon():
            return Response(status_code=204)

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
            session_enabled = _is_true_value(request.app.state.config.get('general', {}).get('session_id', {}).get('required', False))
            
            if not session_enabled:
                # Check if chat history requires session ID
                chat_history_config = request.app.state.config.get('chat_history', {})
                chat_history_enabled = _is_true_value(chat_history_config.get('enabled', True))
                session_required = chat_history_config.get('session', {}).get('required', True)
                
                if chat_history_enabled and session_required:
                    # Get session ID header name from chat history config
                    session_header = chat_history_config['session']['header_name']
                    session_id = request.headers.get(session_header)
                    
                    if not session_id or not session_id.strip():
                        # Check if auto-generate is enabled
                        if chat_history_config.get('session', {}).get('auto_generate', True):
                            # Generate a session ID
                            import uuid
                            session_id = str(uuid.uuid4())
                            if request.app.state.config.get('general', {}).get('verbose', False):
                                self.logger.info(f"Auto-generated session ID: {session_id}")
                        else:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Session ID is required. Please provide a non-empty string in the {session_header} header."
                            )
                    
                    return session_id.strip()
                else:
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

        async def get_user_id(request: Request) -> Optional[str]:
            """
            Extract user ID from request headers if provided
            
            Args:
                request: The incoming request
                
            Returns:
                The user ID if provided, None otherwise
            """
            # Get user header configuration from chat history config
            chat_history_config = request.app.state.config.get('chat_history', {})
            user_config = chat_history_config.get('user', {})
            
            if not user_config:
                return None
            
            user_header = user_config.get('header_name', 'X-User-ID')
            user_required = user_config.get('required', False)
            
            user_id = request.headers.get(user_header)
            
            if user_required and not user_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"User ID is required. Please provide a non-empty string in the {user_header} header."
                )
            
            return user_id.strip() if user_id else None

        async def get_api_key(request: Request) -> tuple[Optional[str], Optional[ObjectId]]:
            """
            Extract API key from request headers and validate it
            
            Args:
                request: The incoming request
                
            Returns:
                Tuple of (collection_name, system_prompt_id) associated with the API key
            """
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            
            if inference_only:
                # In inference_only mode, return default values without validation
                return "default", None
            
            # Get API key from header
            header_name = request.app.state.config.get('api_keys', {}).get('header_name', 'X-API-Key')
            api_key = request.headers.get(header_name)
            
            # For health endpoint, only require API key if explicitly configured
            if request.url.path == "/health":
                require_for_health = _is_true_value(request.app.state.config.get('api_keys', {}).get('require_for_health', False))
                if not require_for_health:
                    return "default", None
            
            # Check if API key service is available
            if not hasattr(request.app.state, 'api_key_service') or request.app.state.api_key_service is None:
                # If no API key service is available, allow access with default collection
                # This handles the case where API keys are disabled in config
                api_keys_enabled = _is_true_value(request.app.state.config.get('api_keys', {}).get('enabled', True))
                if not api_keys_enabled or (request.url.path == "/health" and not _is_true_value(request.app.state.config.get('api_keys', {}).get('require_for_health', False))):
                    return "default", None
                else:
                    raise HTTPException(status_code=503, detail="API key service is not available")
            
            # Validate API key and get collection name and system prompt ID
            try:
                collection_name, system_prompt_id = await request.app.state.api_key_service.get_collection_for_api_key(api_key)
                return collection_name, system_prompt_id
            except HTTPException as e:
                # Allow health check without API key if configured
                if (request.url.path == "/health" and 
                    not request.app.state.config.get('api_keys', {}).get('require_for_health', False)):
                    return "default", None
                raise e
                
        # MCP protocol endpoint
        @self.app.post("/v1/chat")
        async def mcp_chat_endpoint(
            request: Request,
            chat_service = Depends(get_chat_service),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(get_api_key),
            session_id: str = Depends(validate_session_id),
            user_id: Optional[str] = Depends(get_user_id)
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
                if user_id:
                    self.logger.debug(f"User ID: {user_id}")
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
                                    api_key=api_key,
                                    session_id=session_id,
                                    user_id=user_id
                                ):
                                    # Process chunk data
                                    try:
                                        if chunk.startswith("data: "):
                                            chunk = chunk[6:].strip()  # Remove "data: " prefix
                                        
                                        chunk_data = json.loads(chunk)
                                        
                                        # Handle error responses (including moderation blocks)
                                        if "error" in chunk_data:
                                            # Format the error response as a complete message
                                            error_response = {
                                                "jsonrpc": "2.0",
                                                "id": jsonrpc_request.id,
                                                "result": {
                                                    "name": "chat",
                                                    "type": "complete",
                                                    "output": {
                                                        "messages": [
                                                            {
                                                                "role": "assistant",
                                                                "content": chunk_data["error"]
                                                            }
                                                        ]
                                                    }
                                                }
                                            }
                                            yield f"data: {json.dumps(error_response)}\n\n"
                                            yield f"data: [DONE]\n\n"
                                            return
                                        
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
                            api_key=api_key,
                            session_id=session_id,
                            user_id=user_id
                        )
                        
                        # Handle error responses (including moderation blocks)
                        if "error" in result:
                            return MCPJsonRpcResponse(
                                jsonrpc="2.0",
                                error={
                                    "code": result["error"].get("code", -32603),
                                    "message": result["error"].get("message", "Unknown error")
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
            request: Request
        ):
            """
            Create a new API key for accessing the server.
            
            This endpoint allows administrators to create API keys with:
            - Collection-based access control
            - Client identification
            - Usage notes
            - Optional system prompt association
            
            Security considerations:
            - This is an admin-only endpoint
            - Should be protected by additional authentication
            - API keys should be stored securely
            - Keys should be rotated periodically
            
            Args:
                api_key_data: The API key creation request data
                request: The incoming request
                
            Returns:
                ApiKeyResponse containing the created API key and metadata
                
            Raises:
                HTTPException: If API key creation fails or service is unavailable
            """
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            if inference_only:
                raise HTTPException(
                    status_code=503, 
                    detail="API key management is not available in inference-only mode"
                )
            
            # Check if API key service is available
            if not hasattr(request.app.state, 'api_key_service') or request.app.state.api_key_service is None:
                raise HTTPException(
                    status_code=503, 
                    detail="API key service is not available"
                )
            
            api_key_service = request.app.state.api_key_service
            
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
            request: Request
        ):
            """
            List all API keys in the system.
            
            This endpoint provides a list of all API keys with:
            - Masked key values
            - Collection associations
            - Client information
            - Creation timestamps
            - Status information
            
            Security considerations:
            - This is an admin-only endpoint
            - Should be protected by additional authentication
            - API keys are masked in the response
            - Limited to 100 keys per request
            
            Args:
                request: The incoming request
                
            Returns:
                List of API key records with masked values
                
            Raises:
                HTTPException: If API key listing fails or service is unavailable
            """
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            if inference_only:
                raise HTTPException(
                    status_code=503, 
                    detail="API key management is not available in inference-only mode"
                )
            
            # Check if API key service is available
            if not hasattr(request.app.state, 'api_key_service') or request.app.state.api_key_service is None:
                raise HTTPException(
                    status_code=503, 
                    detail="API key service is not available"
                )
            
            api_key_service = request.app.state.api_key_service
            
            try:
                # Ensure service is initialized
                if not api_key_service._initialized:
                    await api_key_service.initialize()
                
                # Retrieve all API keys
                cursor = api_key_service.api_keys_collection.find({})
                api_keys = await cursor.to_list(length=100)  # Limit to 100 keys
                
                # Convert MongoDB documents to JSON-serializable format
                serialized_keys = []
                for key in api_keys:
                    # Convert _id to string
                    key_dict = {
                        "_id": str(key["_id"]),
                        "api_key": f"***{key['api_key'][-4:]}" if key.get("api_key") else "***",
                        "collection_name": key.get("collection_name"),
                        "client_name": key.get("client_name"),
                        "notes": key.get("notes"),
                        "active": key.get("active", True),
                        "created_at": key.get("created_at").timestamp() if key.get("created_at") else None
                    }
                    
                    # Handle system_prompt_id if it exists
                    if key.get("system_prompt_id"):
                        key_dict["system_prompt_id"] = str(key["system_prompt_id"])
                    
                    serialized_keys.append(key_dict)
                
                return serialized_keys
                
            except Exception as e:
                self.logger.error(f"Error listing API keys: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to list API keys: {str(e)}")

        @self.app.get("/admin/api-keys/{api_key}/status")
        async def get_api_key_status(
            api_key: str,
            request: Request
        ):
            """
            Get the status of a specific API key.
            
            This endpoint provides detailed status information for an API key:
            - Active/inactive status
            - Last used timestamp
            - Associated collection
            - System prompt association
            - Usage statistics
            
            Security considerations:
            - This is an admin-only endpoint
            - Should be protected by additional authentication
            - API key is masked in logs
            
            Args:
                api_key: The API key to check
                request: The incoming request
                
            Returns:
                Status information for the specified API key
                
            Raises:
                HTTPException: If API key status check fails or service is unavailable
            """
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            if inference_only:
                raise HTTPException(
                    status_code=503, 
                    detail="API key management is not available in inference-only mode"
                )
            
            # Check if API key service is available
            if not hasattr(request.app.state, 'api_key_service') or request.app.state.api_key_service is None:
                raise HTTPException(
                    status_code=503, 
                    detail="API key service is not available"
                )
            
            api_key_service = request.app.state.api_key_service
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
            health_service = Depends(get_health_service)
        ):
            """Check the health of the application and its dependencies"""
            health = await health_service.get_health_status()
            return health

        # System Prompts management routes
        @self.app.post("/admin/prompts", response_model=SystemPromptResponse)
        async def create_prompt(
            prompt_data: SystemPromptCreate,
            request: Request
        ):
            """Create a new system prompt"""
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            if inference_only:
                raise HTTPException(
                    status_code=503, 
                    detail="Prompt management is not available in inference-only mode"
                )
            
            # Check if prompt service is available
            if not hasattr(request.app.state, 'prompt_service') or request.app.state.prompt_service is None:
                raise HTTPException(
                    status_code=503, 
                    detail="Prompt service is not available"
                )
            
            prompt_service = request.app.state.prompt_service
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

        @self.app.get("/admin/chat-history/{session_id}")
        async def get_chat_history(
            session_id: str,
            request: Request,
            limit: int = 50
        ):
            """Get chat history for a session"""
            # Check if inference_only is enabled
            inference_only = _is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            if not inference_only:
                raise HTTPException(
                    status_code=503, 
                    detail="Chat history is only available in inference-only mode"
                )
            
            if not hasattr(request.app.state, 'chat_history_service') or not request.app.state.chat_history_service:
                raise HTTPException(status_code=503, detail="Chat history service is not available")
            
            history = await request.app.state.chat_history_service.get_conversation_history(
                session_id=session_id,
                limit=limit,
                include_metadata=True
            )
            
            return {"session_id": session_id, "messages": history, "count": len(history)}
    
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
        """
        Run the FastAPI application with the configured settings.
        
        This method starts the server with the following features:
        - HTTPS support if configured
        - Graceful shutdown handling
        - Signal handling for clean termination
        - Automatic session cleanup
        
        The server can run in two modes:
        1. HTTP mode: Standard HTTP server
        2. HTTPS mode: Secure server with SSL/TLS
        
        Configuration is read from:
        - Server settings (host, port)
        - SSL settings (certificates, keys)
        - Timeout settings
        - Logging settings
        
        The server uses uvicorn as the ASGI server with:
        - Async support
        - Keep-alive connections
        - Graceful shutdown
        - Custom logging
        
        Raises:
            Exception: If server fails to start
        """
        # Get server settings from config
        port = int(self.config.get('general', {}).get('port', 3000))
        host = self.config.get('general', {}).get('host', '0.0.0.0')

        # Use HTTPS if enabled in config
        https_enabled = _is_true_value(self.config.get('general', {}).get('https', {}).get('enabled', False))
        
        # Set SSL params based on config
        ssl_keyfile = None
        ssl_certfile = None
        port_to_use = port
        
        if https_enabled:
            ssl_keyfile = self.config['general']['https']['key_file']
            ssl_certfile = self.config['general']['https']['cert_file']
            port_to_use = int(self.config['general']['https'].get('port', 3443))
        
        # Configure uvicorn with signal handlers for graceful shutdown
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port_to_use,
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile,
            loop="asyncio",
            timeout_keep_alive=30,
            timeout_graceful_shutdown=30,
            access_log=False  # Disable FastAPI's default access logging
        )
        
        server = uvicorn.Server(config)
        
        try:
            # Register a shutdown function to ensure all aiohttp sessions are closed
            atexit.register(lambda: asyncio.run(close_all_aiohttp_sessions()))
            
            # Start the server
            if https_enabled:
                self.logger.info(f"Starting HTTPS server on {host}:{port_to_use}")
            else:
                self.logger.info(f"Starting HTTP server on {host}:{port_to_use}")
                
            server.run()
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal, initiating graceful shutdown...")
            # The server will handle the graceful shutdown through its signal handlers