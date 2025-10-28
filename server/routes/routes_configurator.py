"""
Route configuration utilities for the inference server.

This module handles all route setup and configuration, including:
- Endpoint registration and configuration
- Dependency injection setup
- Request validation and authentication
- Response formatting and error handling
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from bson import ObjectId
from pydantic import BaseModel

from utils import is_true_value

from utils import is_true_value
from models.schema import MCPJsonRpcRequest, MCPJsonRpcResponse


class RouteConfigurator:
    """
    Handles all aspects of route configuration for the inference server.
    
    This class is responsible for:
    - Setting up API endpoints and their dependencies
    - Configuring request validation and authentication
    - Managing response formatting and error handling
    - Providing extensible endpoint registration
    """
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        """
        Initialize the RouteConfigurator.
        
        Args:
            config: The application configuration dictionary
            logger: Logger instance for route configuration logging
        """
        self.config = config
        self.logger = logger
    
    def configure_routes(self, app: FastAPI) -> None:
        """
        Configure all routes and endpoints for the FastAPI application.
        
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
        
        Args:
            app: The FastAPI application instance
        """
        # Configure dependencies
        dependencies = self._create_dependencies()
        
        # Configure basic endpoints
        self._configure_basic_endpoints(app)
        
        # Configure main chat endpoint
        self._configure_chat_endpoint(app, dependencies)
        
        # Configure health endpoint
        self._configure_health_endpoint(app, dependencies)
        
        # Include admin router
        self._include_admin_routes(app)
        
        self.logger.info("Routes configured successfully")
    
    def _create_dependencies(self) -> Dict[str, Any]:
        """Create and return all FastAPI dependencies."""
        return {
            'get_chat_service': self._create_chat_service_dependency(),
            'get_health_service': self._create_health_service_dependency(),
            'get_api_key_service': self._create_api_key_service_dependency(),
            'get_prompt_service': self._create_prompt_service_dependency(),
            'validate_session_id': self._create_session_validator(),
            'get_user_id': self._create_user_id_extractor(),
            'get_api_key': self._create_api_key_validator()
        }
    
    def _create_chat_service_dependency(self):
        """Create chat service dependency."""
        async def get_chat_service(request: Request):
            if not hasattr(request.app.state, 'chat_service'):
                # Chat service should always be initialized by ServiceFactory
                # If it's missing, there's a configuration issue
                raise RuntimeError("Chat service not initialized. Please check server initialization.")
            return request.app.state.chat_service
        return get_chat_service
    
    def _create_health_service_dependency(self):
        """Create health service dependency."""
        async def get_health_service(request: Request):
            if not hasattr(request.app.state, 'health_service'):
                from services.health_service import HealthService
                request.app.state.health_service = HealthService(
                    config=request.app.state.config,
                    datasource_client=getattr(request.app.state, 'datasource_client', None),
                    llm_client=request.app.state.llm_client
                )
            return request.app.state.health_service
        return get_health_service
    
    def _create_api_key_service_dependency(self):
        """Create API key service dependency."""
        async def get_api_key_service(request: Request):
            return request.app.state.api_key_service
        return get_api_key_service
    
    def _create_prompt_service_dependency(self):
        """Create prompt service dependency."""
        async def get_prompt_service(request: Request):
            return request.app.state.prompt_service
        return get_prompt_service
    
    def _create_session_validator(self):
        """Create session ID validation dependency."""
        async def validate_session_id(request: Request) -> Optional[str]:
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
            session_enabled = is_true_value(request.app.state.config.get('general', {}).get('session_id', {}).get('required', False))
            
            if not session_enabled:
                # Check if chat history requires session ID
                chat_history_config = request.app.state.config.get('chat_history', {})
                chat_history_enabled = is_true_value(chat_history_config.get('enabled', True))
                session_required = chat_history_config.get('session', {}).get('required', True)
                
                if chat_history_enabled and session_required:
                    # Get session ID header name from chat history config
                    session_header = chat_history_config['session']['header_name']
                    session_id = request.headers.get(session_header)
                    
                    if not session_id or not session_id.strip():
                        # Check if auto-generate is enabled
                        if chat_history_config.get('session', {}).get('auto_generate', True):
                            # Generate a session ID
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
        return validate_session_id
    
    def _create_user_id_extractor(self):
        """Create user ID extraction dependency."""
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
        return get_user_id
    
    def _create_api_key_validator(self):
        """Create API key validation dependency."""
        async def get_api_key(request: Request) -> tuple[Optional[str], Optional[ObjectId]]:
            """
            Extract API key from request headers and validate it
            
            Args:
                request: The incoming request
                
            Returns:
                Tuple of (adapter_name, system_prompt_id) associated with the API key
            """
            # Check if inference_only is enabled
            inference_only = is_true_value(request.app.state.config.get('general', {}).get('inference_only', False))
            
            if inference_only:
                # In inference_only mode, return default values without validation
                return "default", None
            
            # Get API key from header
            header_name = request.app.state.config.get('api_keys', {}).get('header_name', 'X-API-Key')
            api_key = request.headers.get(header_name)
            
            # For health endpoint, only require API key if explicitly configured
            if request.url.path == "/health":
                require_for_health = is_true_value(request.app.state.config.get('api_keys', {}).get('require_for_health', False))
                if not require_for_health:
                    return "default", None
            
            # Check if API key service is available
            if not hasattr(request.app.state, 'api_key_service') or request.app.state.api_key_service is None:
                # If no API key service is available, allow access with default collection
                # This handles the case where API keys are disabled in config
                api_keys_enabled = is_true_value(request.app.state.config.get('api_keys', {}).get('enabled', True))
                if not api_keys_enabled or (request.url.path == "/health" and not is_true_value(request.app.state.config.get('api_keys', {}).get('require_for_health', False))):
                    return "default", None
                else:
                    raise HTTPException(status_code=503, detail="API key service is not available")
            
            # Validate API key and get adapter name and system prompt ID
            try:
                adapter_name, system_prompt_id = await request.app.state.api_key_service.get_adapter_for_api_key(api_key)
                return adapter_name, system_prompt_id
            except HTTPException as e:
                # Allow health check without API key if configured
                if (request.url.path == "/health" and 
                    not request.app.state.config.get('api_keys', {}).get('require_for_health', False)):
                    return "default", None
                raise e
        return get_api_key
    
    def _configure_basic_endpoints(self, app: FastAPI) -> None:
        """Configure basic utility endpoints."""
        # Add favicon.ico handler to return 204 No Content
        @app.get("/favicon.ico")
        async def favicon():
            return Response(status_code=204)
    
    def _configure_chat_endpoint(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure the main chat endpoint."""
        class ChatRequest(BaseModel):
            messages: List[Dict[str, str]]
            stream: bool = False

        @app.post("/v1/chat", operation_id="chat")
        async def chat_endpoint(
            chat_request: ChatRequest,
            request: Request,
            chat_service = Depends(dependencies['get_chat_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key']),
            session_id: str = Depends(dependencies['validate_session_id']),
            user_id: Optional[str] = Depends(dependencies['get_user_id'])
        ):
            """
            Process a chat request and return a response.
            This endpoint is now a standard RESTful endpoint.
            The fastapi-mcp library will expose it as an MCP tool.
            """
            adapter_name, system_prompt_id = api_key_result
            client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
            api_key = request.headers.get(self.config.get('api_keys', {}).get('header_name', 'X-API-Key'))

            # Extract the last user message
            user_messages = [m for m in chat_request.messages if m.get("role") == "user"]
            if not user_messages:
                raise HTTPException(status_code=400, detail="No user message found in request")
            
            last_user_message = user_messages[-1].get("content", "")

            if chat_request.stream:
                async def stream_generator():
                    async for chunk in chat_service.process_chat_stream(
                        message=last_user_message,
                        client_ip=client_ip,
                        adapter_name=adapter_name,
                        system_prompt_id=system_prompt_id,
                        api_key=api_key,
                        session_id=session_id,
                        user_id=user_id
                    ):
                        yield chunk

                # Return StreamingResponse with headers to prevent buffering
                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",  # Disable nginx buffering if behind proxy
                    }
                )
            else:
                result = await chat_service.process_chat(
                    message=last_user_message,
                    client_ip=client_ip,
                    adapter_name=adapter_name,
                    system_prompt_id=system_prompt_id,
                    api_key=api_key,
                    session_id=session_id,
                    user_id=user_id
                )
                return result
    
    def _configure_health_endpoint(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure the health check endpoint."""
        @app.get("/health")
        async def health_check(
            health_service = Depends(dependencies['get_health_service'])
        ):
            """Check the health of the application and its dependencies"""
            health = await health_service.get_health_status()
            return health
    
    def _include_admin_routes(self, app: FastAPI) -> None:
        """Include admin routes, auth routes, and health routes."""
        from routes.admin_routes import admin_router
        from routes.auth_routes import auth_router
        
        # Include existing routers
        app.include_router(admin_router)
        
        # Include auth router if auth is enabled
        auth_enabled = is_true_value(self.config.get('auth', {}).get('enabled', False))
        if auth_enabled:
            app.include_router(auth_router)
            self.logger.info("Authentication routes registered")
        else:
            self.logger.info("Authentication routes skipped (auth disabled)")
        
        # Include health routes (always enabled as core functionality)
        from routes.health_routes import create_health_router
        health_router = create_health_router()
        app.include_router(health_router)
        self.logger.info("Health routes registered")
        
        # Include dashboard routes for monitoring
        try:
            from routes.dashboard_routes import create_dashboard_router
            dashboard_router = create_dashboard_router()
            app.include_router(dashboard_router)
            self.logger.info("Dashboard routes registered")
        except Exception as e:
            self.logger.warning(f"Failed to register dashboard routes: {e}")
    
    