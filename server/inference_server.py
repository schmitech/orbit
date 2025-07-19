import ssl
import asyncio
import atexit
import aiohttp
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import local modules (ensure these exist in your project structure)
from config.config_manager import load_config, _is_true_value
from config.resolver import ConfigResolver
from config.logging_configurator import LoggingConfigurator
from config.middleware_configurator import MiddlewareConfigurator
from services.service_factory import ServiceFactory
from utils.http_utils import close_all_aiohttp_sessions, setup_aiohttp_session_tracking
from routes.routes_configurator import RouteConfigurator
from config.configuration_summary_logger import ConfigurationSummaryLogger
from datasources import DatasourceFactory

# Lazy imports for retrievers - only imported when needed
RetrieverFactory = None
ADAPTER_REGISTRY = None

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
        - aiohttp session tracking for proper cleanup
        
        Args:
            config_path: Optional path to a custom configuration file.
                        If not provided, uses default configuration.
        
        Raises:
            FileNotFoundError: If the specified config file doesn't exist
            ValueError: If the configuration is invalid
        """
        # Initialize basic logging until proper configuration is loaded
        self.logger = LoggingConfigurator.setup_initial_logging()
        
        # Set up aiohttp session tracking for proper cleanup
        setup_aiohttp_session_tracking()
        
        # Load configuration
        self.config = load_config(config_path)
        
        # Configure proper logging with loaded configuration
        self.logger = LoggingConfigurator.setup_full_logging(self.config)
        
        # Now create the config resolver with the proper logger
        self.config_resolver = ConfigResolver(self.config, self.logger)

        self.service_factory = ServiceFactory(self.config, self.logger)
        self.route_configurator = RouteConfigurator(self.config, self.logger)
        self.configuration_summary_logger = ConfigurationSummaryLogger(self.config, self.logger)
        self.datasource_factory = DatasourceFactory(self.config, self.logger)
        
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
        MiddlewareConfigurator.configure_middleware(self.app, self.config, self.logger)
        self.route_configurator.configure_routes(self.app)
        
        self.logger.info("InferenceServer initialized")

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
                self.configuration_summary_logger.log_configuration_summary(app)
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

    def _initialize_retrievers(self):
        """
        Initialize retrievers package and its dependencies only if not in inference_only mode.
        """
        inference_only = _is_true_value(self.config.get('general', {}).get('inference_only', False))
        
        if not inference_only:
            global RetrieverFactory, ADAPTER_REGISTRY
            from retrievers.base.base_retriever import RetrieverFactory
            from retrievers.adapters.registry import ADAPTER_REGISTRY
            self.logger.info("Initializing retrievers package for RAG mode")
        else:
            self.logger.info("Skipping retrievers initialization in inference-only mode")

    def _initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client
        """
        return self.datasource_factory.initialize_datasource_client(provider)

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
        self.config_resolver.resolve_all_providers()
        
        # Initialize retrievers if needed
        self._initialize_retrievers()

        # Use service factory to initialize all services
        await self.service_factory.initialize_all_services(app)

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
        
        if hasattr(app.state, 'prompt_service'):
            # PromptService doesn't have a close method, so we skip it
            self.logger.info("Skipping PromptService shutdown (no close method)")
        
        if hasattr(app.state, 'reranker_service'):
            add_shutdown_task(app.state.reranker_service, 'Reranker Service')
        
        if hasattr(app.state, 'api_key_service'):
            add_shutdown_task(app.state.api_key_service, 'API Key Service')
        
        if hasattr(app.state, 'embedding_service'):
            add_shutdown_task(app.state.embedding_service, 'Embedding Service')
        
        if hasattr(app.state, 'llm_guard_service'):
            add_shutdown_task(app.state.llm_guard_service, 'LLM Guard Service')
            
        # Close Moderator Service
        if hasattr(app.state, 'moderator_service'):
            add_shutdown_task(app.state.moderator_service, 'Moderator Service')

        # Close shared MongoDB service
        if hasattr(app.state, 'mongodb_service'):
            add_shutdown_task(app.state.mongodb_service, 'MongoDB Service')

        # Close Redis service
        if hasattr(app.state, 'redis_service'):
            add_shutdown_task(app.state.redis_service, 'Redis Service')
        
        # Close Chat History service
        if hasattr(app.state, 'chat_history_service'):
            add_shutdown_task(app.state.chat_history_service, 'Chat History Service')
        
        # Close fault tolerance services
        if hasattr(self.service_factory, '_shutdown_fault_tolerance_services'):
            try:
                await self.service_factory._shutdown_fault_tolerance_services(app)
            except Exception as e:
                self.logger.error(f"Error shutting down fault tolerance services: {str(e)}")
        
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
            # Start the server
            if https_enabled:
                self.logger.info(f"Starting HTTPS server on {host}:{port_to_use}")
            else:
                self.logger.info(f"Starting HTTP server on {host}:{port_to_use}")
                
            server.run()
        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal, initiating graceful shutdown...")
            # The server will handle the graceful shutdown through its signal handlers