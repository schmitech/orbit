"""
Voice Routes

WebSocket endpoints for real-time voice conversations with AI.

Supports two handler types:
- VoiceWebSocketHandler: Traditional cascade (STT -> LLM -> TTS)
- PersonaPlexWebSocketHandler: Full-duplex speech-to-speech (PersonaPlex)

Handler selection is automatic based on adapter type:
- type: "speech_to_speech" -> PersonaPlexWebSocketHandler
- other types -> VoiceWebSocketHandler
"""

import logging
from typing import Optional, Tuple, Any, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request, Query, HTTPException
from services.chat_handlers.voice_websocket_handler import VoiceWebSocketHandler

logger = logging.getLogger(__name__)

router = APIRouter()


def get_chat_service(request: Request):
    """Get chat service from app state."""
    chat_service = getattr(request.app.state, 'chat_service', None)
    if not chat_service:
        raise HTTPException(status_code=503, detail="Chat service not available")
    return chat_service


def get_config(request: Request):
    """Get config from app state."""
    config = getattr(request.app.state, 'config', None)
    if not config:
        raise HTTPException(status_code=503, detail="Configuration not available")
    return config


async def validate_adapter(adapter_name: str, request: Request) -> Dict[str, Any]:
    """
    Validate that the adapter exists and supports real-time audio.

    Args:
        adapter_name: Adapter name to validate
        request: FastAPI request

    Returns:
        Adapter configuration dictionary

    Raises:
        HTTPException: If adapter is invalid or doesn't support real-time audio
    """
    # Get adapter manager from chat service
    chat_service = get_chat_service(request)

    if not hasattr(chat_service, 'context_builder') or not chat_service.context_builder:
        raise HTTPException(status_code=500, detail="Chat service not properly initialized")

    adapter_manager = chat_service.context_builder.adapter_manager
    if not adapter_manager:
        raise HTTPException(status_code=500, detail="Adapter manager not available")

    # Get adapter config
    adapter_config = adapter_manager.get_adapter_config(adapter_name)
    if not adapter_config:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter_name}' not found")

    # Check if adapter supports real-time audio
    capabilities = adapter_config.get('capabilities', {})
    supports_realtime_audio = capabilities.get('supports_realtime_audio', False)

    if not supports_realtime_audio:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{adapter_name}' does not support real-time audio conversations"
        )

    # Check adapter type
    adapter_type = adapter_config.get('type', '')

    # For speech_to_speech adapters (PersonaPlex), audio_provider is not required
    if adapter_type == 'speech_to_speech':
        logger.info(
            f"Adapter validation successful: {adapter_name}, "
            f"type: speech_to_speech (full-duplex)"
        )
        return adapter_config

    # For other adapter types, audio provider must be configured
    audio_provider = adapter_config.get('audio_provider')
    if not audio_provider:
        # Also check stt_provider/tts_provider for voice adapters
        stt_provider = adapter_config.get('stt_provider')
        tts_provider = adapter_config.get('tts_provider')
        if not (stt_provider or tts_provider):
            raise HTTPException(
                status_code=400,
                detail=f"Adapter '{adapter_name}' has no audio provider configured"
            )
        audio_provider = f"stt:{stt_provider or 'none'}, tts:{tts_provider or 'none'}"

    logger.info(
        f"Adapter validation successful: {adapter_name}, "
        f"audio provider: {audio_provider}"
    )

    return adapter_config


