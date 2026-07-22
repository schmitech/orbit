import logging
import os
import ssl
import asyncio
import datetime
from pathlib import Path
from typing import Any, Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP

from config.config_manager import load_config
from config.resolver import ConfigResolver
from config.logging_configurator import LoggingConfigurator
from config.middleware_configurator import MiddlewareConfigurator
from config.configuration_summary_logger import ConfigurationSummaryLogger
from services.service_factory import ServiceFactory
from utils import is_true_value
from utils.http_utils import close_all_aiohttp_sessions, setup_aiohttp_session_tracking
from utils.thread_pool_manager import ThreadPoolManager
from routes.routes_configurator import RouteConfigurator
from datasources import DatasourceFactory

logger = logging.getLogger(__name__)
ADMIN_DIR = Path(__file__).parent / "admin"
TLS_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!eNULL:!MD5:!RC4:!3DES"

# Lazy imports for retrievers - only imported when needed
RetrieverFactory = None
ADAPTER_REGISTRY = None

class InferenceServer:
    """
    A modular inference server built with FastAPI that provides chat endpoints
    with LLM integration and vector database retrieval capabilities.

    This class serves as the main entry point for the ORBIT server.
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

        # Store config path for hot-reload functionality
        self.config_path = config_path or self._find_default_config_path()

        # Load configuration
        self.config = load_config(self.config_path)
        
        # Configure proper logging with loaded configuration
        self.logger = LoggingConfigurator.setup_full_logging(self.config)
        
        # Now create the config resolver with the proper logger
        self.config_resolver = ConfigResolver(self.config, self.logger)

        self.service_factory = ServiceFactory(self.config, self.logger)
        self.route_configurator = RouteConfigurator(self.config, self.logger)
        self.configuration_summary_logger = ConfigurationSummaryLogger(self.config, self.logger)
        self.datasource_factory = DatasourceFactory(self.config, self.logger)
        
        # Initialize thread pool manager with specialized pools
        self.thread_pool_manager = ThreadPoolManager(self.config, self.logger)

        docs_enabled = self._docs_enabled()
        
        # Initialize FastAPI app with lifespan manager
        self.app = FastAPI(
            title="ORBIT",
            description="A FastAPI server with chat endpoint and RAG capabilities",
            version="2.10.1",
            lifespan=self._create_lifespan_manager(),
            docs_url="/docs" if docs_enabled else None,
            redoc_url="/redoc" if docs_enabled else None,
            openapi_url="/openapi.json" if docs_enabled else None,
        )
        self.app.mount("/static", StaticFiles(directory=str(ADMIN_DIR)), name="static")
        
        # Configure middleware and routes
        MiddlewareConfigurator.configure_middleware(self.app, self.config, self.logger)
        self.route_configurator.configure_routes(self.app)

        # Initialize MCP server
        logger.info("Initializing MCP server with fastmcp")
        self.mcp_server = FastMCP.from_fastapi(self.app, name="ORBIT")
        self.app.mount("/mcp", self.mcp_server.http_app())

        logger.info(
            "OpenAPI docs %s (ENVIRONMENT=%s)",
            "enabled" if docs_enabled else "disabled",
            os.getenv("ENVIRONMENT", "unset"),
        )
        
        logger.info("InferenceServer initialized")

    @staticmethod
    def _docs_enabled() -> bool:
        """Disable autogenerated docs when ENVIRONMENT is set to production."""
        return os.getenv("ENVIRONMENT", "").strip().lower() != "production"

    def _find_default_config_path(self) -> str:
        """
        Find the default config.yaml path by checking common locations.

        Returns:
            Path to the config file

        Raises:
            FileNotFoundError: If no config file found
        """
        config_paths = [
            '../config/config.yaml',
            '../../config/config.yaml',
            'config.yaml',
            'config/config.yaml'
        ]

        for path in config_paths:
            if os.path.exists(path):
                return os.path.abspath(path)

        raise FileNotFoundError("Could not find config.yaml in any of the default locations")

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
            logger.info("Starting up FastAPI application")
            
            # Initialize services and clients
            try:
                # Store thread pool manager in app state for service access
                app.state.thread_pool_manager = self.thread_pool_manager
                await self._initialize_services(app)
                self.configuration_summary_logger.log_configuration_summary(app)
                logger.info("Startup complete")
            except Exception as e:
                logger.error("Failed to initialize services: %s", e)
                raise
            
            yield
            
            # Cleanup resources
            try:
                logger.info("Shutting down services...")
                await self._shutdown_services(app)
                logger.info("Services shut down successfully")
            except Exception as e:
                logger.error("Error during shutdown: %s", e)
        
        return lifespan

    def _initialize_retrievers(self):
        """
        Initialize retrievers package and its dependencies.
        """
        global RetrieverFactory, ADAPTER_REGISTRY
        from retrievers.base.base_retriever import RetrieverFactory
        from adapters.registry import ADAPTER_REGISTRY
        logger.info("Initializing retrievers package for RAG mode")

    async def _initialize_datasource_client(self, provider: str) -> Any:
        """
        Initialize a datasource client based on the selected provider.
        
        Args:
            provider: The datasource provider to initialize
            
        Returns:
            An initialized datasource client
        """
        return await self.datasource_factory.initialize_datasource_client(provider)

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
        - Cache service (Redis, Memcached, ...) for caching
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
        # Store config and config path in app state
        app.state.config = self.config
        app.state.config_path = self.config_path
        app.state.paused = False
        
        # Resolve provider configurations
        self.config_resolver.resolve_all_providers()
        
        # Initialize retrievers if needed
        self._initialize_retrievers()

        # Use service factory to initialize all services
        await self.service_factory.initialize_all_services(app)

        # Ensure the durable pause-state row exists before any request can reach
        # it, so a later read failure can only mean a real outage, never "row not
        # created yet" (see services/pause_state.py).
        from services.pause_state import ensure_initialized
        await ensure_initialized(app.state)

    async def _shutdown_services(self, app: FastAPI) -> None:
        """
        Shut down all services and clients.

        Args:
            app: The FastAPI application containing services
        """
        # Stop the message consumer first so in-flight messages settle before the
        # pipeline/services it uses are torn down.
        message_consumer = getattr(app.state, 'message_consumer', None)
        if message_consumer is not None:
            try:
                await asyncio.wait_for(message_consumer.stop(), timeout=10.0)
            except Exception as e:
                logger.error("Error stopping message consumer: %s", e)

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
                    logger.error("Error preparing shutdown for %s: %s", service_name, e)

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
                logger.info("Retriever was never initialized, no need to close")

        if hasattr(app.state, 'reranker_service'):
            add_shutdown_task(app.state.reranker_service, 'Reranker Service')

        if hasattr(app.state, 'api_key_service'):
            add_shutdown_task(app.state.api_key_service, 'API Key Service')

        if hasattr(app.state, 'embedding_service'):
            add_shutdown_task(app.state.embedding_service, 'Embedding Service')

        # Close Moderator Service
        if hasattr(app.state, 'moderator_service'):
            add_shutdown_task(app.state.moderator_service, 'Moderator Service')

        # Close shared MongoDB service
        if hasattr(app.state, 'mongodb_service'):
            add_shutdown_task(app.state.mongodb_service, 'MongoDB Service')

        # Close cache service
        if hasattr(app.state, 'cache_service'):
            add_shutdown_task(app.state.cache_service, 'Cache Service')

        # Close Metrics service
        if hasattr(app.state, 'metrics_service'):
            add_shutdown_task(app.state.metrics_service, 'Metrics Service')

        # Close Chat History service
        if hasattr(app.state, 'chat_history_service'):
            add_shutdown_task(app.state.chat_history_service, 'Chat History Service')

        # Close Adapter Manager (includes file retriever cleanup)
        if hasattr(app.state, 'adapter_manager'):
            add_shutdown_task(app.state.adapter_manager, 'Adapter Manager')

        # Close File Processing Service
        if hasattr(app.state, 'file_processing_service'):
            add_shutdown_task(app.state.file_processing_service, 'File Processing Service')

        # Close fault tolerance services (with timeout to prevent hanging)
        if hasattr(self.service_factory, '_shutdown_fault_tolerance_services'):
            try:
                await asyncio.wait_for(
                    self.service_factory._shutdown_fault_tolerance_services(app),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error("Timeout shutting down fault tolerance services, continuing shutdown")
            except Exception as e:
                logger.error("Error shutting down fault tolerance services: %s", e)

        # Close all tracked aiohttp sessions
        shutdown_tasks.append(close_all_aiohttp_sessions())

        # Run all async service shutdown tasks with timeout
        if shutdown_tasks:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=30.0,
                )
                for result in results:
                    if isinstance(result, Exception):
                        logger.error("Error during service shutdown: %s", result)
                logger.info("Services shut down successfully")
            except asyncio.TimeoutError:
                logger.error("Timeout while shutting down services")
            except Exception as e:
                logger.error("Error during shutdown of services: %s", e)
        else:
            logger.info("No services to shut down")

        # LAST: Shutdown thread pool manager (after all services that may use pools)
        # Run in executor to avoid blocking the event loop
        if hasattr(self, 'thread_pool_manager'):
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(self.thread_pool_manager.shutdown, wait=True),
                    timeout=5.0,
                )
                logger.info("Thread pool manager shut down successfully")
            except asyncio.TimeoutError:
                logger.warning("Thread pool shutdown timed out, force-cancelling remaining tasks")
                self.thread_pool_manager.shutdown(wait=False)
                logger.info("Thread pool manager force shut down")
            except Exception as e:
                logger.error("Error shutting down thread pool manager: %s", e)

    def _validate_ssl_config(self, https_config: dict) -> None:
        """
        Validate SSL certificate and key files before starting uvicorn.

        Raises:
            ValueError: If required config keys are missing or cert/key don't match
            FileNotFoundError: If cert or key file cannot be found
        """
        cert_file = https_config.get('cert_file')
        key_file = https_config.get('key_file')
        key_password = https_config.get('key_password')

        if not cert_file:
            raise ValueError("HTTPS enabled but 'cert_file' not set in config")
        if not key_file:
            raise ValueError("HTTPS enabled but 'key_file' not set in config")
        if not os.path.isfile(cert_file):
            raise FileNotFoundError(f"TLS certificate not found: {cert_file}")
        if not os.path.isfile(key_file):
            raise FileNotFoundError(f"TLS key file not found: {key_file}")

        # Verify cert and key are a matched pair (raises ssl.SSLError on mismatch)
        try:
            probe = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            probe.load_cert_chain(cert_file, key_file, password=key_password)
        except ssl.SSLError as e:
            raise ValueError(f"TLS cert/key validation failed: {e}") from e

        logger.info("TLS certificate and key validated successfully")

        # Best-effort expiry check (requires the 'cryptography' package)
        try:
            from cryptography import x509 as _x509  # type: ignore[import]
            with open(cert_file, 'rb') as f:
                cert = _x509.load_pem_x509_certificate(f.read())
            try:
                expiry = cert.not_valid_after_utc  # cryptography >= 42
            except AttributeError:
                expiry = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days_remaining = (expiry - now).days
            if days_remaining < 0:
                raise ValueError(f"TLS certificate expired {abs(days_remaining)} days ago ({expiry.date()})")
            if days_remaining < 30:
                logger.warning("TLS certificate expires in %d days (%s)", days_remaining, expiry.date())
            else:
                logger.info("TLS certificate valid for %d more days", days_remaining)
        except ImportError:
            pass  # 'cryptography' not available — skipping expiry check

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
        https_enabled = is_true_value(self.config.get('general', {}).get('https', {}).get('enabled', False))

        # Set SSL params based on config
        ssl_keyfile = None
        ssl_certfile = None
        ssl_keyfile_password = None
        port_to_use = port

        if https_enabled:
            https_config = self.config.get('general', {}).get('https', {}) or {}
            ssl_certfile = https_config.get('cert_file')
            ssl_keyfile = https_config.get('key_file')
            ssl_keyfile_password = https_config.get('key_password')
            port_to_use = int(https_config.get('port', 3443))
            # Validate cert/key files early so errors are clear before uvicorn starts
            self._validate_ssl_config(https_config)

        # Get performance configuration
        perf_config = self.config.get('performance', {})
        workers = perf_config.get('workers', 1)

        config_kwargs = {
            "host": host,
            "port": port_to_use,
            "workers": workers if workers > 1 else None,  # Only use workers if > 1
            "loop": "asyncio",
            "timeout_keep_alive": perf_config.get('keep_alive_timeout', 30),
            "timeout_graceful_shutdown": 30,
            "access_log": False,  # Disable FastAPI's default access logging
            "log_config": None,  # Reuse global logging configuration for consistent formatting
            "h11_max_incomplete_event_size": perf_config.get('h11_max_incomplete_event_size'),
            "limit_concurrency": None,  # Don't limit concurrent connections
            "backlog": 2048,  # Connection backlog
        }

        if https_enabled:
            config_kwargs.update(
                {
                    "ssl_keyfile": ssl_keyfile,
                    "ssl_certfile": ssl_certfile,
                    "ssl_keyfile_password": ssl_keyfile_password,
                    "ssl_ciphers": TLS_CIPHERS,
                }
            )

        # Configure uvicorn with signal handlers for graceful shutdown
        config = uvicorn.Config(self.app, **config_kwargs)
        
        server = uvicorn.Server(config)
        
        try:
            # Start the server
            if https_enabled:
                logger.info("Starting HTTPS server on %s:%s", host, port_to_use)
            else:
                logger.info("Starting HTTP server on %s:%s", host, port_to_use)
                
            server.run()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal, initiating graceful shutdown...")
            # The server will handle the graceful shutdown through its signal handlers
