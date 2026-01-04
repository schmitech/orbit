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
from typing import Optional, Dict, Any, List, Tuple
from fastapi import FastAPI, Request, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from bson import ObjectId
from pydantic import BaseModel

from utils import is_true_value
from services.stream_registry import stream_registry
from models.schema import MCPJsonRpcRequest, MCPJsonRpcResponse
from ai_services.services.inference_service import OpenAIResponseFormatter

logger = logging.getLogger(__name__)


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

        # Configure stop streaming endpoint
        self._configure_stop_endpoint(app, dependencies)

        # Configure autocomplete endpoint
        self._configure_autocomplete_endpoint(app, dependencies)

        # Configure health endpoint
        self._configure_health_endpoint(app, dependencies)
        
        # Configure thread endpoints
        self._configure_thread_endpoints(app, dependencies)
        
        # Include admin router
        self._include_admin_routes(app)
        
        logger.info("Routes configured successfully")
    
    def _create_dependencies(self) -> Dict[str, Any]:
        """Create and return all FastAPI dependencies."""
        return {
            'get_chat_service': self._create_chat_service_dependency(),
            'get_health_service': self._create_health_service_dependency(),
            'get_api_key_service': self._create_api_key_service_dependency(),
            'get_prompt_service': self._create_prompt_service_dependency(),
            'get_thread_service': self._create_thread_service_dependency(),
            'get_autocomplete_service': self._create_autocomplete_service_dependency(),
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
    
    def _create_thread_service_dependency(self):
        """Create thread service dependency."""
        async def get_thread_service(request: Request):
            if not hasattr(request.app.state, 'thread_service'):
                # Initialize thread service if not already initialized
                from services.thread_service import ThreadService
                # Use shared thread_dataset_service if available
                thread_dataset_service = getattr(request.app.state, 'thread_dataset_service', None)
                database_service = getattr(request.app.state, 'database_service', None)
                thread_service = ThreadService(
                    request.app.state.config,
                    database_service=database_service,
                    dataset_service=thread_dataset_service
                )
                await thread_service.initialize()
                request.app.state.thread_service = thread_service
            return request.app.state.thread_service
        return get_thread_service

    def _create_autocomplete_service_dependency(self):
        """Create autocomplete service dependency."""
        async def get_autocomplete_service(request: Request):
            if not hasattr(request.app.state, 'autocomplete_service'):
                # Initialize autocomplete service if not already initialized
                from services.autocomplete_service import AutocompleteService
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
                redis_service = getattr(request.app.state, 'redis_service', None)
                autocomplete_service = AutocompleteService(
                    request.app.state.config,
                    adapter_manager=adapter_manager,
                    redis_service=redis_service
                )
                request.app.state.autocomplete_service = autocomplete_service
            return request.app.state.autocomplete_service
        return get_autocomplete_service
    
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
                            session_id = str(uuid.uuid4())
                            logger.debug("Auto-generated session ID: %s", session_id)
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
                # Get adapter manager from app state to check live configs (respects hot-reload)
                adapter_manager = getattr(request.app.state, 'adapter_manager', None)
                adapter_name, system_prompt_id = await request.app.state.api_key_service.get_adapter_for_api_key(api_key, adapter_manager)
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
            file_ids: Optional[List[str]] = None  # Optional list of file IDs for file context
            thread_id: Optional[str] = None  # Optional thread ID for follow-up questions
            # Audio input parameters (for STT)
            audio_input: Optional[str] = None  # Base64-encoded audio data for STT
            audio_format: Optional[str] = None  # Audio format (mp3, wav, etc.)
            language: Optional[str] = None  # Language code for STT (e.g., "en-US")
            # Audio output parameters (for TTS)
            return_audio: Optional[bool] = None  # Whether to return audio response (TTS)
            tts_voice: Optional[str] = None  # Voice for TTS (e.g., "alloy", "echo" for OpenAI)
            source_language: Optional[str] = None  # Source language for translation
            target_language: Optional[str] = None  # Target language for translation

        class OpenAIChatCompletionRequest(BaseModel):
            model: Optional[str] = None
            messages: List[Dict[str, Any]]
            stream: bool = False
            temperature: Optional[float] = None
            max_tokens: Optional[int] = None
            top_p: Optional[float] = None
            user: Optional[str] = None

            class Config:
                extra = "allow"

        def _prepare_chat_parameters(chat_request: Any) -> Tuple[str, Dict[str, Any]]:
            """Extract the last user message and shared kwargs for chat processing."""
            messages = getattr(chat_request, "messages", None) or []
            user_messages = [m for m in messages if m.get("role") == "user"]
            if not user_messages:
                raise HTTPException(status_code=400, detail="No user message found in request")

            last_user_message = user_messages[-1].get("content", "")

            payload = {
                "file_ids": getattr(chat_request, "file_ids", None) or [],
                "thread_id": getattr(chat_request, "thread_id", None),
                "audio_input": getattr(chat_request, "audio_input", None),
                "audio_format": getattr(chat_request, "audio_format", None),
                "language": getattr(chat_request, "language", None),
                "return_audio": getattr(chat_request, "return_audio", None),
                "tts_voice": getattr(chat_request, "tts_voice", None),
                "source_language": getattr(chat_request, "source_language", None),
                "target_language": getattr(chat_request, "target_language", None),
            }

            return last_user_message, payload

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

            last_user_message, payload_kwargs = _prepare_chat_parameters(chat_request)
            return_audio = payload_kwargs.get("return_audio")
            tts_voice = payload_kwargs.get("tts_voice")

            # Debug logging for tts_voice
            if return_audio and tts_voice:
                logger.info(f"API Request received tts_voice: {tts_voice} for adapter: {adapter_name}")

            if chat_request.stream:
                # Generate unique request_id for this stream
                request_id = str(uuid.uuid4())

                # Register the stream and get cancellation event
                cancel_event = await stream_registry.register(
                    session_id=session_id,
                    request_id=request_id,
                    adapter_name=adapter_name
                )

                async def stream_generator():
                    try:
                        # Send request_id as first chunk so client can use it for cancellation
                        yield f"data: {json.dumps({'request_id': request_id})}\n\n"

                        async for chunk in chat_service.process_chat_stream(
                            message=last_user_message,
                            client_ip=client_ip,
                            adapter_name=adapter_name,
                            system_prompt_id=system_prompt_id,
                            api_key=api_key,
                            session_id=session_id,
                            user_id=user_id,
                            cancel_event=cancel_event,
                            **payload_kwargs
                        ):
                            # Check for cancellation before yielding each chunk
                            if cancel_event.is_set():
                                logger.debug(f"[CHAT_STREAM] >>> CANCELLATION DETECTED in stream loop <<< session={session_id}, request={request_id}")
                                break
                            yield chunk
                    finally:
                        # Always unregister when stream ends
                        await stream_registry.unregister(session_id, request_id)

                # Return StreamingResponse with headers to prevent buffering
                return StreamingResponse(
                    stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",  # Disable nginx buffering if behind proxy
                        "X-Request-ID": request_id,  # Include request_id in headers
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
                    user_id=user_id,
                    **payload_kwargs
                )
                return result

        @app.post("/v1/chat/completions", operation_id="chat_completions")
        async def openai_chat_completions(
            chat_request: OpenAIChatCompletionRequest,
            request: Request,
            chat_service = Depends(dependencies['get_chat_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key']),
            session_id: str = Depends(dependencies['validate_session_id']),
            user_id: Optional[str] = Depends(dependencies['get_user_id'])
        ):
            """
            OpenAI-compatible chat completions endpoint so the official OpenAI
            Python SDK (and other compatible clients) can talk to ORBIT.
            """
            adapter_name, system_prompt_id = api_key_result
            client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
            api_key = request.headers.get(self.config.get('api_keys', {}).get('header_name', 'X-API-Key'))

            last_user_message, payload_kwargs = _prepare_chat_parameters(chat_request)
            formatter = OpenAIResponseFormatter(
                model=chat_request.model,
                provider=adapter_name
            )

            if chat_request.stream:
                async def openai_stream_generator():
                    stream_started = False
                    async for chunk in chat_service.process_chat_stream(
                        message=last_user_message,
                        client_ip=client_ip,
                        adapter_name=adapter_name,
                        system_prompt_id=system_prompt_id,
                        api_key=api_key,
                        session_id=session_id,
                        user_id=user_id,
                        **payload_kwargs
                    ):
                        if not chunk or not chunk.startswith("data:"):
                            continue

                        chunk_payload = chunk[6:].strip()
                        if not chunk_payload:
                            continue

                        try:
                            chunk_data = json.loads(chunk_payload)
                        except json.JSONDecodeError:
                            continue

                        if "error" in chunk_data:
                            error_chunk = formatter.build_stream_chunk(
                                finish_reason="error",
                                orbit_extension={"error": chunk_data["error"]}
                            )
                            yield f"data: {json.dumps(error_chunk)}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                        if chunk_data.get("done"):
                            orbit_extension = formatter.build_orbit_extension(
                                sources=chunk_data.get("sources"),
                                metadata=chunk_data.get("metadata"),
                                audio=chunk_data.get("audio"),
                                audio_format=chunk_data.get("audioFormat"),
                                threading=chunk_data.get("threading"),
                                extra={
                                    "total_audio_chunks": chunk_data.get("total_audio_chunks")
                                } if chunk_data.get("total_audio_chunks") is not None else None
                            )
                            final_chunk = formatter.build_stream_chunk(
                                finish_reason="stop",
                                orbit_extension=orbit_extension
                            )
                            yield f"data: {json.dumps(final_chunk)}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                        orbit_extension = None
                        if "audio_chunk" in chunk_data:
                            orbit_extension = formatter.build_orbit_extension(
                                extra={
                                    "audio_chunk": chunk_data["audio_chunk"],
                                    "audioFormat": chunk_data.get("audioFormat")
                                }
                            )

                        if "response" in chunk_data and chunk_data["response"] is not None:
                            chunk_dict = formatter.build_stream_chunk(
                                content=chunk_data["response"],
                                role="assistant" if not stream_started else None,
                                orbit_extension=orbit_extension
                            )
                            stream_started = True
                            yield f"data: {json.dumps(chunk_dict)}\n\n"
                        elif orbit_extension:
                            chunk_dict = formatter.build_stream_chunk(
                                orbit_extension=orbit_extension
                            )
                            yield f"data: {json.dumps(chunk_dict)}\n\n"

                    # If the upstream generator exits without emitting a done chunk,
                    # still terminate the SSE stream so clients do not hang forever.
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    openai_stream_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    }
                )

            result = await chat_service.process_chat(
                message=last_user_message,
                client_ip=client_ip,
                adapter_name=adapter_name,
                system_prompt_id=system_prompt_id,
                api_key=api_key,
                session_id=session_id,
                user_id=user_id,
                **payload_kwargs
            )

            if "error" in result:
                raise HTTPException(status_code=500, detail=result["error"])

            return formatter.build_completion_response(
                content=result.get("response", "") or "",
                metadata=result.get("metadata"),
                sources=result.get("sources", []),
                audio=result.get("audio"),
                audio_format=result.get("audio_format"),
                threading=result.get("threading")
            )

    def _configure_stop_endpoint(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure the stop streaming endpoint."""

        class StopStreamRequest(BaseModel):
            """Request model for stopping a stream."""
            session_id: str
            request_id: str

        @app.post("/v1/chat/stop", operation_id="stop_chat")
        async def stop_chat_stream(
            request: Request,
            stop_request: StopStreamRequest,
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key'])
        ) -> Dict[str, Any]:
            """
            Stop an active streaming request.

            Args:
                stop_request: Contains session_id and request_id to identify the stream

            Returns:
                Status indicating whether the stream was found and cancelled
            """
            logger.debug(f"[STOP_ENDPOINT] Received stop request: session={stop_request.session_id}, request={stop_request.request_id}")

            success = await stream_registry.cancel(
                session_id=stop_request.session_id,
                request_id=stop_request.request_id
            )

            if success:
                logger.debug(f"[STOP_ENDPOINT] >>> STOP SUCCESS <<< session={stop_request.session_id}, request={stop_request.request_id}")
                return {
                    "status": "cancelled",
                    "message": "Stream cancellation requested",
                    "session_id": stop_request.session_id,
                    "request_id": stop_request.request_id
                }
            else:
                return {
                    "status": "not_found",
                    "message": "Stream not found or already completed",
                    "session_id": stop_request.session_id,
                    "request_id": stop_request.request_id
                }

    def _configure_autocomplete_endpoint(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure the autocomplete suggestions endpoint."""
        from fastapi import Query

        class AutocompleteResponse(BaseModel):
            suggestions: List[Dict[str, str]]
            query: str

        @app.get("/v1/autocomplete", operation_id="autocomplete", response_model=AutocompleteResponse)
        async def autocomplete_endpoint(
            request: Request,
            q: str = Query(..., min_length=3, description="Query prefix to match"),
            limit: int = Query(5, ge=1, le=10, description="Maximum number of suggestions"),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key']),
            autocomplete_service = Depends(dependencies['get_autocomplete_service'])
        ) -> AutocompleteResponse:
            """
            Get autocomplete suggestions based on query prefix.

            This endpoint returns query suggestions based on nl_examples from
            intent adapter templates. Useful for helping users discover
            available queries.

            Args:
                q: The query prefix to match (minimum 3 characters)
                limit: Maximum number of suggestions to return (1-10, default 5)

            Returns:
                AutocompleteResponse with list of suggestions
            """
            # Check if autocomplete is disabled at config level
            autocomplete_config = request.app.state.config.get('autocomplete', {})
            if not autocomplete_config.get('enabled', True):
                return AutocompleteResponse(suggestions=[], query=q)

            adapter_name, _ = api_key_result

            try:
                suggestions = await autocomplete_service.get_suggestions(
                    query=q,
                    adapter_name=adapter_name,
                    limit=limit
                )

                return AutocompleteResponse(
                    suggestions=[{"text": s.text} for s in suggestions],
                    query=q
                )

            except Exception as e:
                logger.warning(f"Autocomplete error: {e}")
                # Return empty suggestions rather than error - autocomplete is non-critical
                return AutocompleteResponse(suggestions=[], query=q)

    def _configure_health_endpoint(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure the health check endpoint."""
        @app.get("/health")
        async def health_check(
            health_service = Depends(dependencies['get_health_service'])
        ):
            """Check the health of the application and its dependencies"""
            health = await health_service.get_health_status()
            return health
    
    def _configure_thread_endpoints(self, app: FastAPI, dependencies: Dict[str, Any]) -> None:
        """Configure thread management endpoints."""
        
        class CreateThreadRequest(BaseModel):
            message_id: str
            session_id: str
        
        @app.post("/api/threads", operation_id="create_thread")
        async def create_thread(
            request_body: CreateThreadRequest,
            request: Request,
            thread_service = Depends(dependencies['get_thread_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key']),
            session_id: str = Depends(dependencies['validate_session_id'])
        ):
            """
            Create a conversation thread from a parent message.
            
            This endpoint creates a thread that allows follow-up questions
            on retrieved datasets without re-querying the database.
            """
            adapter_name, _ = api_key_result
            api_key = request.headers.get(self.config.get('api_keys', {}).get('header_name', 'X-API-Key'))
            
            # Get the parent message from chat history using database service
            chat_history_service = getattr(request.app.state, 'chat_history_service', None)
            if not chat_history_service:
                raise HTTPException(status_code=503, detail="Chat history service is not available")
            
            # Get parent message from database
            database_service = chat_history_service.database_service
            collection_name = chat_history_service.collection_name
            
            # Query using _id (database service will convert to 'id' for SQLite automatically)
            parent_message = await database_service.find_one(
                collection_name,
                {'_id': request_body.message_id, 'session_id': request_body.session_id}
            )
            
            if not parent_message:
                raise HTTPException(status_code=404, detail="Parent message not found")
            
            # Check if message is from assistant
            if parent_message.get('role') != 'assistant':
                raise HTTPException(status_code=400, detail="Parent message must be from assistant")
            
            # Extract query context and raw results from message metadata
            metadata = parent_message.get('metadata', {})
            if not isinstance(metadata, dict):
                try:
                    import json
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata)
                    elif hasattr(metadata, '__dict__'):
                        metadata = vars(metadata)
                    else:
                        metadata = {}
                except:
                    metadata = {}
            
            # Get retrieved docs from metadata (stored by pipeline)
            # The metadata might be stored as metadata_json in SQLite
            if 'metadata_json' in parent_message:
                try:
                    import json
                    metadata_json = json.loads(parent_message['metadata_json'])
                    metadata.update(metadata_json)
                except:
                    pass
            
            retrieved_docs = metadata.get('retrieved_docs', [])
            if not retrieved_docs:
                raise HTTPException(status_code=400, detail="Parent message does not contain retrieved data")
            
            # Extract query context from metadata
            query_context = {
                'original_query': metadata.get('original_query', ''),
                'adapter_name': adapter_name,
                'template_id': metadata.get('template_id'),
                'parameters': metadata.get('parameters_used', {})
            }
            
            # Create thread
            try:
                thread_info = await thread_service.create_thread(
                    parent_message_id=request_body.message_id,
                    parent_session_id=request_body.session_id,
                    adapter_name=adapter_name,
                    query_context=query_context,
                    raw_results=retrieved_docs
                )
                return thread_info
            except Exception as e:
                logger.error(f"Failed to create thread: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create thread: {str(e)}")
        
        @app.get("/api/threads/{thread_id}", operation_id="get_thread")
        async def get_thread(
            thread_id: str,
            request: Request,
            thread_service = Depends(dependencies['get_thread_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key'])
        ):
            """Get thread information by thread ID."""
            thread_info = await thread_service.get_thread(thread_id)
            if not thread_info:
                raise HTTPException(status_code=404, detail="Thread not found or expired")
            return thread_info
        
        @app.delete("/api/threads/{thread_id}", operation_id="delete_thread")
        async def delete_thread(
            thread_id: str,
            request: Request,
            thread_service = Depends(dependencies['get_thread_service']),
            api_key_result: tuple[str, Optional[ObjectId]] = Depends(dependencies['get_api_key'])
        ):
            """Delete a thread and its associated dataset."""
            result = await thread_service.delete_thread(thread_id)
            if not result:
                raise HTTPException(status_code=404, detail="Thread not found")
            return {"status": "success", "message": "Thread deleted", "thread_id": thread_id}
    
    def _include_admin_routes(self, app: FastAPI) -> None:
        """Include admin routes, auth routes, and health routes."""
        from routes.admin_routes import admin_router
        from routes.auth_routes import auth_router
        
        # Include existing routers
        app.include_router(admin_router)

        # Authentication is always enabled - include auth router
        app.include_router(auth_router)
        logger.info("Authentication routes registered")

        # Include health routes (always enabled as core functionality)
        from routes.health_routes import create_health_router
        health_router = create_health_router()
        app.include_router(health_router)
        logger.info("Health routes registered")
        
        # Include dashboard routes for monitoring
        try:
            from routes.dashboard_routes import create_dashboard_router
            dashboard_router = create_dashboard_router()
            app.include_router(dashboard_router)
            logger.info("Dashboard routes registered")
        except Exception as e:
            logger.warning(f"Failed to register dashboard routes: {e}")
        
        # Include file routes for file upload and management
        try:
            from routes.file_routes import create_file_router
            file_router = create_file_router()
            app.include_router(file_router)
            logger.info("File routes registered")
        except Exception as e:
            logger.warning(f"Failed to register file routes: {e}")

        # Include voice routes for real-time voice conversations
        try:
            from routes.voice_routes import router as voice_router
            app.include_router(voice_router)
            logger.info("Voice routes registered")
        except Exception as e:
            logger.warning(f"Failed to register voice routes: {e}")
    
    