async def _create_personaplex_handler(
    websocket: WebSocket,
    adapter_name: str,
    adapter_config: Dict[str, Any],
    config: Dict[str, Any],
    session_id: Optional[str],
    user_id: Optional[str],
    prompt_service: Optional[Any] = None,
    system_prompt_id: Optional[str] = None,
    clock_service: Optional[Any] = None
):
    """
    Create and initialize a PersonaPlex WebSocket handler.

    Args:
        websocket: WebSocket connection
        adapter_name: Name of the adapter
        adapter_config: Adapter configuration
        config: Global configuration
        session_id: Optional session ID
        user_id: Optional user ID
        prompt_service: Optional prompt service for dynamic prompt loading
        system_prompt_id: Optional system prompt ID from API key
        clock_service: Optional clock service for time awareness

    Returns:
        Initialized PersonaPlexWebSocketHandler
    """
    from services.chat_handlers.personaplex_websocket_handler import PersonaPlexWebSocketHandler
    from services.personaplex_knowledge_service import PersonaPlexKnowledgeService
    from ai_services.factory import AIServiceFactory
    from ai_services.base import ServiceType

    # Get or create PersonaPlex service
    try:
        personaplex_service = AIServiceFactory.create_service(
            ServiceType.SPEECH_TO_SPEECH,
            'personaplex',
            config
        )

        # Initialize service if needed
        if not personaplex_service.initialized:
            success = await personaplex_service.initialize()
            if not success:
                raise RuntimeError("Failed to initialize PersonaPlex service")

    except Exception as e:
        logger.error(f"Failed to create PersonaPlex service: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"PersonaPlex service unavailable: {str(e)}"
        )

    # Create knowledge service if adapter has knowledge config with facts_file
    knowledge_service = None
    knowledge_config = adapter_config.get('knowledge', {})
    if knowledge_config.get('enabled', False) and knowledge_config.get('facts_file'):
        logger.info(f"Creating knowledge service for adapter '{adapter_name}'")
        knowledge_service = PersonaPlexKnowledgeService(config)

    # Create handler
    handler = PersonaPlexWebSocketHandler(
        websocket=websocket,
        personaplex_service=personaplex_service,
        adapter_name=adapter_name,
        adapter_config=adapter_config,
        config=config,
        session_id=session_id,
        user_id=user_id,
        prompt_service=prompt_service,
        system_prompt_id=system_prompt_id,
        knowledge_service=knowledge_service,
        clock_service=clock_service
    )

    return handler


