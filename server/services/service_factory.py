"""
Service factory for managing application service initialization and lifecycle.

This module handles the creation, initialization, and management of all services
required by the inference server, including dependency injection and lifecycle management.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI

from utils import is_true_value
from services.auth_service import AuthService

from ai_services.registry import register_all_services


class ServiceFactory:
    """
    Factory class for managing service initialization and lifecycle.

    This class is responsible for:
    - Service discovery and instantiation
    - Dependency injection between services
    - Service lifecycle management
    - Health checking and verification
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """
        Initialize the ServiceFactory.

        Args:
            config: The application configuration dictionary
            logger: Logger instance for service initialization logging
        """
        self.config = config
        self.logger = logger
        self.chat_history_enabled = is_true_value(config.get('chat_history', {}).get('enabled', False))
        self.verbose = is_true_value(config.get('general', {}).get('verbose', False))

        # Fault tolerance is always enabled as core functionality
        self.fault_tolerance_enabled = True

        # Register AI services with config to enable selective loading
        register_all_services(config)

        # Log the mode detection for debugging (only when verbose)
        if self.verbose:
            self.logger.info(f"ServiceFactory initialized - chat_history_enabled={self.chat_history_enabled}")
    
    async def initialize_all_services(self, app: FastAPI) -> None:
        """Initialize all services required by the application."""
        try:
            if self.verbose:
                self.logger.info(f"Starting service initialization - chat_history_enabled={self.chat_history_enabled}")

            # Initialize core services (MongoDB, Redis)
            await self._initialize_core_services(app)

            # Initialize full mode services
            if self.verbose:
                self.logger.info("Initializing full RAG mode services")
            await self._initialize_full_mode_services(app)
            
            # Initialize shared services (Logger, LLM Guard, Reranker)
            await self._initialize_shared_services(app)
            
            # Initialize fault tolerance services (always enabled)
            if self.verbose:
                self.logger.info("Initializing fault tolerance services")
            # Fault tolerance is now handled by FaultTolerantAdapterManager directly
            
            # Initialize LLM client (after LLM Guard service)
            await self._initialize_llm_client(app)
            
            # Initialize dependent services (chat service and health service)
            await self._initialize_dependent_services(app)
            
            self.logger.info("All services initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize services: {str(e)}")
            raise
    
    async def _initialize_core_services(self, app: FastAPI) -> None:
        """Initialize core services that are always needed."""
        # Authentication is always enabled (no option to disable)
        auth_enabled = True

        # Initialize database service if needed
        await self._initialize_database_if_needed(app, auth_enabled)

        # Initialize Redis service if enabled
        await self._initialize_redis_service(app)

        # Initialize authentication service (requires database to be initialized first)
        await self._initialize_auth_service_if_available(app, auth_enabled)
    
    async def _initialize_database_if_needed(self, app: FastAPI, auth_enabled: bool) -> None:
        """Initialize database service if required by current configuration."""
        # Database is required when:
        # - Retriever adapters are present (full mode always initializes database)
        # - OR auth is enabled (for authentication) - auth is always enabled
        # - OR chat_history is enabled (for chat history storage)
        database_required = (
            auth_enabled or
            self.chat_history_enabled
        )

        if database_required:
            await self._initialize_database_service(app)

            # Log the specific reason(s) for database initialization
            reasons = []
            if auth_enabled:
                reasons.append("authentication")
            if self.chat_history_enabled:
                reasons.append("chat history")

            # Get backend type for logging
            backend_type = self.config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')
            self.logger.info(f"Database ({backend_type}) initialized for: {', '.join(reasons)}")
    
    async def _initialize_auth_service_if_available(self, app: FastAPI, auth_enabled: bool) -> None:
        """Initialize authentication service if database is available. Auth is always enabled."""
        if hasattr(app.state, 'database_service') and app.state.database_service is not None:
            await self._initialize_auth_service(app)
        else:
            # Auth is always enabled - log error if database is not available
            self.logger.error("Authentication is required but database service not available - server will not function properly")
            if False:  # Keep old else branch for reference but never execute
                self.logger.info("Auth service disabled in configuration")
    
    async def _initialize_auth_service(self, app: FastAPI) -> None:
        """Initialize the authentication service. Authentication is always enabled."""
        try:
            # Use the shared database service if available
            database_service = getattr(app.state, 'database_service', None)

            # Initialize auth service
            from services.auth_service import AuthService
            auth_service = AuthService(self.config, database_service)
            await auth_service.initialize()

            app.state.auth_service = auth_service
            self.logger.info("Authentication service initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize authentication service: {str(e)}")
            # Don't fail the entire startup if auth fails, but log it prominently
            app.state.auth_service = None
    
    async def _initialize_full_mode_services(self, app: FastAPI) -> None:
        """Initialize services specific to full RAG mode."""
        # Initialize API Key Service
        await self._initialize_api_key_service(app)
        
        # Initialize Prompt Service
        await self._initialize_prompt_service(app)
        
        # Initialize Vector Store Manager (for adapters that need it)
        await self._initialize_vector_store_manager(app)
        
        # Initialize Dynamic Adapter Manager
        await self._initialize_adapter_manager(app)

        # Configure chat history consistently with inference-only mode
        await self._configure_chat_history_service(app)
    
    async def _initialize_shared_services(self, app: FastAPI) -> None:
        """Initialize services that are used in both modes."""
        # Initialize Logger Service (always needed)
        await self._initialize_logger_service(app)
        
        # Initialize Metrics Service (for monitoring dashboard)
        await self._initialize_metrics_service(app)
        
        # Initialize Clock Service
        await self._initialize_clock_service(app)
        
        # Initialize Moderator Service if enabled
        await self._initialize_moderator_service(app)
        
        # Initialize LLM Guard Service if enabled
        await self._initialize_llm_guard_service(app)
        
        # Initialize File Processing Service (for file upload API)
        await self._initialize_file_processing_service(app)

        # Initialize Reranker Service if enabled
        if is_true_value(self.config.get('reranker', {}).get('enabled', False)):
            await self._initialize_reranker_service(app)
        else:
            app.state.reranker_service = None
    
    async def _initialize_llm_client(self, app: FastAPI) -> None:
        """Initialize and verify the LLM client."""
        # Pipeline mode is now the default - no need to create traditional LLM client
        app.state.llm_client = None
        self.logger.info("Using pipeline architecture - traditional LLM client not needed")
    
    async def _initialize_dependent_services(self, app: FastAPI) -> None:
        """Initialize services that depend on other services."""
        # Initialize Chat Service (always needed)
        chat_history_service = getattr(app.state, 'chat_history_service', None)
        llm_guard_service = getattr(app.state, 'llm_guard_service', None)
        moderator_service = getattr(app.state, 'moderator_service', None)
        clock_service = getattr(app.state, 'clock_service', None)
        
        # Use pipeline-based chat service (now the default)
        from services.pipeline_chat_service import PipelineChatService
        app.state.chat_service = PipelineChatService(
            config=self.config,
            logger_service=app.state.logger_service,
            chat_history_service=chat_history_service,
            llm_guard_service=llm_guard_service,
            moderator_service=moderator_service,
            retriever=getattr(app.state, 'retriever', None),
            reranker_service=getattr(app.state, 'reranker_service', None),
            prompt_service=getattr(app.state, 'prompt_service', None),
            clock_service=clock_service
        )
        # Initialize the pipeline provider
        try:
            await app.state.chat_service.initialize()
            self.logger.info("Initialized pipeline-based chat service")
        except ValueError as e:
            if "No service registered for inference with provider" in str(e):
                # Extract available providers from the error message
                error_msg = str(e)

                # Get the configured provider
                configured_provider = self.config.get('general', {}).get('inference_provider', 'unknown')

                self.logger.warning("=" * 80)
                self.logger.warning("CONFIGURATION WARNING: Main inference provider not available")
                self.logger.warning("=" * 80)
                self.logger.warning(f"The default inference provider '{configured_provider}' is not registered.")
                self.logger.warning(f"This is likely because the provider is disabled in config/inference.yaml.")
                self.logger.warning("")
                self.logger.warning("The server will continue to start, but:")
                self.logger.warning(f"  - Adapters WITHOUT their own inference_provider override will NOT work")
                self.logger.warning(f"  - Adapters WITH their own inference_provider override WILL work normally")
                self.logger.warning("")
                self.logger.warning("To fix this warning:")
                self.logger.warning(f"  1. Enable '{configured_provider}' in config/inference.yaml by setting 'enabled: true'")
                self.logger.warning(f"  2. Change 'inference_provider' in config/config.yaml to an enabled provider")
                self.logger.warning("")

                # Try to extract available providers from error message
                if "Available services:" in error_msg:
                    available_inference = error_msg.split("'inference': [")[1].split("]")[0] if "'inference': [" in error_msg else "unknown"
                    self.logger.warning(f"Available inference providers: [{available_inference}]")

                self.logger.warning("=" * 80)

                # Mark chat service as initialized but without default provider
                app.state.chat_service._pipeline_initialized = True
                app.state.chat_service._default_provider_available = False
                self.logger.warning("Chat service initialized WITHOUT default provider - only adapter overrides will work")
            else:
                # Re-raise other ValueError exceptions
                raise
        
        # Initialize Health Service
        from services.health_service import HealthService
        app.state.health_service = HealthService(
            config=self.config,
            datasource_client=getattr(app.state, 'datasource_client', None),
            llm_client=getattr(app.state, 'llm_client', None)  # May be None in pipeline mode
        )
        
        self.logger.info("Dependent services initialized successfully")
    
    async def _initialize_database_service(self, app: FastAPI) -> None:
        """Initialize database service using factory method."""
        from services.database_service import create_database_service

        # Create database service using factory
        app.state.database_service = create_database_service(self.config)

        # For backward compatibility, also set mongodb_service
        app.state.mongodb_service = app.state.database_service

        backend_type = self.config.get('internal_services', {}).get('backend', {}).get('type', 'mongodb')
        self.logger.info(f"Initializing shared database service ({backend_type})...")

        try:
            await app.state.database_service.initialize()
            self.logger.info(f"Shared database service ({backend_type}) initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize shared database service: {str(e)}")
            raise
    
    async def _initialize_redis_service(self, app: FastAPI) -> None:
        """Initialize Redis service if enabled."""
        redis_enabled = is_true_value(self.config.get('internal_services', {}).get('redis', {}).get('enabled', False))
        if redis_enabled:
            from services.redis_service import RedisService
            
            # Get Redis configuration
            redis_config = self.config.get('internal_services', {}).get('redis', {})
            
            # Log Redis configuration details
            self.logger.info("Redis configuration:")
            self.logger.info(f"  Host: {redis_config.get('host', 'localhost')}")
            self.logger.info(f"  Port: {redis_config.get('port', 6379)}")
            self.logger.info(f"  SSL: {'enabled' if is_true_value(redis_config.get('use_ssl', False)) else 'disabled'}")
            self.logger.info(f"  Username: {'set' if redis_config.get('username') else 'not set'}")
            self.logger.info(f"  Password: {'set' if redis_config.get('password') else 'not set'}")
            
            # Validate required Redis configuration
            if not redis_config.get('host'):
                self.logger.error("Redis host is not configured")
                app.state.redis_service = None
            else:
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
    
    async def _initialize_chat_history_service(self, app: FastAPI) -> None:
        """Initialize Chat History Service."""
        if self.verbose:
            self.logger.info("Creating Chat History Service instance...")
        from services.chat_history_service import ChatHistoryService
        app.state.chat_history_service = ChatHistoryService(
            self.config,
            app.state.database_service
        )
        self.logger.info("Initializing Chat History Service...")
        try:
            await app.state.chat_history_service.initialize()
            self.logger.info("Chat History Service initialized successfully")

            # Verify chat history service is working
            if self.verbose:
                self.logger.info("Performing Chat History Service health check...")
            health = await app.state.chat_history_service.health_check()
            if health["status"] != "healthy":
                self.logger.error(f"Chat History Service health check failed: {health}")
                app.state.chat_history_service = None
            else:
                if self.verbose:
                    self.logger.info(f"Chat History Service health check passed: {health}")
        except Exception as e:
            self.logger.error(f"Failed to initialize Chat History Service: {str(e)}")
            # Don't raise - chat history is optional
            app.state.chat_history_service = None

    async def _configure_chat_history_service(self, app: FastAPI) -> None:
        """Enable or disable chat history service based on configuration."""
        if self.chat_history_enabled:
            if self.verbose:
                self.logger.info("Chat history is enabled - initializing Chat History Service")
            await self._initialize_chat_history_service(app)
        else:
            app.state.chat_history_service = None
            self.logger.info("Chat history is disabled")
    
    async def _initialize_api_key_service(self, app: FastAPI) -> None:
        """Initialize API Key Service."""
        from services.api_key_service import ApiKeyService
        app.state.api_key_service = ApiKeyService(self.config, app.state.database_service)
        self.logger.info("Initializing API Key Service...")
        try:
            await app.state.api_key_service.initialize()
            self.logger.info("API Key Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize API Key Service: {str(e)}")
            raise

    async def _initialize_prompt_service(self, app: FastAPI) -> None:
        """Initialize Prompt Service."""
        from services.prompt_service import PromptService
        app.state.prompt_service = PromptService(self.config, app.state.database_service)
        self.logger.info("Initializing Prompt Service...")
        try:
            await app.state.prompt_service.initialize()
            self.logger.info("Prompt Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Prompt Service: {str(e)}")
            raise
    
    async def _initialize_adapter_manager(self, app: FastAPI) -> None:
        """Initialize Dynamic Adapter Manager for adapter-based routing."""
        try:
            # Always use fault tolerant adapter manager (core functionality)
            from services.fault_tolerant_adapter_manager import FaultTolerantAdapterManager
            from services.dynamic_adapter_manager import AdapterProxy
            
            # Create the fault tolerant adapter manager
            adapter_manager = FaultTolerantAdapterManager(self.config, app.state)
            
            # Create an adapter proxy that provides a retriever-like interface
            adapter_proxy = AdapterProxy(adapter_manager)
            
            # Store both the manager and proxy in app state
            app.state.adapter_manager = adapter_manager
            app.state.retriever = adapter_proxy  # LLM clients expect 'retriever'
            
            self.logger.info("Fault Tolerant Adapter Manager initialized successfully")
            
            # Log available adapters - use the base adapter manager for both types
            base_adapter_manager = adapter_manager.base_adapter_manager if hasattr(adapter_manager, 'base_adapter_manager') else adapter_manager
            available_adapters = base_adapter_manager.get_available_adapters()
            self.logger.info(f"Available adapters: {available_adapters}")
            
            # Preload all adapters in parallel to prevent sequential blocking
            if available_adapters:
                self.logger.info("Starting parallel adapter preloading...")
                preload_results = await base_adapter_manager.preload_all_adapters(timeout_per_adapter=60.0)
                
                # Log preloading results
                successful_adapters = [name for name, result in preload_results.items() if result["success"]]
                failed_adapters = [name for name, result in preload_results.items() if not result["success"]]
                
                self.logger.info(f"Adapter preloading completed: {len(successful_adapters)}/{len(available_adapters)} successful")
                if failed_adapters:
                    self.logger.warning(f"Failed to preload adapters: {failed_adapters}")
            
            # Health service registration is no longer needed with simplified fault tolerance system
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Dynamic Adapter Manager: {str(e)}")
            raise
    
    # Fault tolerance services initialization removed - now handled by FaultTolerantAdapterManager directly
    async def _shutdown_fault_tolerance_services(self, app: FastAPI) -> None:
        """Shutdown fault tolerance services."""
        try:
            # Shutdown fault tolerant adapter manager
            if hasattr(app.state, 'fault_tolerant_adapter_manager'):
                # FaultTolerantAdapterManager doesn't have cleanup method, but parallel executor might
                if hasattr(app.state.fault_tolerant_adapter_manager, 'parallel_executor'):
                    if app.state.fault_tolerant_adapter_manager.parallel_executor:
                        await app.state.fault_tolerant_adapter_manager.parallel_executor.cleanup()
                
            self.logger.info("Fault tolerance services shutdown successfully")
            
        except Exception as e:
            self.logger.error(f"Error shutting down fault tolerance services: {str(e)}")
    
    async def _initialize_logger_service(self, app: FastAPI) -> None:
        """Initialize Logger Service."""
        from services.logger_service import LoggerService
        app.state.logger_service = LoggerService(self.config)
        await app.state.logger_service.initialize_elasticsearch()
        self.logger.info("Logger Service initialized successfully")
    
    async def _initialize_metrics_service(self, app: FastAPI) -> None:
        """Initialize Metrics Service for monitoring."""
        try:
            # Check if monitoring is enabled in configuration
            monitoring_config = self.config.get('monitoring', {})
            monitoring_enabled = monitoring_config.get('enabled', True)
            
            if not monitoring_enabled:
                app.state.metrics_service = None
                self.logger.info("Metrics Service disabled by configuration")
                return
            
            from services.metrics_service import MetricsService
            app.state.metrics_service = MetricsService(self.config)
            await app.state.metrics_service.start_collection()
            self.logger.info("Metrics Service initialized successfully")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Metrics Service: {str(e)}")
            # Don't fail startup if metrics service fails
            app.state.metrics_service = None
    
    async def _initialize_clock_service(self, app: FastAPI) -> None:
        """Initialize the Clock Service."""
        clock_config = self.config.get('clock_service', {'enabled': False})
        if clock_config.get('enabled'):
            from services.clock_service import ClockService
            app.state.clock_service = ClockService(clock_config)
            self.logger.info("ClockService initialized successfully.")
        else:
            app.state.clock_service = None
            self.logger.info("ClockService is disabled in configuration.")
    
    async def _initialize_moderator_service(self, app: FastAPI) -> None:
        """Initialize Moderator Service if enabled."""
        # Get safety configuration
        safety_config = self.config.get('safety', {})
        
        # Check if safety is enabled
        safety_enabled = is_true_value(safety_config.get('enabled', False))
        
        if safety_enabled:
            from services.moderator_service import ModeratorService
            app.state.moderator_service = ModeratorService(self.config)
            self.logger.info("Initializing Moderator Service...")
            try:
                await app.state.moderator_service.initialize()
                self.logger.info("Moderator Service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize Moderator Service: {str(e)}")
                # Don't raise here - allow server to continue without Moderator
                app.state.moderator_service = None
                self.logger.warning("Continuing without Moderator Service")
        else:
            app.state.moderator_service = None
            self.logger.info("Safety is disabled, skipping Moderator Service initialization")
    
    async def _initialize_llm_guard_service(self, app: FastAPI) -> None:
        """Initialize LLM Guard Service if enabled."""
        # Get LLM Guard configuration
        llm_guard_config = self.config.get('llm_guard', {})
        
        # Check if enabled (explicit field) or if section exists (simplified structure)
        if llm_guard_config:
            if 'enabled' in llm_guard_config:
                # Structure with explicit enabled field
                is_enabled = llm_guard_config.get('enabled', False)
            else:
                # Simplified structure - if section exists, it's enabled
                is_enabled = True
        else:
            is_enabled = False
        
        if is_enabled:
            from services.llm_guard_service import LLMGuardService
            # Ensure singleton usage to avoid multiple instantiations
            app.state.llm_guard_service = LLMGuardService.get_instance(self.config)
            self.logger.info("Initializing LLM Guard Service...")
            try:
                await app.state.llm_guard_service.initialize()
                self.logger.info("LLM Guard Service initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize LLM Guard Service: {str(e)}")
                # Don't raise here - allow server to continue without LLM Guard
                app.state.llm_guard_service = None
                self.logger.warning("Continuing without LLM Guard Service")
        else:
            app.state.llm_guard_service = None
            self.logger.info("LLM Guard is disabled, skipping LLM Guard Service initialization")
    
    async def _initialize_file_processing_service(self, app: FastAPI) -> None:
        """Initialize File Processing Service for file upload API."""
        try:
            from services.file_processing.file_processing_service import FileProcessingService

            # Initialize file processing service with config and app_state for adapter-aware vision provider
            app.state.file_processing_service = FileProcessingService(
                config=self.config,
                app_state=app.state
            )
            self.logger.info("File Processing Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize File Processing Service: {str(e)}")
            # Don't raise - allow server to continue without file processing
            app.state.file_processing_service = None
            self.logger.warning("Continuing without File Processing Service")
    
    async def _initialize_reranker_service(self, app: FastAPI) -> None:
        """Initialize Reranker Service if enabled using the new unified architecture."""
        # Early return if reranker is disabled
        if not is_true_value(self.config.get('reranker', {}).get('enabled', False)):
            app.state.reranker_service = None
            self.logger.info("Reranker is disabled, skipping initialization")
            return

        # Create reranker service using the new unified architecture
        from services.reranker_service_manager import RerankingServiceManager

        try:
            # Get the provider name from config
            provider_name = self.config.get('reranker', {}).get('provider', 'ollama')

            # Create the reranker service (singleton)
            app.state.reranker_service = RerankingServiceManager.create_reranker_service(
                self.config,
                provider_name
            )

            # Initialize the reranker service
            if await app.state.reranker_service.initialize():
                self.logger.info(f"Reranker Service initialized successfully (provider: {provider_name})")
            else:
                self.logger.error("Failed to initialize Reranker Service")
                app.state.reranker_service = None

        except ValueError as e:
            self.logger.warning(f"Reranker provider not available: {str(e)}")
            app.state.reranker_service = None
        except Exception as e:
            self.logger.error(f"Failed to initialize Reranker Service: {str(e)}")
            app.state.reranker_service = None
    
    async def _initialize_vector_store_manager(self, app: FastAPI) -> None:
        """Initialize Vector Store Manager for adapters that need vector storage.
        
        This is initialized lazily - the manager is created but stores are only
        initialized when adapters actually request them.
        """
        try:
            # Check if vector stores configuration exists
            vector_stores_config = self.config.get('vector_stores', {})
            
            # Check if any vector store is enabled
            vector_stores_enabled = False
            for store_type in ['chroma', 'pinecone', 'qdrant']:
                if vector_stores_config.get(store_type, {}).get('enabled', False):
                    vector_stores_enabled = True
                    break
            
            if not vector_stores_enabled:
                app.state.vector_store_manager = None
                app.state.store_manager = None
                self.logger.info("No vector stores enabled in configuration")
                return
            
            # Import and create the store manager
            from vector_stores import get_store_manager
            
            # Look for stores configuration file
            stores_config_path = self.config.get('stores_config_path', 'config/stores.yaml')
            
            # Create the store manager (singleton)
            store_manager = get_store_manager(stores_config_path)
            app.state.vector_store_manager = store_manager  # Keep for backward compatibility
            app.state.store_manager = store_manager  # New unified name
            
            self.logger.info("Store Manager initialized (lazy loading enabled)")
            
            # Log available store types
            stats = app.state.vector_store_manager.get_statistics()
            self.logger.info(f"Available vector store types: {stats.get('available_store_types', [])}")
            
        except ImportError as e:
            self.logger.warning(f"Vector stores module not available: {e}")
            app.state.vector_store_manager = None
            app.state.store_manager = None
        except Exception as e:
            self.logger.warning(f"Failed to initialize Store Manager: {e}")
            # Don't fail startup if vector stores fail
            app.state.vector_store_manager = None
            app.state.store_manager = None
