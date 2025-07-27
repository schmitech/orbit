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
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from bson import ObjectId

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
        """Configure the main chat endpoint with MCP protocol support."""
        @app.post("/v1/chat")
        async def mcp_chat_endpoint(
            request: Request,
            chat_service = Depends(dependencies['get_chat_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key']),
            session_id: str = Depends(dependencies['validate_session_id']),
            user_id: Optional[str] = Depends(dependencies['get_user_id'])
        ):
            """
            Process an MCP protocol chat request and return a response
            
            This endpoint implements the MCP protocol using JSON-RPC 2.0 format
            with the tools/call method and chat tool.
            """
            return await self._process_mcp_request(
                request, chat_service, api_key_result, session_id, user_id
            )
    
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
        """Include admin routes, auth routes, file upload routes, and health routes."""
        from routes.admin_routes import admin_router
        from routes.file_routes import file_router
        from routes.auth_routes import auth_router
        
        # Include existing routers
        app.include_router(admin_router)
        app.include_router(file_router)
        
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
    
    async def _process_mcp_request(
        self, 
        request: Request, 
        chat_service, 
        api_key_result: tuple[str, Optional[ObjectId]], 
        session_id: str, 
        user_id: Optional[str]
    ):
        """Process MCP protocol requests."""
        adapter_name, system_prompt_id = api_key_result
        
        # Extract the API key and client info
        api_key = request.headers.get("X-API-Key")
        masked_api_key = f"***{api_key[-4:]}" if api_key else "***"
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
        
        # Enhanced verbose logging
        if is_true_value(self.config.get('general', {}).get('verbose', False)):
            self._log_request_details(session_id, client_ip, adapter_name, system_prompt_id, masked_api_key, request.method, user_id, request.headers)
        
        # Get request body
        try:
            body = await request.json()
            if is_true_value(self.config.get('general', {}).get('verbose', False)):
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
            if is_true_value(self.config.get('general', {}).get('verbose', False)):
                self.logger.debug("JSON-RPC Request Details:")
                self.logger.debug(f"  Method: {jsonrpc_request.method}")
                self.logger.debug(f"  ID: {jsonrpc_request.id}")
                self.logger.debug("  Params:")
                self.logger.debug(json.dumps(jsonrpc_request.params, indent=2))
        except Exception as e:
            self.logger.error(f"Failed to parse JSON-RPC request: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid request format: {str(e)}")
        
        return await self._handle_mcp_method(
            jsonrpc_request, chat_service, client_ip, adapter_name, 
            system_prompt_id, api_key, session_id, user_id
        )
    
    def _log_request_details(self, session_id: str, client_ip: str, adapter_name: str, 
                           system_prompt_id: Optional[ObjectId], masked_api_key: str, 
                           method: str, user_id: Optional[str], headers) -> None:
        """Log detailed request information for debugging."""
        self.logger.debug("=" * 50)
        self.logger.debug("Incoming MCP Request Details:")
        self.logger.debug(f"Session ID: {session_id}")
        self.logger.debug(f"Client IP: {client_ip}")
        self.logger.debug(f"Adapter: {adapter_name}")
        self.logger.debug(f"System Prompt ID: {system_prompt_id}")
        self.logger.debug(f"API Key: {masked_api_key}")
        self.logger.debug(f"Request Method: {method}")
        if user_id:
            self.logger.debug(f"User ID: {user_id}")
        self.logger.debug("Request Headers:")
        for header, value in headers.items():
            if header.lower() == "x-api-key":
                self.logger.debug(f"  {header}: {masked_api_key}")
            else:
                self.logger.debug(f"  {header}: {value}")
    
    async def _handle_mcp_method(
        self, 
        jsonrpc_request: MCPJsonRpcRequest, 
        chat_service, 
        client_ip: str, 
        adapter_name: str, 
        system_prompt_id: Optional[ObjectId], 
        api_key: str, 
        session_id: str, 
        user_id: Optional[str]
    ):
        """Handle MCP protocol method calls."""
        try:
            # Handle the tools/call method for chat
            if jsonrpc_request.method == "tools/call":
                return await self._handle_chat_tool(
                    jsonrpc_request, chat_service, client_ip, adapter_name,
                    system_prompt_id, api_key, session_id, user_id
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
    
    async def _handle_chat_tool(
        self, 
        jsonrpc_request: MCPJsonRpcRequest, 
        chat_service, 
        client_ip: str, 
        adapter_name: str, 
        system_prompt_id: Optional[ObjectId], 
        api_key: str, 
        session_id: str, 
        user_id: Optional[str]
    ):
        """Handle chat tool requests."""
        # Validate tool name is "chat"
        tool_name = jsonrpc_request.params.get("name", "")
        if tool_name != "chat":
            if is_true_value(self.config.get('general', {}).get('verbose', False)):
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
        
        if is_true_value(self.config.get('general', {}).get('verbose', False)):
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
        
        if is_true_value(self.config.get('general', {}).get('verbose', False)):
            self.logger.debug(f"Processing user message (length: {len(last_user_message)})")
        
        # Check for streaming parameter
        stream = arguments.get("stream", False)
        
        if is_true_value(self.config.get('general', {}).get('verbose', False)):
            self.logger.debug(f"Streaming mode: {'enabled' if stream else 'disabled'}")

        # Handle streaming vs non-streaming
        if stream:
            return await self._handle_streaming_chat(
                jsonrpc_request, chat_service, last_user_message, client_ip,
                adapter_name, system_prompt_id, api_key, session_id, user_id
            )
        else:
            return await self._handle_non_streaming_chat(
                jsonrpc_request, chat_service, last_user_message, client_ip,
                adapter_name, system_prompt_id, api_key, session_id, user_id
            )
    
    async def _handle_streaming_chat(
        self, jsonrpc_request: MCPJsonRpcRequest, chat_service, message: str,
        client_ip: str, adapter_name: str, system_prompt_id: Optional[ObjectId],
        api_key: str, session_id: str, user_id: Optional[str]
    ):
        """Handle streaming chat responses."""
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
                    message=message,
                    client_ip=client_ip,
                    adapter_name=adapter_name,
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
    
    async def _handle_non_streaming_chat(
        self, jsonrpc_request: MCPJsonRpcRequest, chat_service, message: str,
        client_ip: str, adapter_name: str, system_prompt_id: Optional[ObjectId],
        api_key: str, session_id: str, user_id: Optional[str]
    ):
        """Handle non-streaming chat responses."""
        # Process the chat message (non-streaming)
        result = await chat_service.process_chat(
            message=message,
            client_ip=client_ip,
            adapter_name=adapter_name,
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