@router.websocket("/ws/voice/{adapter_name}")
async def websocket_voice(
    websocket: WebSocket,
    adapter_name: str,
    session_id: Optional[str] = Query(None, description="Session ID for conversation history"),
    user_id: Optional[str] = Query(None, description="User ID for tracking"),
    api_key: Optional[str] = Query(None, description="API key for authentication")
):
    """
    WebSocket endpoint for real-time voice conversations.

    This endpoint enables bidirectional audio streaming between client and AI.

    Protocol:
    - Client sends: {"type": "audio_chunk", "data": "base64_audio", "format": "wav"}
    - Server sends: {"type": "audio_chunk", "data": "base64_audio", "format": "wav", "chunk_index": 0}
    - Client can interrupt: {"type": "interrupt"}
    - Server sends transcription (optional): {"type": "transcription", "text": "..."}
    - Server sends errors: {"type": "error", "message": "..."}
    - Server sends completion: {"type": "done", "session_id": "..."}

    Args:
        websocket: WebSocket connection
        adapter_name: Name of the adapter to use
        session_id: Optional session ID for conversation history
        user_id: Optional user ID for tracking

    Example client connection:
        ws://localhost:8000/ws/voice/real-time-voice-chat?session_id=abc123
    """
    handler = None

    try:
        # Validate adapter before accepting connection
        adapter_config = await validate_adapter(adapter_name, websocket)

        # Get services from app state
        chat_service = get_chat_service(websocket)
        config = get_config(websocket)

        # Validate API key if required by adapter
        requires_auth = adapter_config.get('capabilities', {}).get('requires_api_key_validation', False)
        if requires_auth:
            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail="API key required for this adapter"
                )
            # TODO: Add actual API key validation logic here
            # For now, we accept any non-empty API key
            logger.info(f"API key provided for adapter: {adapter_name}")

        # Extract system_prompt_id from API key if provided
        system_prompt_id = None
        if api_key:
            api_key_service = getattr(websocket.app.state, 'api_key_service', None)
            if api_key_service:
                try:
                    adapter_manager = getattr(websocket.app.state, 'adapter_manager', None)
                    is_valid, _, system_prompt_id = await api_key_service.validate_api_key(
                        api_key, adapter_manager=adapter_manager
                    )
                    if system_prompt_id:
                        logger.info(f"API key has system_prompt_id: {system_prompt_id}")
                except Exception as e:
                    logger.warning(f"Failed to validate API key for prompt lookup: {e}")

        # Check adapter type to determine handler
        adapter_type = adapter_config.get('type', '')

        if adapter_type == 'speech_to_speech':
            # Use PersonaPlex handler for full-duplex speech-to-speech
            prompt_service = getattr(websocket.app.state, 'prompt_service', None)
            clock_service = getattr(websocket.app.state, 'clock_service', None)

            handler = await _create_personaplex_handler(
                websocket=websocket,
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                config=config,
                session_id=session_id,
                user_id=user_id,
                prompt_service=prompt_service,
                system_prompt_id=str(system_prompt_id) if system_prompt_id else None,
                clock_service=clock_service
            )
        else:
            # Use standard voice handler for cascade (STT -> LLM -> TTS)
            handler = VoiceWebSocketHandler(
                websocket=websocket,
                chat_service=chat_service,
                adapter_name=adapter_name,
                config=config,
                session_id=session_id,
                user_id=user_id
            )

            # Initialize handler
            await handler.initialize()

            # Accept connection
            await handler.accept_connection()

        # Run message loop
        await handler.run()

    except HTTPException as e:
        # Send error before closing
        try:
            await websocket.send_json({
                "type": "error",
                "message": e.detail
            })
        except Exception:
            pass
        logger.error(f"HTTP exception in voice WebSocket: {e.detail}")

    except WebSocketDisconnect:
        logger.info(f"Voice WebSocket disconnected for adapter: {adapter_name}")

    except Exception as e:
        logger.error(f"Error in voice WebSocket endpoint: {str(e)}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except Exception:
            pass

    finally:
        # Cleanup
        if handler:
            try:
                await handler.cleanup()
            except Exception as e:
                logger.error(f"Error during handler cleanup: {str(e)}")


@router.get("/voice/status")
async def voice_status(request: Request):
    """
    Get status of voice service and available adapters.

    Returns information about:
    - Voice service availability
    - Audio providers configured
    - Adapters supporting real-time audio

    Returns:
        Dictionary with voice service status
    """
    try:
        chat_service = get_chat_service(request)
        config = get_config(request)

        # Get adapter manager
        if not hasattr(chat_service, 'context_builder') or not chat_service.context_builder:
            return {
                "available": False,
                "error": "Chat service not properly initialized"
            }

        adapter_manager = chat_service.context_builder.adapter_manager
        if not adapter_manager:
            return {
                "available": False,
                "error": "Adapter manager not available"
            }

        # Find all adapters that support real-time audio
        all_adapters = adapter_manager.get_all_adapter_names()
        voice_adapters = []

        for adapter_name in all_adapters:
            adapter_config = adapter_manager.get_adapter_config(adapter_name)
            if not adapter_config:
                continue

            capabilities = adapter_config.get('capabilities', {})
            if capabilities.get('supports_realtime_audio', False):
                adapter_type = adapter_config.get('type', 'passthrough')
                is_full_duplex = adapter_type == 'speech_to_speech'

                adapter_info = {
                    "name": adapter_name,
                    "type": adapter_type,
                    "enabled": adapter_config.get('enabled', False),
                    "full_duplex": is_full_duplex
                }

                if is_full_duplex:
                    # PersonaPlex adapters
                    adapter_info["mode"] = "speech_to_speech"
                    persona = adapter_config.get('persona', {})
                    adapter_info["voice"] = persona.get('voice_prompt', 'default')
                else:
                    # Traditional cascade adapters
                    adapter_info["mode"] = "cascade"
                    adapter_info["audio_provider"] = adapter_config.get('audio_provider', 'unknown')
                    adapter_info["stt_provider"] = adapter_config.get('stt_provider')
                    adapter_info["tts_provider"] = adapter_config.get('tts_provider')

                voice_adapters.append(adapter_info)

        # Get global sound configuration
        sound_config = config.get('sound', {})

        return {
            "available": True,
            "global_audio_enabled": sound_config.get('enabled', False),
            "default_provider": sound_config.get('provider', 'unknown'),
            "adapters": voice_adapters,
            "websocket_endpoint": "/ws/voice/{adapter_name}"
        }

    except Exception as e:
        logger.error(f"Error getting voice status: {str(e)}", exc_info=True)
        return {
            "available": False,
            "error": str(e)
        }
