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


class ServiceFactory:
    """
    Factory class for managing service initialization and lifecycle.
    
    This class is responsible for:
    - Service discovery and instantiation
    - Dependency injection between services
    - Mode-aware initialization (inference-only vs full mode)
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
        self.inference_only = is_true_value(config.get('general', {}).get('inference_only', False))
        self.chat_history_enabled = is_true_value(config.get('chat_history', {}).get('enabled', False))
        self.verbose = is_true_value(config.get('general', {}).get('verbose', False))
        
        # Fault tolerance is always enabled as core functionality
        self.fault_tolerance_enabled = True
        
        # Log the mode detection for debugging (only when verbose)
        if self.verbose:
            self.logger.info(f"ServiceFactory initialized - inference_only={self.inference_only}, chat_history_enabled={self.chat_history_enabled}")
    
    async def initialize_all_services(self, app: FastAPI) -> None:
        """Initialize all services required by the application."""
        try:
            if self.verbose:
                self.logger.info(f"Starting service initialization - inference_only={self.inference_only}, chat_history_enabled={self.chat_history_enabled}")
            
            # Initialize core services (MongoDB, Redis) based on mode
            await self._initialize_core_services(app)
            
            # Initialize mode-specific services
            if self.inference_only:
                if self.verbose:
                    self.logger.info("Initializing inference-only mode services")
                await self._initialize_inference_only_services(app)
            else:
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
        # Check if authentication is enabled
        auth_enabled = is_true_value(self.config.get('auth', {}).get('enabled', False))
        
        # Initialize MongoDB service if needed
        await self._initialize_mongodb_if_needed(app, auth_enabled)
        
        # Initialize Redis service if enabled
        await self._initialize_redis_service(app)
        
        # Initialize authentication service (requires MongoDB to be initialized first)
        await self._initialize_auth_service_if_available(app, auth_enabled)
    
    async def _initialize_mongodb_if_needed(self, app: FastAPI, auth_enabled: bool) -> None:
        """Initialize MongoDB service if required by current configuration."""
        # MongoDB is required when:
        # - inference_only is false (for retriever adapters)
        # - OR auth is enabled (for authentication)
        # - OR chat_history is enabled (for chat history storage)
        mongodb_required = (
            not self.inference_only or 
            auth_enabled or 
            self.chat_history_enabled
        )
        
        if mongodb_required:
            await self._initialize_mongodb_service(app)
            
            # Log the specific reason(s) for MongoDB initialization
            reasons = []
            if not self.inference_only:
                reasons.append("retriever adapters")
            if auth_enabled:
                reasons.append("authentication")
            if self.chat_history_enabled:
                reasons.append("chat history")
            
            self.logger.info(f"MongoDB initialized for: {', '.join(reasons)}")
        else:
            app.state.mongodb_service = None
            self.logger.info("Skipping MongoDB initialization - inference_only=true, auth disabled, and chat_history disabled")
    
    async def _initialize_auth_service_if_available(self, app: FastAPI, auth_enabled: bool) -> None:
        """Initialize authentication service if MongoDB is available and auth is enabled."""
        if app.state.mongodb_service is not None:
            await self._initialize_auth_service(app)
        else:
            # Only log warning if auth is actually enabled but MongoDB is not available
            if auth_enabled:
                self.logger.warning("Auth is enabled but MongoDB service not available - auth service will be disabled")
            else:
                self.logger.info("Auth service disabled in configuration")
    
    async def _initialize_auth_service(self, app: FastAPI) -> None:
        """Initialize the authentication service"""
        auth_enabled = is_true_value(self.config.get('auth', {}).get('enabled', False))
        
        if not auth_enabled:
            self.logger.info("Authentication service disabled in configuration")
            app.state.auth_service = None
            return
        
        try:
            # Use the shared MongoDB service if available
            mongodb_service = getattr(app.state, 'mongodb_service', None)
            
            # Initialize auth service
            from services.auth_service import AuthService
            auth_service = AuthService(self.config, mongodb_service)
            await auth_service.initialize()
            
            app.state.auth_service = auth_service
            self.logger.info("Authentication service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize authentication service: {str(e)}")
            # Don't fail the entire startup if auth fails, but log it prominently
            app.state.auth_service = None
    
    async def _initialize_inference_only_services(self, app: FastAPI) -> None:
        """Initialize services specific to inference-only mode."""
        self.logger.info("Inference-only mode enabled - skipping unnecessary service initialization")
        
        # Set services to None for inference-only mode
        app.state.retriever = None
        app.state.adapter_manager = None
        app.state.embedding_service = None
        app.state.prompt_service = None
        app.state.reranker_service = None
        
        # Initialize API key service only if MongoDB is available and auth is disabled
        # (API key service is used for admin operations when auth is disabled but MongoDB is available)
        auth_enabled = is_true_value(self.config.get('auth', {}).get('enabled', False))
        if not auth_enabled and app.state.mongodb_service is not None:
            self.logger.info("Authentication disabled but MongoDB available - initializing API key service for admin operations")
            await self._initialize_api_key_service(app)
        else:
            app.state.api_key_service = None
            if not auth_enabled:
                self.logger.info("Authentication disabled and MongoDB not available - skipping API key service")
            else:
                self.logger.info("Authentication enabled - API key service not needed in inference-only mode")
        
        # Initialize Chat History Service if enabled
        if self.chat_history_enabled:
            if self.verbose:
                self.logger.info("Chat history is enabled - initializing Chat History Service")
            await self._initialize_chat_history_service(app)
        else:
            app.state.chat_history_service = None
            self.logger.info("Chat history is disabled")
        
        self.logger.info("Inference-only mode service initialization complete")
    
    async def _initialize_full_mode_services(self, app: FastAPI) -> None:
        """Initialize services specific to full RAG mode."""
        # Initialize API Key Service
        await self._initialize_api_key_service(app)
        
        # Initialize Prompt Service
        await self._initialize_prompt_service(app)
        
        # Initialize Dynamic Adapter Manager
        await self._initialize_adapter_manager(app)
        
        # Chat history is not initialized in full mode
        app.state.chat_history_service = None
        self.logger.info("Chat history is not in inference-only mode")
    
    async def _initialize_shared_services(self, app: FastAPI) -> None:
        """Initialize services that are used in both modes."""
        # Initialize Logger Service (always needed)
        await self._initialize_logger_service(app)
        
        # Initialize Moderator Service if enabled
        await self._initialize_moderator_service(app)
        
        # Initialize LLM Guard Service if enabled
        await self._initialize_llm_guard_service(app)
        
        # Initialize Reranker Service if enabled and not in inference-only mode
        if not self.inference_only and is_true_value(self.config.get('reranker', {}).get('enabled', False)):
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
            prompt_service=getattr(app.state, 'prompt_service', None)
        )
        # Initialize the pipeline provider
        await app.state.chat_service.initialize()
        self.logger.info("Initialized pipeline-based chat service")
        
        # Initialize Health Service
        from services.health_service import HealthService
        app.state.health_service = HealthService(
            config=self.config,
            datasource_client=getattr(app.state, 'datasource_client', None),
            llm_client=getattr(app.state, 'llm_client', None)  # May be None in pipeline mode
        )
        
        self.logger.info("Dependent services initialized successfully")
    
    async def _initialize_mongodb_service(self, app: FastAPI) -> None:
        """Initialize MongoDB service."""
        from services.mongodb_service import MongoDBService
        app.state.mongodb_service = MongoDBService(self.config)
        self.logger.info("Initializing shared MongoDB service...")
        try:
            await app.state.mongodb_service.initialize()
            self.logger.info("Shared MongoDB service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize shared MongoDB service: {str(e)}")
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
            app.state.mongodb_service
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
    
    async def _initialize_api_key_service(self, app: FastAPI) -> None:
        """Initialize API Key Service."""
        from services.api_key_service import ApiKeyService
        app.state.api_key_service = ApiKeyService(self.config, app.state.mongodb_service)
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
        app.state.prompt_service = PromptService(self.config, app.state.mongodb_service)
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
                preload_results = await base_adapter_manager.preload_all_adapters(timeout_per_adapter=25.0)
                
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
            app.state.llm_guard_service = LLMGuardService(self.config)
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
    
    async def _initialize_reranker_service(self, app: FastAPI) -> None:
        """Initialize Reranker Service if enabled."""
        # Early return if reranker is disabled
        if not is_true_value(self.config.get('reranker', {}).get('enabled', False)):
            app.state.reranker_service = None
            self.logger.info("Reranker is disabled, skipping initialization")
            return

        # Create reranker service
        from rerankers import RerankerFactory
        app.state.reranker_service = RerankerFactory.create(self.config)
        
        # Early return if no reranker provider configured
        if not app.state.reranker_service:
            self.logger.warning("No reranker provider configured or provider not supported")
            app.state.reranker_service = None
            return

        # Initialize the reranker service
        try:
            if await app.state.reranker_service.initialize():
                self.logger.info("Reranker Service initialized successfully")
            else:
                self.logger.error("Failed to initialize Reranker Service")
                app.state.reranker_service = None
        except Exception as e:
            self.logger.error(f"Failed to initialize Reranker Service: {str(e)}")
            app.state.reranker_service = None