"""
Voice Routes

WebSocket endpoints for real-time voice conversations with AI.
"""

import logging
from typing import Optional
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


async def validate_adapter(adapter_name: str, request: Request) -> bool:
    """
    Validate that the adapter exists and supports real-time audio.

    Args:
        adapter_name: Adapter name to validate
        request: FastAPI request

    Returns:
        True if adapter is valid

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

    # Check if audio provider is configured
    audio_provider = adapter_config.get('audio_provider')
    if not audio_provider:
        raise HTTPException(
            status_code=400,
            detail=f"Adapter '{adapter_name}' has no audio provider configured"
        )

    logger.info(
        f"Adapter validation successful: {adapter_name}, "
        f"audio provider: {audio_provider}"
    )

    return True


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
        await validate_adapter(adapter_name, websocket)

        # Get services from app state
        chat_service = get_chat_service(websocket)
        config = get_config(websocket)

        # Validate API key if required by adapter
        if hasattr(chat_service, 'context_builder') and chat_service.context_builder:
            adapter_manager = chat_service.context_builder.adapter_manager
            if adapter_manager:
                adapter_config = adapter_manager.get_adapter_config(adapter_name)
                if adapter_config:
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

        # Create handler
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
                voice_adapters.append({
                    "name": adapter_name,
                    "audio_provider": adapter_config.get('audio_provider', 'unknown'),
                    "enabled": adapter_config.get('enabled', False)
                })

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
